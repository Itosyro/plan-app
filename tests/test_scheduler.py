"""Tests for Phase 4b cron worker (`app/workers/scheduler.py`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import get_or_create_user
from app.db.models import Reminder, Task
from app.workers.scheduler import (
    MAX_REMINDER_ATTEMPTS,
    _format_reminder,
    tick_reminders,
)


class _FakeBot:
    """Drop-in stand-in for ``aiogram.Bot.send_message``."""

    def __init__(self, *, fail: bool = False, fail_with: Exception | None = None) -> None:
        self.fail = fail
        self.fail_with = fail_with or RuntimeError("boom")
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str, **_: Any) -> None:
        if self.fail:
            raise self.fail_with
        self.calls.append((chat_id, text))


async def _seed(
    session: AsyncSession,
    *,
    telegram_id: int,
    title: str = "Купить хлеб",
    fire_at: datetime,
    due_at: datetime | None = None,
    status: str = "pending",
    attempts: int = 0,
) -> Reminder:
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.flush()
    assert user.id is not None
    task = Task(user_id=user.id, title=title, due_at=due_at)
    session.add(task)
    await session.flush()
    assert task.id is not None
    reminder = Reminder(
        user_id=user.id,
        task_id=task.id,
        fire_at=fire_at,
        status=status,
        attempts=attempts,
    )
    session.add(reminder)
    await session.commit()
    return reminder


def test_format_reminder_with_time() -> None:
    task = Task(user_id=1, title="Совещание", due_at=datetime(2026, 5, 8, 11, 0))
    assert _format_reminder(task) == "⏰ Напоминаю: Совещание — в 11:00."


def test_format_reminder_without_time() -> None:
    task = Task(user_id=1, title="Йога")
    assert _format_reminder(task) == "⏰ Напоминаю: Йога"


def test_format_reminder_midnight_due_treated_as_no_time() -> None:
    task = Task(user_id=1, title="Без часа", due_at=datetime(2026, 5, 8, 0, 0))
    assert _format_reminder(task) == "⏰ Напоминаю: Без часа"


@pytest.mark.asyncio
async def test_tick_sends_due_reminders(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(session, telegram_id=900, fire_at=now - timedelta(minutes=1))
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 1, "retry": 0, "failed": 0}
    assert len(bot.calls) == 1
    assert bot.calls[0][0] == 900
    rows = list((await session.exec(select(Reminder))).all())
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None
    assert rows[0].last_error is None


@pytest.mark.asyncio
async def test_tick_skips_future_reminders(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(session, telegram_id=901, fire_at=now + timedelta(minutes=10))
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 0, "retry": 0, "failed": 0}
    assert bot.calls == []
    rows = list((await session.exec(select(Reminder))).all())
    assert rows[0].status == "pending"
    assert rows[0].attempts == 0


@pytest.mark.asyncio
async def test_tick_skips_already_sent(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(
        session,
        telegram_id=902,
        fire_at=now - timedelta(minutes=10),
        status="sent",
    )
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 0, "retry": 0, "failed": 0}
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_retries_on_failure(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    rem = await _seed(session, telegram_id=903, fire_at=now - timedelta(minutes=1))
    bot = _FakeBot(fail=True, fail_with=RuntimeError("network down"))

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 0, "retry": 1, "failed": 0}
    await session.refresh(rem)
    assert rem.status == "pending"
    assert rem.attempts == 1
    assert rem.last_error is not None
    assert "network down" in rem.last_error


@pytest.mark.asyncio
async def test_tick_marks_failed_after_max_attempts(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    rem = await _seed(
        session,
        telegram_id=904,
        fire_at=now - timedelta(minutes=1),
        attempts=MAX_REMINDER_ATTEMPTS - 1,
    )
    bot = _FakeBot(fail=True)

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 0, "retry": 0, "failed": 1}
    await session.refresh(rem)
    assert rem.status == "failed"
    assert rem.attempts == MAX_REMINDER_ATTEMPTS


@pytest.mark.asyncio
async def test_tick_processes_multiple_reminders(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(session, telegram_id=905, fire_at=now - timedelta(minutes=5))
    await _seed(session, telegram_id=905, fire_at=now - timedelta(minutes=2))
    await _seed(session, telegram_id=905, fire_at=now + timedelta(minutes=10))
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert result == {"sent": 2, "retry": 0, "failed": 0}
    assert len(bot.calls) == 2
