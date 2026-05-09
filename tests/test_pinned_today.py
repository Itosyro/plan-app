"""Tests for the pinned-morning-digest tracker (Phase 6.3)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.pinned_today import refresh_pinned_morning, send_and_pin_morning_digest
from app.bot.services import get_or_create_user
from app.db.models import User, UserSettings


class _FakeBot:
    def __init__(
        self,
        *,
        send_fail: Exception | None = None,
        pin_fail: Exception | None = None,
        edit_fail: Exception | None = None,
    ) -> None:
        self.send_fail = send_fail
        self.pin_fail = pin_fail
        self.edit_fail = edit_fail
        self.sends: list[dict[str, Any]] = []
        self.pins: list[dict[str, Any]] = []
        self.edits: list[dict[str, Any]] = []
        self._next_id = 5000

    async def send_message(self, **kwargs: Any) -> SimpleNamespace:
        if self.send_fail:
            raise self.send_fail
        self.sends.append(kwargs)
        msg_id = self._next_id
        self._next_id += 1
        return SimpleNamespace(message_id=msg_id)

    async def pin_chat_message(self, **kwargs: Any) -> bool:
        if self.pin_fail:
            raise self.pin_fail
        self.pins.append(kwargs)
        return True

    async def edit_message_text(self, **kwargs: Any) -> bool:
        if self.edit_fail:
            raise self.edit_fail
        self.edits.append(kwargs)
        return True


async def _setup_user(
    session: AsyncSession, *, telegram_id: int = 9001
) -> tuple[int, UserSettings]:
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    assert user.id is not None
    today = date(2026, 5, 9)
    settings = UserSettings(user_id=user.id, last_morning_digest_on=today)
    session.add(settings)
    await session.flush()
    return user.id, settings


async def _get_user(session: AsyncSession, telegram_id: int) -> User:
    """Re-fetch the user without recreating settings (helper for tests)."""
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    return user


@pytest.mark.asyncio
async def test_send_and_pin_records_message_id_and_chat(session: AsyncSession) -> None:
    _user_id, settings = await _setup_user(session)
    user = await _get_user(session, telegram_id=9001)

    bot = _FakeBot()
    msg_id = await send_and_pin_morning_digest(bot, session, user, settings, "🌅 Доброе утро!")
    assert msg_id is not None
    assert len(bot.sends) == 1
    assert bot.sends[0]["text"] == "🌅 Доброе утро!"
    assert len(bot.pins) == 1
    assert bot.pins[0]["chat_id"] == 9001
    assert bot.pins[0]["message_id"] == msg_id
    assert settings.pinned_morning_chat_id == 9001
    assert settings.pinned_morning_message_id == msg_id
    assert settings.pinned_morning_date == date(2026, 5, 9)


@pytest.mark.asyncio
async def test_send_and_pin_pin_failure_still_returns_message_id(
    session: AsyncSession,
) -> None:
    """Pin failure (e.g. group chat without admin) shouldn't fail the digest."""
    _user_id, settings = await _setup_user(session, telegram_id=9002)
    user = await _get_user(session, telegram_id=9002)

    bot = _FakeBot(pin_fail=TelegramBadRequest(method=None, message="not enough rights"))  # type: ignore[arg-type]
    msg_id = await send_and_pin_morning_digest(bot, session, user, settings, "🌅 Доброе утро!")
    assert msg_id is not None
    # We sent the message...
    assert len(bot.sends) == 1
    # ...but no tracked pin (pin_chat_message threw).
    assert settings.pinned_morning_chat_id is None
    assert settings.pinned_morning_message_id is None


@pytest.mark.asyncio
async def test_send_and_pin_send_failure_returns_none(session: AsyncSession) -> None:
    """If we can't even send the message, no pin tracking happens."""
    _user_id, settings = await _setup_user(session, telegram_id=9003)
    user = await _get_user(session, telegram_id=9003)

    bot = _FakeBot(send_fail=TelegramForbiddenError(method=None, message="bot was blocked"))  # type: ignore[arg-type]
    msg_id = await send_and_pin_morning_digest(bot, session, user, settings, "🌅 Доброе утро!")
    assert msg_id is None
    assert bot.sends == []
    assert settings.pinned_morning_message_id is None


@pytest.mark.asyncio
async def test_refresh_pinned_morning_no_pin_returns_false(
    session: AsyncSession,
) -> None:
    user_id, _settings = await _setup_user(session, telegram_id=9004)
    bot = _FakeBot()
    ok = await refresh_pinned_morning(bot, session, user_id)
    assert ok is False
    assert bot.edits == []


@pytest.mark.asyncio
async def test_refresh_pinned_morning_stale_date_returns_false(
    session: AsyncSession,
) -> None:
    user_id, settings = await _setup_user(session, telegram_id=9005)
    settings.pinned_morning_chat_id = 9005
    settings.pinned_morning_message_id = 7777
    # Pin from yesterday — should be skipped, not edited.
    settings.pinned_morning_date = date(2026, 5, 8)
    settings.last_morning_digest_on = date(2026, 5, 9)
    session.add(settings)
    await session.flush()

    bot = _FakeBot()
    ok = await refresh_pinned_morning(bot, session, user_id)
    assert ok is False
    assert bot.edits == []
    # We don't clear the pin — the next morning digest send will replace it.
    assert settings.pinned_morning_message_id == 7777


@pytest.mark.asyncio
async def test_refresh_pinned_morning_clears_on_telegram_rejection(
    session: AsyncSession,
) -> None:
    """If Telegram says the message is gone or too old, clear the pin."""
    user_id, settings = await _setup_user(session, telegram_id=9006)
    settings.pinned_morning_chat_id = 9006
    settings.pinned_morning_message_id = 8888
    settings.pinned_morning_date = settings.last_morning_digest_on
    session.add(settings)
    await session.flush()

    bot = _FakeBot(
        edit_fail=TelegramBadRequest(  # type: ignore[arg-type]
            method=None, message="message to edit not found"
        )
    )
    ok = await refresh_pinned_morning(bot, session, user_id)
    assert ok is False
    # Pin cleared — we won't keep retrying.
    res = await session.exec(select(UserSettings).where(UserSettings.user_id == user_id))
    s = res.first()
    assert s is not None
    assert s.pinned_morning_chat_id is None
    assert s.pinned_morning_message_id is None
    assert s.pinned_morning_date is None


@pytest.mark.asyncio
async def test_refresh_pinned_morning_swallows_not_modified(
    session: AsyncSession,
) -> None:
    """`message is not modified` is a non-error (concurrent callbacks)."""
    user_id, settings = await _setup_user(session, telegram_id=9007)
    settings.pinned_morning_chat_id = 9007
    settings.pinned_morning_message_id = 1111
    settings.pinned_morning_date = settings.last_morning_digest_on
    session.add(settings)
    await session.flush()

    bot = _FakeBot(
        edit_fail=TelegramBadRequest(  # type: ignore[arg-type]
            method=None,
            message="Bad Request: message is not modified: specified new message content...",
        )
    )
    ok = await refresh_pinned_morning(bot, session, user_id)
    assert ok is True
    res = await session.exec(select(UserSettings).where(UserSettings.user_id == user_id))
    s = res.first()
    assert s is not None
    # Pin retained — we'll try again on the next done.
    assert s.pinned_morning_message_id == 1111
