"""Unit tests for `app/bot/services.py` (no aiogram fixtures needed)."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import (
    complete_onboarding,
    get_or_create_user,
    is_update_processed,
    is_valid_timezone,
    record_update,
    store_inbox_text,
)
from app.db.models import InboxEntry, TelegramUpdate, User, UserSettings


def test_is_valid_timezone_true_cases() -> None:
    assert is_valid_timezone("Europe/Moscow")
    assert is_valid_timezone("Asia/Tashkent")
    assert is_valid_timezone("UTC")


def test_is_valid_timezone_false_cases() -> None:
    assert not is_valid_timezone("Mars/Olympus")
    assert not is_valid_timezone("")
    assert not is_valid_timezone("not a tz")


@pytest.mark.asyncio
async def test_get_or_create_user_creates_then_finds(session: AsyncSession) -> None:
    user, created = await get_or_create_user(session, telegram_id=42, lang_code="ru")
    assert created is True
    assert user.id is not None
    assert user.telegram_id == 42
    assert user.lang_code == "ru"
    assert user.tz == "UTC"  # default before onboarding
    assert user.onboarded_at is None
    await session.commit()

    again, created2 = await get_or_create_user(session, telegram_id=42)
    assert created2 is False
    assert again.id == user.id


@pytest.mark.asyncio
async def test_complete_onboarding_writes_user_and_settings(
    session: AsyncSession,
) -> None:
    user, _ = await get_or_create_user(session, telegram_id=7)
    await session.commit()

    settings = await complete_onboarding(session, user, display_name="Юсуф", tz="Europe/Moscow")
    await session.commit()

    fetched = (await session.exec(select(User).where(User.telegram_id == 7))).first()
    assert fetched is not None
    assert fetched.display_name == "Юсуф"
    assert fetched.tz == "Europe/Moscow"
    assert fetched.onboarded_at is not None

    fetched_settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).first()
    assert fetched_settings is not None
    assert fetched_settings.critic_mode == "confidence"
    assert fetched_settings.critic_confidence_threshold == pytest.approx(0.7)
    assert fetched_settings.morning_digest_at == "08:00"
    assert fetched_settings.evening_digest_at == "21:00"
    assert fetched_settings.response_style_source == "mix"
    assert fetched_settings.week_due_semantic == "deadline_sunday"
    assert fetched_settings.default_reminder_offsets == {
        "same_day": [60, 15],
        "multi_day": [1440, 60],
    }
    assert settings.user_id == user.id


@pytest.mark.asyncio
async def test_record_and_check_idempotency(session: AsyncSession) -> None:
    assert await is_update_processed(session, 100) is False
    await record_update(session, update_id=100, user_id=None, kind="message")
    await session.commit()
    assert await is_update_processed(session, 100) is True

    rows = (await session.exec(select(TelegramUpdate))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_store_inbox_text(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=11)
    await session.commit()
    assert user.id is not None

    entry = await store_inbox_text(
        session,
        user_id=user.id,
        raw_text="купить хлеб",
        telegram_message_id=999,
    )
    await session.commit()

    rows = (await session.exec(select(InboxEntry))).all()
    assert len(rows) == 1
    assert rows[0].id == entry.id
    assert rows[0].kind == "text"
    assert rows[0].raw_text == "купить хлеб"
    assert rows[0].telegram_message_id == 999
