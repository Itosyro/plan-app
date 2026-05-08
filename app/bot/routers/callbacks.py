"""Inline-button callback handlers for task actions.

Phase 3b: ✅ done, 🔄 move (horizon picker), 🗑 delete.
Callback data format: ``task:<action>:<task_id>[:<extra>]``.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.services import (
    delete_task,
    get_or_create_user,
    get_task_by_id,
    mark_task_done,
    update_task_horizon,
)
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)

HORIZON_OPTIONS: list[tuple[str, str]] = [
    ("today", "Сегодня"),
    ("tomorrow", "Завтра"),
    ("week", "На неделе"),
    ("month", "В месяце"),
    ("year", "В году"),
    ("someday", "Когда-нибудь"),
]


def task_action_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Build the inline keyboard shown under each task."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton(
                    text="🔄 Перенести", callback_data=f"task:pick_move:{task_id}"
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:delete:{task_id}"),
            ],
        ],
    )


def horizon_picker_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Build the horizon-selection keyboard for moving a task."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug, label in HORIZON_OPTIONS:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"task:move:{task_id}:{slug}",
            ),
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="↩ Назад", callback_data=f"task:cancel:{task_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_router() -> Router:
    """Build a fresh ``callbacks`` router."""
    router = Router(name="callbacks")

    @router.callback_query(F.data.startswith("task:done:"))
    async def cb_task_done(callback: CallbackQuery) -> None:
        """Mark a task as completed."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат.")
            return
        task_id = int(parts[2])

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            await mark_task_done(session, task, user.id)

        await callback.answer("✅ Выполнено!")
        if callback.message is not None:
            await callback.message.edit_text(
                f"✅ ~{task.title}~ — выполнено",
                parse_mode="Markdown",
            )

    @router.callback_query(F.data.startswith("task:delete:"))
    async def cb_task_delete(callback: CallbackQuery) -> None:
        """Delete a task."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат.")
            return
        task_id = int(parts[2])

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            title = task.title
            await delete_task(session, task, user.id)

        await callback.answer("🗑 Удалено!")
        if callback.message is not None:
            await callback.message.edit_text(f"🗑 ~{title}~ — удалено", parse_mode="Markdown")

    @router.callback_query(F.data.startswith("task:pick_move:"))
    async def cb_task_pick_move(callback: CallbackQuery) -> None:
        """Show horizon picker for moving a task."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат.")
            return
        task_id = int(parts[2])

        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_reply_markup(
                reply_markup=horizon_picker_keyboard(task_id),
            )

    @router.callback_query(F.data.startswith("task:move:"))
    async def cb_task_move(callback: CallbackQuery) -> None:
        """Move a task to a chosen horizon."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 4:
            await callback.answer("Неверный формат.")
            return
        task_id = int(parts[2])
        target_horizon = parts[3]

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            await update_task_horizon(session, task, target_horizon, user.id)

        horizon_labels = dict(HORIZON_OPTIONS)
        label = horizon_labels.get(target_horizon, target_horizon)
        await callback.answer(f"Перенесено → {label}")
        if callback.message is not None:
            await callback.message.edit_text(
                f"🔄 «{task.title}» → {label}",
                parse_mode="Markdown",
            )

    @router.callback_query(F.data.startswith("task:cancel:"))
    async def cb_task_cancel(callback: CallbackQuery) -> None:
        """Cancel horizon picker — restore action buttons."""
        if callback.from_user is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Неверный формат.")
            return
        task_id = int(parts[2])

        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_reply_markup(
                reply_markup=task_action_keyboard(task_id),
            )

    return router
