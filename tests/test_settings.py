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
)
from app.bot.services import (
    complete_onboarding,
    get_or_create_user,
    get_user_settings,
    update_user_settings,
)
from app.db.models import UserSettings

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


# ── Formatter tests ──────────────────────────────────────────────────


def test_format_settings_default_values() -> None:
    settings = UserSettings(user_id=1)
    result = _format_settings(settings)
    assert "Настройки" in result
    assert "Режим критика" in result
    assert "По уверенности" in result
    assert "08:00" in result
    assert "21:00" in result


def test_format_settings_custom_values() -> None:
    settings = UserSettings(
        user_id=1,
        critic_mode="always",
        morning_digest_at="07:00",
        response_style_source="formal",
    )
    result = _format_settings(settings)
    assert "Всегда" in result
    assert "07:00" in result
    assert "Формальный" in result


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
async def test_update_user_settings_no_settings_row(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=303)
    await session.commit()
    assert user.id is not None

    result = await update_user_settings(session, user.id, "critic_mode", "always")
    assert result is None


@pytest.mark.asyncio
async def test_update_user_settings_response_style(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=304)
    await session.commit()
    assert user.id is not None
    await complete_onboarding(session, user, display_name="Тест4", tz="Europe/London")
    await session.commit()

    updated = await update_user_settings(session, user.id, "response_style_source", "formal")
    assert updated is not None
    assert updated.response_style_source == "formal"


# ── Display mapping tests ───────────────────────────────────────────


def test_setting_display_maps_all_options() -> None:
    for field, options in SETTING_OPTIONS.items():
        for value, label in options:
            assert SETTING_DISPLAY[field][value] == label
