"""Unit tests for `app/bot/services.py` (no aiogram fixtures needed)."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import (
    claim_update,
    complete_onboarding,
    get_or_create_user,
    is_update_processed,
    is_valid_timezone,
    record_update,
    store_inbox_text,
)
from app.db.base import get_sessionmaker
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
async def test_complete_onboarding_is_idempotent(session: AsyncSession) -> None:
    """Regression for R-NEW-I-3: re-running ``/start`` after onboarding
    must not raise ``IntegrityError`` on the ``UserSettings.user_id`` PK.

    The user's earlier UI tweaks (critic_mode, digest times, etc.) are
    preserved across re-onboarding — we only update the User row.
    """
    user, _ = await get_or_create_user(session, telegram_id=88)
    await session.commit()
    s1 = await complete_onboarding(session, user, display_name="Aйша", tz="Europe/Moscow")
    await session.commit()

    # Pretend the user later changed a setting through /settings.
    s1.critic_mode = "always"
    s1.morning_digest_at = "09:00"
    session.add(s1)
    await session.commit()

    # Wiped chat → /start again → completes the wizard a second time.
    s2 = await complete_onboarding(session, user, display_name="Aйша", tz="Asia/Tashkent")
    await session.commit()

    # Same row, not a fresh one — user-tweaked fields survive.
    assert s2.user_id == user.id
    assert s2.critic_mode == "always"
    assert s2.morning_digest_at == "09:00"

    # The User row was updated to the new tz / display_name.
    fetched = (await session.exec(select(User).where(User.telegram_id == 88))).first()
    assert fetched is not None
    assert fetched.tz == "Asia/Tashkent"

    # Still exactly one settings row in the DB.
    all_settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).all()
    assert len(all_settings) == 1


@pytest.mark.asyncio
async def test_record_and_check_idempotency(session: AsyncSession) -> None:
    assert await is_update_processed(session, 100) is False
    await record_update(session, update_id=100, user_id=None, kind="message")
    await session.commit()
    assert await is_update_processed(session, 100) is True

    rows = (await session.exec(select(TelegramUpdate))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_claim_update_first_caller_inserts(session: AsyncSession) -> None:
    """First call to ``claim_update`` for a fresh ``update_id`` returns True
    and persists the row.
    """
    assert await is_update_processed(session, 200) is False
    claimed = await claim_update(session, update_id=200, user_id=None, kind="message")
    await session.commit()
    assert claimed is True
    rows = (await session.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == 200))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_claim_update_duplicate_returns_false_without_raising(
    engine: None,
) -> None:
    """Regression for R-NEW-C-5: a second ``claim_update`` for the same
    ``update_id`` (e.g. from a concurrent webhook delivery that lost the
    INSERT race) must return ``False`` instead of propagating the
    primary-key ``IntegrityError`` up to the webhook handler.
    """
    sm = get_sessionmaker()
    async with sm() as s1:
        first = await claim_update(s1, update_id=300, user_id=None, kind="message")
        await s1.commit()
    assert first is True

    # Independent session — emulates the second concurrent webhook delivery.
    async with sm() as s2:
        second = await claim_update(s2, update_id=300, user_id=None, kind="message")
        await s2.commit()
    assert second is False

    async with sm() as s3:
        rows = (await s3.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == 300))).all()
        assert len(rows) == 1, "duplicate claim must not double-insert the row"


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
