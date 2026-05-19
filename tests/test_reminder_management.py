"""Tests for PR-J reminder listing and cancellation."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import EditIntent
from app.bot.edit_executor import execute_edit
from app.bot.routers.commands import _format_reminder_list
from app.bot.services import (
    cancel_reminder,
    cancel_task_reminders,
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
    list_pending_reminders,
)
from app.db.models import Reminder, Task


async def _create_task_with_reminders(
    session: AsyncSession,
    *,
    telegram_id: int,
    title: str = "Созвон",
) -> tuple[int, int, list[int]]:
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.commit()
    assert user.id is not None
    category = await get_or_create_category(session, user.id, "Работа")
    horizon = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=category.id,
        horizon_id=horizon.id,
        title=title,
        priority="medium",
        due_at=datetime(2026, 5, 20, 12, 0),
    )
    session.add(task)
    await session.flush()
    assert task.id is not None
    reminders = [
        Reminder(user_id=user.id, task_id=task.id, fire_at=datetime(2026, 5, 20, 10, 0)),
        Reminder(user_id=user.id, task_id=task.id, fire_at=datetime(2026, 5, 20, 11, 45)),
    ]
    session.add_all(reminders)
    await session.commit()
    ids = [r.id for r in reminders]
    assert all(rid is not None for rid in ids)
    return user.id, task.id, [rid for rid in ids if rid is not None]


@pytest.mark.asyncio
async def test_list_pending_reminders_orders_and_filters(session: AsyncSession) -> None:
    user_id, _task_id, reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=810,
    )
    cancelled = await cancel_reminder(session, user_id, reminder_ids[1])
    assert cancelled is not None
    await session.commit()

    rows = await list_pending_reminders(session, user_id)

    assert len(rows) == 1
    reminder, task = rows[0]
    assert reminder.id == reminder_ids[0]
    assert task.title == "Созвон"


@pytest.mark.asyncio
async def test_list_pending_reminders_skips_overdue_pending(session: AsyncSession) -> None:
    user_id, _task_id, _reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=814,
    )

    rows = await list_pending_reminders(session, user_id, now=datetime(2026, 5, 20, 10, 30))

    assert len(rows) == 1
    reminder, task = rows[0]
    assert reminder.fire_at == datetime(2026, 5, 20, 11, 45)
    assert task.title == "Созвон"


@pytest.mark.asyncio
async def test_cancel_reminder_is_user_scoped(session: AsyncSession) -> None:
    _user_id, _task_id, reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=811,
    )

    result = await cancel_reminder(session, user_id=999999, reminder_id=reminder_ids[0])

    assert result is None
    row = (await session.exec(select(Reminder).where(Reminder.id == reminder_ids[0]))).one()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_cancel_task_reminders_cancels_all_pending_for_task(session: AsyncSession) -> None:
    user_id, task_id, _reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=812,
    )

    count = await cancel_task_reminders(session, user_id, task_id)
    await session.commit()

    rows = (await session.exec(select(Reminder).where(Reminder.task_id == task_id))).all()
    assert count == 2
    assert {row.status for row in rows} == {"cancelled"}


@pytest.mark.asyncio
async def test_execute_edit_cancel_reminder(session: AsyncSession) -> None:
    user_id, _task_id, _reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=813,
        title="Планёрка",
    )
    intent = EditIntent(intent="cancel_reminder", task_query="Планёрка", confidence=0.95)

    reply, kb = await execute_edit(intent, user_id)

    assert kb is None
    assert "Отменил напоминания" in reply
    rows = (await session.exec(select(Reminder).where(Reminder.user_id == user_id))).all()
    assert {row.status for row in rows} == {"cancelled"}


def test_format_reminder_list_plain_text() -> None:
    task = Task(user_id=1, title="Позвонить *Олегу_", priority="medium")
    reminder = Reminder(
        user_id=1,
        task_id=1,
        fire_at=datetime(2026, 5, 20, 11, 0) - timedelta(hours=3),
    )

    text = _format_reminder_list([(reminder, task)], "Europe/Moscow")

    assert "⏰ Напоминания" in text
    assert "11:00" in text
    assert "Позвонить *Олегу_" in text


def test_classifier_result_accepts_cancel_reminder_intent() -> None:
    intent = EditIntent(intent="cancel_reminder", task_query="созвон", confidence=0.95)

    assert intent.intent == "cancel_reminder"
