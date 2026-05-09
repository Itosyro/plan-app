"""Tests for Phase 3c /settings command and inline setting editors."""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.routers.settings import (
    SETTING_DISPLAY,
    SETTING_LABELS,
    SETTING_OPTIONS,
    _format_settings,
    _options_keyboard,
    _settings_keyboard,
    parse_set_callback,
)
from app.bot.services import (
    REMINDER_PRESETS,
    complete_onboarding,
    get_or_create_user,
    get_user_settings,
    reminder_preset_from_offsets,
    update_user_settings,
)
from app.db.models import User, UserSettings

# ── Keyboard builder tests ───────────────────────────────────────────


def test_settings_keyboard_has_all_fields() -> None:
    kb = _settings_keyboard()
    data_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    for field in SETTING_LABELS:
        assert f"settings:edit:{field}" in data_values


def test_options_keyboard_has_back_button() -> None:
    kb = _options_keyboard("critic_mode")
    last_row = kb.inline_keyboard[-1]
    assert last_row[0].callback_data == "settings:back"
    assert last_row[0].text == "↩ Назад"


def test_options_keyboard_has_all_options() -> None:
    for field, options in SETTING_OPTIONS.items():
        kb = _options_keyboard(field)
        data_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        for value, _label in options:
            assert f"settings:set:{field}:{value}" in data_values


def test_parse_set_callback_round_trips_every_keyboard_button() -> None:
    """Regression for R-NEW-C-1: every ``callback_data`` produced by
    ``_options_keyboard`` must be parseable back into ``(field, value)``
    by ``parse_set_callback`` (which is what ``cb_settings_set`` calls).

    Before the fix, the handler used ``split(":")`` and rejected every
    ``HH:MM`` value as malformed — so all 8 morning/evening digest-time
    buttons were silently inert in the UI.
    """
    for field, options in SETTING_OPTIONS.items():
        kb = _options_keyboard(field)
        for row in kb.inline_keyboard:
            for btn in row:
                data = btn.callback_data
                if data is None or not data.startswith("settings:set:"):
                    continue
                parsed = parse_set_callback(data)
                assert parsed is not None, f"button data {data!r} did not parse"
                got_field, got_value = parsed
                assert got_field == field, f"field round-trip broken for {data!r}"
                # The value in the keyboard must match what we'll persist.
                assert any(got_value == v for v, _ in options), (
                    f"value {got_value!r} not in declared options for {field!r}"
                )


def test_parse_set_callback_rejects_malformed_input() -> None:
    """``parse_set_callback`` must return ``None`` for prefix or arity
    mismatches so the handler can answer ``"Неверный формат."`` instead
    of crashing.
    """
    assert parse_set_callback("settings:set") is None
    assert parse_set_callback("settings:set:critic_mode") is None
    assert parse_set_callback("foo:set:critic_mode:always") is None
    assert parse_set_callback("settings:edit:critic_mode") is None
    # Arity-4 with empty value is technically parseable; service layer
    # will reject the empty value via ``ALLOWED_SETTING_VALUES``.
    assert parse_set_callback("settings:set:critic_mode:") == ("critic_mode", "")


# ── Formatter tests ──────────────────────────────────────────────────


def test_format_settings_default_values() -> None:
    settings = UserSettings(user_id=1)
    user = User(id=1, telegram_id=1, tz="Europe/Moscow")
    result = _format_settings(settings, user)
    assert "Настройки" in result
    assert "Режим критика" in result
    assert "По уверенности" in result
    assert "08:00" in result
    assert "21:00" in result
    assert "Москва" in result
    assert "Часовой пояс" in result
    assert "Дефолтные напоминания" in result


def test_format_settings_custom_values() -> None:
    settings = UserSettings(
        user_id=1,
        critic_mode="always",
        morning_digest_at="07:00",
        response_style_source="llm_only",
        courier_template_style="friendly",
    )
    user = User(id=1, telegram_id=1, tz="Asia/Almaty")
    result = _format_settings(settings, user)
    assert "Всегда" in result
    assert "07:00" in result
    assert "Только LLM" in result
    assert "Дружеский" in result
    assert "Алматы" in result


def test_format_settings_without_user_falls_back_to_utc() -> None:
    settings = UserSettings(user_id=1)
    result = _format_settings(settings)
    assert "UTC" in result


def test_format_settings_returns_plain_text_no_markdown() -> None:
    """I-6 regression: ``_format_settings`` must not emit Markdown.

    The settings panel was previously sent with ``parse_mode="Markdown"``.
    Although the label set is currently safe, this is fragile: any future
    field whose display value contains Markdown-active characters
    (``*``, ``_``, ``[``, ```` ` ````) would cause Telegram to return a
    400 error and the panel to disappear. We render plain text instead.
    """
    settings = UserSettings(user_id=1)
    user = User(id=1, telegram_id=1, tz="Europe/Moscow")
    result = _format_settings(settings, user)
    # Title is plain text (no surrounding asterisks)
    assert "*Настройки*" not in result
    assert "Настройки" in result
    # No Markdown control chars (other than emoji and bullet which aren't md-active)
    for ch in ("*", "_", "[", "]", "`"):
        assert ch not in result, f"Markdown char {ch!r} leaked into _format_settings output"


# ── Service tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_user_settings_critic_mode(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=300)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест", tz="Europe/Moscow")
    await session.commit()

    updated = await update_user_settings(session, user.id, "critic_mode", "always")
    assert updated is not None
    assert updated.critic_mode == "always"
    await session.commit()

    reloaded = await get_user_settings(session, user.id)
    assert reloaded is not None
    assert reloaded.critic_mode == "always"


@pytest.mark.asyncio
async def test_update_user_settings_morning_digest(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=301)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест2", tz="Asia/Almaty")
    await session.commit()

    updated = await update_user_settings(session, user.id, "morning_digest_at", "09:00")
    assert updated is not None
    assert updated.morning_digest_at == "09:00"


@pytest.mark.asyncio
async def test_update_user_settings_disallowed_field(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=302)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест3", tz="UTC")
    await session.commit()

    result = await update_user_settings(session, user.id, "nonexistent_field", "value")
    assert result is None


@pytest.mark.asyncio
async def test_update_user_settings_rejects_unknown_value(session: AsyncSession) -> None:
    """Regression for C-2: a replayed/crafted callback with a value that
    isn't in the allow-list must be rejected — and must not corrupt the
    DB column with a ``setattr`` of arbitrary string.
    """
    user, _ = await get_or_create_user(session, telegram_id=309)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест9", tz="UTC")
    await session.commit()

    # critic_mode allows {always, confidence, never} — anything else is bad
    bad = await update_user_settings(session, user.id, "critic_mode", "haxxor")
    assert bad is None

    settings = await get_user_settings(session, user.id)
    assert settings is not None
    assert settings.critic_mode != "haxxor"

    # Same for morning_digest_at — must be one of the canned slots
    bad_time = await update_user_settings(session, user.id, "morning_digest_at", "25:99")
    assert bad_time is None

    # Same for response_style_source: a string from the *old* vocab
    # (pre-2026-05-09) is now rejected too, so reusing a stale callback
    # button can't poison the column. See REVIEW-2026-05-09.md::C-1.
    bad_style = await update_user_settings(session, user.id, "response_style_source", "shouty")
    assert bad_style is None

    stale_old_value = await update_user_settings(
        session,
        user.id,
        "response_style_source",
        "formal",
    )
    assert stale_old_value is None

    bad_template = await update_user_settings(
        session,
        user.id,
        "courier_template_style",
        "shouty",
    )
    assert bad_template is None


@pytest.mark.asyncio
async def test_update_user_settings_no_settings_row(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=303)
    await session.commit()
    assert user.id is not None

    result = await update_user_settings(session, user.id, "critic_mode", "always")
    assert result is None


@pytest.mark.asyncio
async def test_update_user_settings_response_style(session: AsyncSession) -> None:
    """C-1 regression: each of the three valid source values round-trips.

    The pre-2026-05-09 vocab (``formal``/``casual``/``mix``) doesn't match
    the courier's branch logic and is now rejected by the allow-list;
    only ``template_only`` / ``llm_only`` / ``mix`` are accepted.
    """
    user, _ = await get_or_create_user(session, telegram_id=304)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест4", tz="Europe/London")
    await session.commit()

    for value in ("template_only", "llm_only", "mix"):
        updated = await update_user_settings(
            session,
            user.id,
            "response_style_source",
            value,
        )
        assert updated is not None, value
        assert updated.response_style_source == value


@pytest.mark.asyncio
async def test_update_user_settings_courier_template_style(session: AsyncSession) -> None:
    """C-1 regression: each of the six template styles round-trips.

    Vocabulary must match the keys of ``app/ai/courier.py::TEMPLATES``
    — a divergence is the bug class C-1 was about.
    """
    user, _ = await get_or_create_user(session, telegram_id=311)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="ТесА11", tz="UTC")
    await session.commit()

    for value in ("neutral", "formal_master", "friendly", "playful", "terse", "respectful"):
        updated = await update_user_settings(
            session,
            user.id,
            "courier_template_style",
            value,
        )
        assert updated is not None, value
        assert updated.courier_template_style == value


@pytest.mark.asyncio
async def test_update_user_settings_tz_persists_on_user(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=305)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест5", tz="Europe/Moscow")
    await session.commit()

    result = await update_user_settings(session, user.id, "tz", "Asia/Almaty")
    assert result is not None
    await session.commit()

    await session.refresh(user)
    assert user.tz == "Asia/Almaty"


@pytest.mark.asyncio
async def test_update_user_settings_tz_invalid_rejected(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=306)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест6", tz="Europe/Moscow")
    await session.commit()

    result = await update_user_settings(session, user.id, "tz", "Europe/Atlantida")
    assert result is None
    await session.refresh(user)
    assert user.tz == "Europe/Moscow"


@pytest.mark.asyncio
async def test_update_user_settings_reminder_preset(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=307)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест7", tz="UTC")
    await session.commit()

    updated = await update_user_settings(session, user.id, "reminder_preset", "minimal")
    assert updated is not None
    assert updated.default_reminder_offsets == REMINDER_PRESETS["minimal"]

    extra = await update_user_settings(session, user.id, "reminder_preset", "extra")
    assert extra is not None
    assert extra.default_reminder_offsets == REMINDER_PRESETS["extra"]


@pytest.mark.asyncio
async def test_update_user_settings_reminder_preset_invalid(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=308)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест8", tz="UTC")
    await session.commit()

    result = await update_user_settings(session, user.id, "reminder_preset", "supersized")
    assert result is None


def test_reminder_preset_from_offsets_known() -> None:
    assert reminder_preset_from_offsets(REMINDER_PRESETS["default"]) == "default"
    assert reminder_preset_from_offsets(REMINDER_PRESETS["minimal"]) == "minimal"
    assert reminder_preset_from_offsets(REMINDER_PRESETS["extra"]) == "extra"


def test_reminder_preset_from_offsets_custom() -> None:
    custom = {"same_day": [42], "multi_day": [99]}
    assert reminder_preset_from_offsets(custom) == "custom"


# ── Display mapping tests ───────────────────────────────────────────


def test_setting_display_maps_all_options() -> None:
    for field, options in SETTING_OPTIONS.items():
        for value, label in options:
            assert SETTING_DISPLAY[field][value] == label
