"""Tests for Phase 4b cron worker (`app/workers/scheduler.py`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import get_or_create_user
from app.db.base import session_scope
from app.db.models import Reminder, Task
from app.workers.scheduler import (
    MAX_REMINDER_ATTEMPTS,
    STALE_REMINDER_HOURS,
    TRASH_RETENTION_HOURS,
    _format_reminder,
    purge_trash,
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
    """C-2: ``due_at`` is naive UTC; rendered HH:MM is in *user_tz*.

    A task due at 11:00 UTC for a Moscow user shows as 14:00 local.
    """
    task = Task(user_id=1, title="Совещание", due_at=datetime(2026, 5, 8, 11, 0))
    assert _format_reminder(task, "Europe/Moscow") == "⏰ Напоминаю: Совещание — в 14:00."
    assert _format_reminder(task, "UTC") == "⏰ Напоминаю: Совещание — в 11:00."


def test_format_reminder_without_time() -> None:
    task = Task(user_id=1, title="Йога")
    assert _format_reminder(task, "Europe/Moscow") == "⏰ Напоминаю: Йога"


def test_format_reminder_midnight_local_treated_as_no_time() -> None:
    """C-2: midnight is judged in the *user's* tz, not UTC.

    21:00 UTC = 00:00 MSK → dropped (sentinel for "date-only deadline").
    """
    task = Task(user_id=1, title="Без часа", due_at=datetime(2026, 5, 7, 21, 0))
    assert _format_reminder(task, "Europe/Moscow") == "⏰ Напоминаю: Без часа"


@pytest.mark.asyncio
async def test_tick_sends_due_reminders(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(session, telegram_id=900, fire_at=now - timedelta(minutes=1))
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert (result["sent"], result["retry"], result["failed"]) == (1, 0, 0)
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

    assert (result["sent"], result["retry"], result["failed"]) == (0, 0, 0)
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

    assert (result["sent"], result["retry"], result["failed"]) == (0, 0, 0)
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_retries_on_failure(session: AsyncSession) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    rem = await _seed(session, telegram_id=903, fire_at=now - timedelta(minutes=1))
    bot = _FakeBot(fail=True, fail_with=RuntimeError("network down"))

    result = await tick_reminders(bot, now=now)

    assert (result["sent"], result["retry"], result["failed"]) == (0, 1, 0)
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

    assert (result["sent"], result["retry"], result["failed"]) == (0, 0, 1)
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

    assert (result["sent"], result["retry"], result["failed"]) == (2, 0, 0)
    assert len(bot.calls) == 2


# ── R-NEW-I-5 regression: claim pattern + per-row commit ─────────────


@pytest.mark.asyncio
async def test_tick_does_not_resend_on_crash_after_send(session: AsyncSession) -> None:
    """Regression for R-NEW-I-5: a crash *after* the Telegram call but
    before the row's terminal state is committed must not resurrect the
    reminder as ``pending`` on the next tick.

    Previously, all rows were collected into a single transaction that
    committed at end-of-batch, so an OOM kill mid-batch left already-
    sent rows back at ``pending`` → the next tick re-sent them. The new
    state machine commits per-row immediately after each send.

    We simulate the partial-progress crash by sending one row through
    ``tick_reminders`` and then verifying that a subsequent tick at the
    same wall-clock cutoff doesn't re-send.
    """
    now = datetime(2026, 5, 8, 12, 0)
    await _seed(session, telegram_id=910, fire_at=now - timedelta(minutes=5))
    bot1 = _FakeBot()

    first = await tick_reminders(bot1, now=now)
    assert (first["sent"], first["retry"], first["failed"]) == (1, 0, 0)
    assert len(bot1.calls) == 1

    # Independent bot for the second tick — verifies that no row is
    # picked up again, regardless of the in-memory state of this test's
    # session (tick_reminders opens its own session_scope).
    bot2 = _FakeBot()
    second = await tick_reminders(bot2, now=now)
    assert (second["sent"], second["retry"], second["failed"]) == (0, 0, 0)
    assert bot2.calls == []


@pytest.mark.asyncio
async def test_tick_atomic_claim_skips_already_processing(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-I-5: a row in ``status='processing'`` must
    NOT be picked up by the SELECT (the ``status='pending'`` filter
    already excludes it) — and even if it were, the atomic claim
    ``UPDATE`` would be a no-op (rowcount=0) and the worker would
    skip it.

    Simulates a stuck row (worker killed between claim and state-flip):
    the next tick must leave it alone, never double-send.
    """
    now = datetime(2026, 5, 8, 12, 0)
    rem = await _seed(
        session,
        telegram_id=911,
        fire_at=now - timedelta(minutes=5),
        status="processing",
    )
    bot = _FakeBot()
    result = await tick_reminders(bot, now=now)
    assert (result["sent"], result["retry"], result["failed"]) == (0, 0, 0)
    assert bot.calls == []
    await session.refresh(rem)
    assert rem.status == "processing"
    assert rem.sent_at is None


@pytest.mark.asyncio
async def test_tick_processes_third_row_when_second_send_fails(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-I-5: per-row commit guarantees that a
    failure on row N doesn't roll back rows < N.

    Send for telegram_id=921 raises; rows for 920 and 922 must still
    be committed as ``sent`` (920) and ``pending`` (921, retry).
    """
    now = datetime(2026, 5, 8, 12, 0)
    rem_a = await _seed(session, telegram_id=920, fire_at=now - timedelta(minutes=10))
    rem_b = await _seed(session, telegram_id=921, fire_at=now - timedelta(minutes=5))
    rem_c = await _seed(session, telegram_id=922, fire_at=now - timedelta(minutes=1))

    class _PickyBot(_FakeBot):
        async def send_message(self, *, chat_id: int, text: str, **_: Any) -> None:
            if chat_id == 921:
                raise RuntimeError("flaky")
            self.calls.append((chat_id, text))

    bot = _PickyBot()
    result = await tick_reminders(bot, now=now)
    assert (result["sent"], result["retry"], result["failed"]) == (2, 1, 0)
    assert sorted(c[0] for c in bot.calls) == [920, 922]

    for r in (rem_a, rem_b, rem_c):
        await session.refresh(r)
    assert rem_a.status == "sent"
    assert rem_b.status == "pending"  # reverted from 'processing' for retry
    assert rem_b.attempts == 1
    assert rem_c.status == "sent"


# ── Downtime storm ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tick_cancels_stale_reminders_instead_of_sending(
    session: AsyncSession,
) -> None:
    """The first tick after a long outage must not spam obsolete reminders.

    The VPS is rented by the week and the bot migrates to a new server
    every ~7 days, so ticks routinely resume hours late. Reminders
    overdue by more than ``STALE_REMINDER_HOURS`` are cancelled in one
    UPDATE; anything fresher still fires normally.
    """
    now = datetime(2026, 5, 8, 12, 0)
    stale = await _seed(
        session,
        telegram_id=930,
        fire_at=now - timedelta(hours=STALE_REMINDER_HOURS, minutes=1),
    )
    fresh = await _seed(session, telegram_id=931, fire_at=now - timedelta(minutes=30))
    bot = _FakeBot()

    result = await tick_reminders(bot, now=now)

    assert [chat_id for chat_id, _ in bot.calls] == [931]
    assert result["sent"] == 1
    assert result["cancelled_stale"] == 1
    await session.refresh(stale)
    await session.refresh(fresh)
    assert stale.status == "cancelled"
    assert fresh.status == "sent"


# ── Orphaned dependents after a hard delete ──────────────────────────


@pytest.mark.asyncio
async def test_purge_deletes_reminders_so_no_ghost_fires(
    session: AsyncSession,
) -> None:
    """A purged task must take its reminders with it — no ghost sends.

    Self-hosted prod is SQLite, where the FK cascades don't exist
    (``PRAGMA foreign_keys`` is off, migrations 0007/0019 are
    PostgreSQL-only), so ``purge_trash`` used to leave the reminder
    behind. SQLite then reuses the freed rowid for the next task, the
    orphan re-joins that brand-new task and the user gets «⏰ Напоминаю»
    about something they never scheduled.
    """
    now = datetime(2026, 5, 8, 12, 0)
    rem = await _seed(
        session,
        telegram_id=940,
        title="Старая удалённая",
        fire_at=now - timedelta(minutes=30),
    )
    user_id, task_id = rem.user_id, rem.task_id
    task = (await session.exec(select(Task).where(Task.id == task_id))).first()
    assert task is not None
    task.deleted_at = now - timedelta(hours=TRASH_RETENTION_HOURS + 1)
    session.add(task)
    await session.commit()

    assert (await purge_trash(now=now))["tasks"] == 1
    assert list((await session.exec(select(Reminder))).all()) == []

    # Ловушка: rowid освободился → новая задача получает id удалённой.
    # Отдельная сессия — как в проде, чтобы не тащить в identity map
    # тестовой сессии удалённую задачу с тем же id.
    async with session_scope() as writer:
        new_task = Task(user_id=user_id, title="Новая невинная задача")
        writer.add(new_task)
        await writer.flush()
        assert new_task.id == task_id

    bot = _FakeBot()
    result = await tick_reminders(bot, now=now)

    assert bot.calls == []
    assert result["sent"] == 0
