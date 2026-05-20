"""Tests for PR-J reminder listing and cancellation."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import EditIntent
from app.bot.edit_executor import execute_edit
from app.bot.reminder_view import format_reminder_list
from app.bot.routers.callbacks import (
    parse_reminder_cancel_callback,
    parse_reminder_page_callback,
    reminder_list_keyboard,
)
from app.bot.services import (
    cancel_reminder,
    cancel_task_reminders,
    count_pending_reminders,
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
    list_pending_reminders,
)
from app.db.models import Reminder, Task
from app.shared.time import plural_ru


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

    # Fixed clock before either seeded reminder so wall-clock drift in
    # the sandbox doesn't make both rows look overdue → filtered out.
    rows = await list_pending_reminders(
        session,
        user_id,
        now=datetime(2026, 5, 20, 9, 0),
    )

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

    cancelled = await cancel_task_reminders(session, user_id, task_id)
    await session.commit()

    rows = (await session.exec(select(Reminder).where(Reminder.task_id == task_id))).all()
    assert len(cancelled) == 2
    assert {row.status for row in rows} == {"cancelled"}
    # Returned objects still carry the original fire_at so callers can
    # show *when* the cancelled reminders were scheduled.
    assert [r.fire_at for r in cancelled] == sorted(r.fire_at for r in cancelled)


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
    # Plural form for 2 reminders → "напоминания" (few). Reply also
    # includes the local fire-times so the user can sanity-check.
    assert "Отменил 2 напоминания" in reply
    assert "Планёрка" in reply
    rows = (await session.exec(select(Reminder).where(Reminder.user_id == user_id))).all()
    assert {row.status for row in rows} == {"cancelled"}


def test_format_reminder_list_plain_text() -> None:
    task = Task(user_id=1, title="Позвонить *Олегу_", priority="medium")
    reminder = Reminder(
        user_id=1,
        task_id=1,
        fire_at=datetime(2026, 5, 20, 11, 0) - timedelta(hours=3),
    )

    text = format_reminder_list(
        [(reminder, task)],
        "Europe/Moscow",
        now=datetime(2026, 5, 20, 7, 0),
    )

    assert "⏰ Напоминания" in text
    assert "11:00" in text
    assert "Позвонить *Олегу_" in text


def test_format_reminder_list_marks_overdue() -> None:
    task = Task(user_id=1, title="Документы", priority="medium")
    overdue = Reminder(user_id=1, task_id=1, fire_at=datetime(2026, 5, 17, 6, 0))
    upcoming = Reminder(user_id=1, task_id=1, fire_at=datetime(2026, 5, 20, 9, 0))

    text = format_reminder_list(
        [(overdue, task), (upcoming, task)],
        "UTC",
        now=datetime(2026, 5, 19, 12, 0),
    )

    assert "❗" in text
    assert "(просрочено)" in text
    # Russian genitive month + day for the overdue row.
    assert "17 мая" in text


def test_format_reminder_list_paging_footer() -> None:
    task = Task(user_id=1, title="Звонок", priority="medium")
    rows = [
        (Reminder(user_id=1, task_id=1, fire_at=datetime(2026, 5, 20, 9, i)), task)
        for i in range(20)
    ]

    text = format_reminder_list(
        rows,
        "UTC",
        now=datetime(2026, 5, 20, 8, 0),
        total_count=42,
    )

    assert "Показано 20 из 42" in text
    assert "/reminders all" in text


def test_classifier_result_accepts_cancel_reminder_intent() -> None:
    intent = EditIntent(intent="cancel_reminder", task_query="созвон", confidence=0.95)

    assert intent.intent == "cancel_reminder"


# ── New PR-J UX tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_cancel_reminder_lists_local_times(
    session: AsyncSession,
) -> None:
    """Reply for cancel_reminder enumerates each cancelled fire-time."""
    user_id, _task_id, _reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=820,
        title="Зум",
    )
    intent = EditIntent(intent="cancel_reminder", task_query="Зум", confidence=0.95)

    reply, _ = await execute_edit(intent, user_id)

    # The two seeded reminders fire at 10:00 and 11:45 UTC; the default
    # user tz from get_or_create_user is "UTC" so the rendered times
    # match exactly.
    assert "10:00" in reply
    assert "11:45" in reply
    assert "20 мая" in reply
    # Plural form for 2 → "напоминания" (few).
    assert "Отменил 2 напоминания" in reply


@pytest.mark.asyncio
async def test_execute_edit_cancel_reminder_singular_copy(
    session: AsyncSession,
) -> None:
    """Singular form ("напоминание") used when only one reminder cancelled."""
    user_id, _task_id, reminder_ids = await _create_task_with_reminders(
        session,
        telegram_id=821,
        title="Брошь",
    )
    # Cancel one ahead of time so the executor only cancels the survivor.
    await cancel_reminder(session, user_id, reminder_ids[0])
    await session.commit()
    intent = EditIntent(intent="cancel_reminder", task_query="Брошь", confidence=0.95)

    reply, _ = await execute_edit(intent, user_id)

    assert "Отменил 1 напоминание для" in reply
    assert "11:45" in reply


@pytest.mark.asyncio
async def test_list_pending_reminders_include_overdue(session: AsyncSession) -> None:
    user_id, _task_id, _ = await _create_task_with_reminders(
        session,
        telegram_id=822,
    )

    fixed_now = datetime(2026, 5, 20, 23, 0)  # both reminders are in the past
    upcoming = await list_pending_reminders(session, user_id, now=fixed_now)
    all_rows = await list_pending_reminders(
        session,
        user_id,
        include_overdue=True,
        now=fixed_now,
    )

    assert upcoming == []
    assert len(all_rows) == 2


@pytest.mark.asyncio
async def test_list_pending_reminders_offset(session: AsyncSession) -> None:
    """offset + limit pages through pending rows in fire_at order."""
    user, _ = await get_or_create_user(session, telegram_id=823)
    await session.commit()
    assert user.id is not None
    cat = await get_or_create_category(session, user.id, "Работа")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Задача",
        priority="medium",
    )
    session.add(task)
    await session.flush()
    assert task.id is not None
    # 5 reminders 09:00..09:04 — all in the future relative to fixed_now.
    for minute in range(5):
        session.add(
            Reminder(
                user_id=user.id,
                task_id=task.id,
                fire_at=datetime(2026, 6, 1, 9, minute),
            )
        )
    await session.commit()
    fixed_now = datetime(2026, 6, 1, 8, 0)

    page_one = await list_pending_reminders(
        session,
        user.id,
        limit=2,
        offset=0,
        now=fixed_now,
    )
    page_two = await list_pending_reminders(
        session,
        user.id,
        limit=2,
        offset=2,
        now=fixed_now,
    )

    assert [r.fire_at.minute for r, _ in page_one] == [0, 1]
    assert [r.fire_at.minute for r, _ in page_two] == [2, 3]


@pytest.mark.asyncio
async def test_count_pending_reminders_respects_include_overdue(
    session: AsyncSession,
) -> None:
    user_id, _task_id, _ = await _create_task_with_reminders(
        session,
        telegram_id=824,
    )

    fixed_now = datetime(2026, 5, 20, 23, 0)
    upcoming = await count_pending_reminders(session, user_id, now=fixed_now)
    everything = await count_pending_reminders(
        session,
        user_id,
        include_overdue=True,
        now=fixed_now,
    )

    assert upcoming == 0
    assert everything == 2


def test_plural_ru_handles_russian_forms() -> None:
    forms = ("напоминание", "напоминания", "напоминаний")
    assert plural_ru(1, forms) == "напоминание"
    assert plural_ru(2, forms) == "напоминания"
    assert plural_ru(4, forms) == "напоминания"
    assert plural_ru(5, forms) == "напоминаний"
    assert plural_ru(11, forms) == "напоминаний"
    assert plural_ru(21, forms) == "напоминание"
    assert plural_ru(22, forms) == "напоминания"
    assert plural_ru(112, forms) == "напоминаний"


def test_parse_reminder_page_callback_validates_input() -> None:
    assert parse_reminder_page_callback("rem:page:20") == 20
    assert parse_reminder_page_callback("rem:page:0") is None  # offset must be > 0
    assert parse_reminder_page_callback("rem:page:-5") is None
    assert parse_reminder_page_callback("rem:page:abc") is None
    assert parse_reminder_page_callback("rem:page:99999") is None
    assert parse_reminder_page_callback("rem:cancel:1") is None
    assert parse_reminder_page_callback("rem:page:") is None


def test_reminder_list_keyboard_appends_next_button() -> None:
    kb = reminder_list_keyboard([(1, 10), (2, 11)], next_offset=20)

    # 2 cancel rows + 1 "next page" row.
    assert len(kb.inline_keyboard) == 3
    last_btn = kb.inline_keyboard[-1][0]
    assert last_btn.callback_data == "rem:page:20"
    assert "Ещё" in last_btn.text


def test_reminder_list_keyboard_without_next_offset() -> None:
    kb = reminder_list_keyboard([(1, 10)])
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == "rem:cancel:10"


def test_parse_reminder_cancel_callback_still_works() -> None:
    # Sanity: existing PR-J callback parser unaffected by new page parser.
    assert parse_reminder_cancel_callback("rem:cancel:42") == 42
