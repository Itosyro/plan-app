"""Tests for Phase 4a reminder scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult
from app.bot.services import (
    DEFAULT_REMINDER_OFFSETS,
    _select_reminder_offsets,
    _to_naive_utc,
    get_or_create_user,
    persist_classification,
    schedule_reminders,
)
from app.db.models import Reminder, Task


def _cr(
    *,
    horizon: str = "tomorrow",
    is_task: bool = True,
    reminder_offsets: list[int] | None = None,
    title: str = "Задача",
) -> ClassifierResult:
    return ClassifierResult(
        category_name="Работа",
        horizon=horizon,  # type: ignore[arg-type]
        priority="medium",
        is_task=is_task,
        confidence=0.9,
        title=title,
        reminder_offsets=reminder_offsets,
    )


# ── _select_reminder_offsets ────────────────────────────────────────


def test_select_offsets_uses_classifier_explicit() -> None:
    """When the classifier extracted explicit offsets, they win over defaults."""
    cr = _cr(horizon="week", reminder_offsets=[30, 5])
    offsets = _select_reminder_offsets(cr, {"same_day": [60], "multi_day": [1440]})
    assert offsets == [30, 5]


def test_select_offsets_same_day_for_today_tomorrow() -> None:
    cr = _cr(horizon="today")
    assert _select_reminder_offsets(cr, None) == DEFAULT_REMINDER_OFFSETS["same_day"]
    cr = _cr(horizon="tomorrow")
    assert _select_reminder_offsets(cr, None) == DEFAULT_REMINDER_OFFSETS["same_day"]


def test_select_offsets_multi_day_for_far_horizons() -> None:
    for horizon in ("week", "month", "year", "someday"):
        cr = _cr(horizon=horizon)
        assert _select_reminder_offsets(cr, None) == DEFAULT_REMINDER_OFFSETS["multi_day"]


def test_select_offsets_uses_user_defaults() -> None:
    cr = _cr(horizon="week")
    custom = {"same_day": [15], "multi_day": [180, 30]}
    assert _select_reminder_offsets(cr, custom) == [180, 30]


def test_select_offsets_drops_non_positive() -> None:
    cr = _cr(horizon="today", reminder_offsets=[0, -5, 30])
    assert _select_reminder_offsets(cr, None) == [30]


# ── schedule_reminders ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_reminders_creates_rows(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=200)
    await session.commit()
    assert user.id is not None

    task = Task(user_id=user.id, title="X", horizon_id=None, category_id=None)
    session.add(task)
    await session.flush()
    assert task.id is not None

    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    due_at = now + timedelta(hours=4)

    created = await schedule_reminders(
        session,
        user_id=user.id,
        task_id=task.id,
        due_at=due_at,
        offsets=[60, 15],
        now=now,
    )
    await session.commit()

    assert len(created) == 2
    rows = list((await session.exec(select(Reminder).order_by(Reminder.fire_at))).all())  # type: ignore[union-attr]
    assert len(rows) == 2
    assert all(r.status == "pending" for r in rows)
    assert all(r.attempts == 0 for r in rows)
    assert all(r.task_id == task.id for r in rows)
    naive_due = _to_naive_utc(due_at)
    assert rows[0].fire_at == naive_due - timedelta(minutes=60)
    assert rows[1].fire_at == naive_due - timedelta(minutes=15)


@pytest.mark.asyncio
async def test_schedule_reminders_skips_past_offsets(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=201)
    await session.commit()
    assert user.id is not None

    task = Task(user_id=user.id, title="X")
    session.add(task)
    await session.flush()
    assert task.id is not None

    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    # Due in 30 minutes — offset 60 minutes lands in the past, 15 minutes is fine.
    due_at = now + timedelta(minutes=30)

    created = await schedule_reminders(
        session,
        user_id=user.id,
        task_id=task.id,
        due_at=due_at,
        offsets=[60, 15],
        now=now,
    )
    assert len(created) == 1
    assert created[0].fire_at == _to_naive_utc(due_at) - timedelta(minutes=15)


@pytest.mark.asyncio
async def test_schedule_reminders_empty_offsets(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=202)
    await session.commit()
    assert user.id is not None

    task = Task(user_id=user.id, title="X")
    session.add(task)
    await session.flush()
    assert task.id is not None

    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    created = await schedule_reminders(
        session,
        user_id=user.id,
        task_id=task.id,
        due_at=now + timedelta(hours=1),
        offsets=[],
        now=now,
    )
    assert created == []
    assert (await session.exec(select(Reminder))).all() == []


# ── persist_classification → schedule reminders ─────────────────────


@pytest.mark.asyncio
async def test_persist_creates_reminders_for_due_at(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=203)
    await session.commit()
    assert user.id is not None

    due_at = datetime.now(UTC) + timedelta(hours=6)
    cr = _cr(horizon="today", title="Купить хлеб")
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=due_at,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Task)
    rows = (await session.exec(select(Reminder))).all()
    # Default same_day is [60, 15], both fit before due_at.
    assert len(rows) == 2
    assert all(r.task_id == row.id for r in rows)


@pytest.mark.asyncio
async def test_persist_skips_reminders_when_no_due_at(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=204)
    await session.commit()
    assert user.id is not None

    cr = _cr(horizon="today")
    await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert (await session.exec(select(Reminder))).all() == []


@pytest.mark.asyncio
async def test_persist_skips_reminders_for_notes(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=205)
    await session.commit()
    assert user.id is not None

    due_at = datetime.now(UTC) + timedelta(hours=6)
    cr = _cr(horizon="someday", is_task=False, title="Идея")
    await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=due_at,
        inbox_id=None,
    )
    await session.commit()

    assert (await session.exec(select(Reminder))).all() == []


@pytest.mark.asyncio
async def test_persist_uses_explicit_classifier_offsets(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=206)
    await session.commit()
    assert user.id is not None

    due_at = datetime.now(UTC) + timedelta(hours=6)
    cr = _cr(horizon="week", reminder_offsets=[120, 30])
    await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=due_at,
        inbox_id=None,
        # Custom user defaults shouldn't be used when classifier was explicit.
        default_reminder_offsets={"same_day": [10], "multi_day": [10000]},
    )
    await session.commit()

    rows = list((await session.exec(select(Reminder).order_by(Reminder.fire_at))).all())  # type: ignore[union-attr]
    assert len(rows) == 2
    naive_due = _to_naive_utc(due_at)
    assert (naive_due - rows[0].fire_at) == timedelta(minutes=120)
    assert (naive_due - rows[1].fire_at) == timedelta(minutes=30)


@pytest.mark.asyncio
async def test_persist_uses_user_default_offsets_for_multi_day(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=207)
    await session.commit()
    assert user.id is not None

    due_at = datetime.now(UTC) + timedelta(days=3)
    cr = _cr(horizon="week")
    await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=due_at,
        inbox_id=None,
        default_reminder_offsets={"same_day": [60], "multi_day": [1440, 60]},
    )
    await session.commit()

    rows = list((await session.exec(select(Reminder).order_by(Reminder.fire_at))).all())  # type: ignore[union-attr]
    assert len(rows) == 2
    naive_due = _to_naive_utc(due_at)
    assert (naive_due - rows[0].fire_at) == timedelta(minutes=1440)
    assert (naive_due - rows[1].fire_at) == timedelta(minutes=60)
