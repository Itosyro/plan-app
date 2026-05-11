"""``/settings`` command — view and edit user preferences via inline buttons.

Phase 3c: shows current settings, each editable via callback buttons.
Phase 3 finish: timezone (``tz``) and reminder preset (``reminder_preset``)
are virtual fields — the service layer routes them to ``User.tz`` and
``UserSettings.default_reminder_offsets`` respectively.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.services import (
    get_or_create_user,
    get_user_settings,
    reminder_preset_from_offsets,
    update_user_settings,
)
from app.db.base import session_scope
from app.db.models import User, UserSettings
from app.shared.logging import get_logger

logger = get_logger(__name__)

SETTING_LABELS: dict[str, str] = {
    "critic_mode": "Режим критика",
    "tz": "Часовой пояс",
    "morning_digest_at": "Утренний дайджест",
    "evening_digest_at": "Вечерний дайджест",
    "reminder_preset": "Дефолтные напоминания",
    "response_style_source": "Источник ответа",
    "courier_template_style": "Тон сообщений",
    "week_due_semantic": "Семантика «на неделе»",
    "concretize_tasks": "Первый шаг в задачах",
}

SETTING_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "critic_mode": [
        ("always", "Всегда"),
        ("confidence", "По уверенности"),
        ("never", "Никогда"),
    ],
    "tz": [
        ("Europe/Moscow", "Москва (UTC+3)"),
        ("Europe/Kaliningrad", "Калининград (UTC+2)"),
        ("Europe/Samara", "Самара (UTC+4)"),
        ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
        ("Asia/Almaty", "Алматы (UTC+6)"),
        ("Asia/Tashkent", "Ташкент (UTC+5)"),
        ("Asia/Vladivostok", "Владивосток (UTC+10)"),
        ("UTC", "UTC"),
    ],
    "morning_digest_at": [
        ("07:00", "07:00"),
        ("08:00", "08:00"),
        ("09:00", "09:00"),
        ("10:00", "10:00"),
    ],
    "evening_digest_at": [
        ("20:00", "20:00"),
        ("21:00", "21:00"),
        ("22:00", "22:00"),
        ("23:00", "23:00"),
    ],
    "reminder_preset": [
        ("minimal", "Минимум: за 15 мин / за 1 ч"),
        ("default", "Стандарт: за 1 ч + 15 мин / за день + 1 ч"),
        ("extra", "Подробно: за 3 ч + 1 ч + 15 мин / за день + 4 ч + 1 ч"),
    ],
    "response_style_source": [
        ("template_only", "Только шаблоны"),
        ("llm_only", "Только LLM"),
        ("mix", "Микс (50/50)"),
    ],
    "courier_template_style": [
        ("neutral", "Нейтральный"),
        ("formal_master", "Слуга («мой господин»)"),
        ("friendly", "Дружеский"),
        ("playful", "Игривый"),
        ("terse", "Лаконичный"),
        ("respectful", "Почтительный"),
    ],
    "week_due_semantic": [
        ("deadline_sunday", "Дедлайн воскресенье"),
        ("deadline_saturday", "Дедлайн суббота"),
        ("spread_evenly", "Равномерно"),
    ],
    "concretize_tasks": [
        ("on", "Добавлять"),
        ("off", "Не трогать"),
    ],
}

SETTING_DISPLAY: dict[str, dict[str, str]] = {
    field: dict(options) for field, options in SETTING_OPTIONS.items()
}


def _setting_value(field: str, settings: UserSettings, user: User | None) -> str:
    """Resolve the current raw value for a setting (incl. virtual fields).

    Uses an explicit field-by-field mapping rather than ``getattr`` so the
    type-checker can prove every branch returns a ``str`` and the
    field-allow-list (``SETTING_LABELS``) is the *only* way to reach a
    column. See ``docs/REVIEW-findings.md::I-1``.
    """
    if field == "tz":
        return user.tz if user is not None else "UTC"
    if field == "reminder_preset":
        return reminder_preset_from_offsets(settings.default_reminder_offsets)
    if field == "critic_mode":
        return settings.critic_mode
    if field == "morning_digest_at":
        return settings.morning_digest_at
    if field == "evening_digest_at":
        return settings.evening_digest_at
    if field == "response_style_source":
        return settings.response_style_source
    if field == "courier_template_style":
        return settings.courier_template_style
    if field == "week_due_semantic":
        return settings.week_due_semantic
    if field == "concretize_tasks":
        return "on" if settings.concretize_tasks else "off"
    return "—"


def _format_settings(settings: UserSettings, user: User | None = None) -> str:
    """Format settings into a readable message.

    Returns plain text without Telegram Markdown — task labels and
    setting display values are user-controlled and may contain
    ``*``, ``_``, ``[``, which would break ``parse_mode="Markdown"``.
    See ``docs/REVIEW-2026-05-09.md::I-6`` and ``::P-2``.
    """
    lines = ["⚙️ Настройки\n"]
    for field, label in SETTING_LABELS.items():
        raw = _setting_value(field, settings, user)
        display = SETTING_DISPLAY.get(field, {}).get(raw, raw)
        lines.append(f"• {label}: {display}")
    return "\n".join(lines)


def _settings_keyboard() -> InlineKeyboardMarkup:
    """Build the main settings keyboard with one button per editable field."""
    rows: list[list[InlineKeyboardButton]] = []
    for field, label in SETTING_LABELS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {label}",
                    callback_data=f"settings:edit:{field}",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_set_callback(data: str) -> tuple[str, str] | None:
    """Parse a ``settings:set:<field>:<value>`` callback string.

    Returns ``(field, value)`` on success or ``None`` if the prefix /
    arity check fails. ``maxsplit=3`` keeps ``value`` intact even when
    it itself contains ``":"`` (e.g. ``"08:00"`` for
    ``morning_digest_at``). Before this fix the handler used
    ``split(":")`` and the arity check rejected every time-of-day option
    as malformed. See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-1``.
    """
    parts = data.split(":", 3)
    if len(parts) != 4 or parts[0] != "settings" or parts[1] != "set":
        return None
    return parts[2], parts[3]


def _options_keyboard(field: str) -> InlineKeyboardMarkup:
    """Build the option-selection keyboard for a specific setting."""
    options = SETTING_OPTIONS.get(field, [])
    rows: list[list[InlineKeyboardButton]] = []
    for value, label in options:
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"settings:set:{field}:{value}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="↩ Назад", callback_data="settings:back"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_router() -> Router:
    """Build a fresh ``settings`` router."""
    router = Router(name="settings")

    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        """Show current settings with edit buttons."""
        if message.from_user is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            if user.id is None:
                return
            settings = await get_user_settings(session, user.id)
            user_snapshot = User(id=user.id, telegram_id=user.telegram_id, tz=user.tz)

        if settings is None:
            await message.answer("Настройки не найдены. Пройди /start заново.")
            return

        await message.answer(
            _format_settings(settings, user_snapshot),
            reply_markup=_settings_keyboard(),
        )

    @router.callback_query(F.data.startswith("settings:edit:"))
    async def cb_settings_edit(callback: CallbackQuery) -> None:
        """Show options for a specific setting."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат.")
            return
        field = parts[2]
        if field not in SETTING_LABELS:
            await callback.answer("Неизвестная настройка.")
            return

        label = SETTING_LABELS[field]
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"✏️ {label}\n\nВыберите значение:",
                reply_markup=_options_keyboard(field),
            )

    @router.callback_query(F.data.startswith("settings:set:"))
    async def cb_settings_set(callback: CallbackQuery) -> None:
        """Apply a chosen value to a setting."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_set_callback(callback.data)
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        field, value = parsed

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            updated = await update_user_settings(session, user.id, field, value)
            if updated is None:
                user_snapshot: User | None = None
            else:
                user_snapshot = User(id=user.id, telegram_id=user.telegram_id, tz=user.tz)

        if updated is None:
            await callback.answer("Не удалось обновить.")
            return

        display = SETTING_DISPLAY.get(field, {}).get(value, value)
        label = SETTING_LABELS.get(field, field)
        await callback.answer(f"{label} → {display}")
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                _format_settings(updated, user_snapshot),
                reply_markup=_settings_keyboard(),
            )

    @router.callback_query(F.data == "settings:back")
    async def cb_settings_back(callback: CallbackQuery) -> None:
        """Go back to settings overview."""
        if callback.from_user is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            settings = await get_user_settings(session, user.id)
            user_snapshot = User(id=user.id, telegram_id=user.telegram_id, tz=user.tz)

        if settings is None:
            await callback.answer("Настройки не найдены.")
            return

        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                _format_settings(settings, user_snapshot),
                reply_markup=_settings_keyboard(),
            )

    return router
