"""Tests for Phase 4b digest builders + tick (`app/bot/digest.py`)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.digest import (
    _matches_hhmm,
    _user_local_now,
    build_evening_digest,
    build_morning_digest,
    tick_digests,
)
from app.bot.services import (
    complete_onboarding,
    get_or_create_horizon,
    get_or_create_user,
)
from app.db.models import Task, UserSettings


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str, **_: Any) -> None:
        self.calls.append((chat_id, text))


# ── Helpers ─────────────────────────────────────────────────────────


def test_matches_hhmm_exact() -> None:
    dt = datetime(2026, 5, 8, 8, 0)
    assert _matches_hhmm(dt, "08:00") is True
    assert _matches_hhmm(dt, "08:01") is False
    assert _matches_hhmm(dt, "07:00") is False


def test_matches_hhmm_invalid() -> None:
    dt = datetime(2026, 5, 8, 8, 0)
    assert _matches_hhmm(dt, None) is False
    assert _matches_hhmm(dt, "") is False
    assert _matches_hhmm(dt, "08-00") is False
    assert _matches_hhmm(dt, "8:00") is False  # need zero-padding
    assert _matches_hhmm(dt, "ab:cd") is False


def test_user_local_now_respects_tz() -> None:
    utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)  # 08:00 MSK
    local = _user_local_now("Europe/Moscow", utc)
    assert local.hour == 8 and local.minute == 0


def test_user_local_now_unknown_tz_falls_back_to_utc() -> None:
    utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    local = _user_local_now("Bogus/Zone", utc)
    assert local.hour == 5 and local.tzinfo is not None


def test_user_local_now_handles_naive_input() -> None:
    naive = datetime(2026, 5, 8, 5, 0)  # treat as UTC
    local = _user_local_now("Europe/Moscow", naive)
    assert local.hour == 8


# ── build_morning_digest ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_morning_digest_empty(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1100)
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Доброе утро" in text
    assert "не запланировано" in text


@pytest.mark.asyncio
async def test_morning_digest_lists_today(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1101)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    session.add(
        Task(
            user_id=user.id,
            horizon_id=today.id,
            title="Купить хлеб",
            priority="high",
            due_at=datetime(2026, 5, 8, 9, 0),
        ),
    )
    session.add(
        Task(user_id=user.id, horizon_id=today.id, title="Йога", priority="low"),
    )
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Сегодня:" in text
    assert "🔴 Купить хлеб — в 09:00" in text
    assert "🟢 Йога" in text


@pytest.mark.asyncio
async def test_morning_digest_skips_done_tasks(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1102)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    session.add(
        Task(user_id=user.id, horizon_id=today.id, title="Done", status="done"),
    )
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Open"))
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Open" in text
    assert "Done" not in text


# ── build_evening_digest ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evening_digest_combines_today_and_tomorrow(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1103)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    tomorrow = await get_or_create_horizon(session, user.id, "tomorrow")
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Доделать отчёт"))
    session.add(Task(user_id=user.id, horizon_id=tomorrow.id, title="Совещание"))
    await session.commit()

    text = await build_evening_digest(session, user)

    assert "Подводим итоги" in text
    assert "Осталось на сегодня:" in text
    assert "Доделать отчёт" in text
    assert "Завтра:" in text
    assert "Совещание" in text


@pytest.mark.asyncio
async def test_evening_digest_celebrates_empty_today(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1104)
    await session.commit()

    text = await build_evening_digest(session, user)

    assert "Сегодня всё закрыто" in text


# ── tick_digests ────────────────────────────────────────────────────


async def _onboard(
    session: AsyncSession,
    *,
    telegram_id: int,
    tz: str,
    morning: str = "08:00",
    evening: str = "21:00",
) -> None:
    """Helper: create user, run onboarding, then tweak digest slots."""
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.flush()
    await complete_onboarding(session, user, display_name="Tester", tz=tz)
    settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).first()
    assert settings is not None
    settings.morning_digest_at = morning
    settings.evening_digest_at = evening
    session.add(settings)
    await session.commit()


@pytest.mark.asyncio
async def test_tick_digests_sends_morning_at_local_match(session: AsyncSession) -> None:
    await _onboard(session, telegram_id=1105, tz="Europe/Moscow")

    bot = _FakeBot()
    # 05:00 UTC == 08:00 MSK → morning slot.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 0, tzinfo=UTC))

    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1
    chat_id, text = bot.calls[0]
    assert chat_id == 1105
    assert "Доброе утро" in text


@pytest.mark.asyncio
async def test_tick_digests_skips_off_minute(session: AsyncSession) -> None:
    await _onboard(session, telegram_id=1106, tz="Europe/Moscow")

    bot = _FakeBot()
    # 05:30 UTC == 08:30 MSK — not 08:00.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 30, tzinfo=UTC))

    assert result == {"morning": 0, "evening": 0, "errors": 0}
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_digests_skips_unonboarded(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1107)
    await session.commit()
    assert user.id is not None and user.onboarded_at is None

    settings = UserSettings(user_id=user.id, morning_digest_at="08:00", evening_digest_at="21:00")
    session.add(settings)
    await session.commit()

    bot = _FakeBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 8, 0, tzinfo=UTC))

    assert result == {"morning": 0, "evening": 0, "errors": 0}
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_digests_isolates_one_failing_user(session: AsyncSession) -> None:
    """A failing send for user A shouldn't stop user B from getting their digest."""

    class _PickyBot(_FakeBot):
        async def send_message(self, *, chat_id: int, text: str, **kw: Any) -> None:
            if chat_id == 1108:
                raise RuntimeError("rate limited")
            await super().send_message(chat_id=chat_id, text=text, **kw)

    for tg_id in (1108, 1109):
        await _onboard(session, telegram_id=tg_id, tz="UTC")

    bot = _PickyBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 8, 0, tzinfo=UTC))

    # 1109 receives, 1108 errors.
    assert result["morning"] == 1
    assert result["errors"] == 1
    assert any(c[0] == 1109 for c in bot.calls)
    assert all(c[0] != 1108 for c in bot.calls)
