"""Tests for Phase 3a view commands (/today, /week, /notes, /categories)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.routers.callbacks import horizon_list_keyboard
from app.bot.routers.commands import (
    HORIZON_PAGE_SIZE,
    _format_note_list,
    _format_task_list,
)
from app.bot.services import (
    get_all_notes,
    get_categories_with_counts,
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
    get_task_by_id,
    get_tasks_by_horizon,
    mark_task_done,
)
from app.db.models import Note, Task

# ── Service tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tasks_by_horizon_empty(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=100)
    await session.commit()
    assert user.id is not None
    tasks = await get_tasks_by_horizon(session, user.id, "today")
    assert tasks == []


@pytest.mark.asyncio
async def test_get_tasks_by_horizon_returns_matching(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=101)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Работа")
    hor_today = await get_or_create_horizon(session, user.id, "today")
    hor_week = await get_or_create_horizon(session, user.id, "week")

    t1 = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor_today.id,
        title="Утренняя пробежка",
        priority="high",
    )
    t2 = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor_week.id,
        title="Отчёт",
        priority="medium",
    )
    t3 = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor_today.id,
        title="Завтрак",
        priority="low",
        status="done",
    )
    session.add_all([t1, t2, t3])
    await session.commit()

    today_tasks = await get_tasks_by_horizon(session, user.id, "today")
    assert len(today_tasks) == 1
    assert today_tasks[0].title == "Утренняя пробежка"

    week_tasks = await get_tasks_by_horizon(session, user.id, "week")
    assert len(week_tasks) == 1
    assert week_tasks[0].title == "Отчёт"


@pytest.mark.asyncio
async def test_get_all_notes_empty(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=102)
    await session.commit()
    assert user.id is not None
    notes = await get_all_notes(session, user.id)
    assert notes == []


@pytest.mark.asyncio
async def test_get_all_notes_returns_recent(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=103)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Личное")
    for i in range(3):
        session.add(Note(user_id=user.id, category_id=cat.id, title=f"Заметка {i}"))
    await session.commit()

    notes = await get_all_notes(session, user.id)
    assert len(notes) == 3


@pytest.mark.asyncio
async def test_get_categories_with_counts(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=104)
    await session.commit()
    assert user.id is not None

    cat_work = await get_or_create_category(session, user.id, "Работа")
    cat_health = await get_or_create_category(session, user.id, "Здоровье")
    hor = await get_or_create_horizon(session, user.id, "today")

    session.add(
        Task(
            user_id=user.id,
            category_id=cat_work.id,
            horizon_id=hor.id,
            title="Совещание",
            priority="high",
        )
    )
    session.add(
        Task(
            user_id=user.id,
            category_id=cat_work.id,
            horizon_id=hor.id,
            title="Отчёт",
            priority="medium",
        )
    )
    session.add(
        Task(
            user_id=user.id,
            category_id=cat_health.id,
            horizon_id=hor.id,
            title="Пробежка",
            priority="low",
        )
    )
    await session.commit()

    pairs = await get_categories_with_counts(session, user.id)
    names_counts = {cat.name: count for cat, count in pairs}
    assert names_counts["Работа"] == 2
    assert names_counts["Здоровье"] == 1


@pytest.mark.asyncio
async def test_mark_task_done(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=105)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Дом")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Уборка",
        priority="medium",
    )
    session.add(task)
    await session.commit()

    updated = await mark_task_done(session, task, user.id)
    assert updated.status == "done"
    await session.commit()

    today = await get_tasks_by_horizon(session, user.id, "today")
    assert len(today) == 0


@pytest.mark.asyncio
async def test_get_task_by_id(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=106)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Работа")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Тест",
        priority="low",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None

    found = await get_task_by_id(session, user.id, task.id)
    assert found is not None
    assert found.title == "Тест"

    not_found = await get_task_by_id(session, user.id, 99999)
    assert not_found is None


# ── Formatter tests ──────────────────────────────────────────────────


def test_format_task_list_empty() -> None:
    result = _format_task_list([], "Сегодня", "UTC")
    assert "Пусто" in result
    assert "Сегодня" in result


def test_format_task_list_with_tasks() -> None:
    """C-2: ``due_at`` is naive UTC; rendered HH:MM is in *user_tz*.

    A task due at 12:30 UTC for a Moscow user shows as 15:30 local.
    """
    t1 = Task(
        id=1,
        user_id=1,
        title="Пробежка",
        priority="high",
        category_id=1,
        horizon_id=1,
    )
    t2 = Task(
        id=2,
        user_id=1,
        title="Обед",
        priority="low",
        category_id=1,
        horizon_id=1,
        # Naive UTC — the schema contract.
        due_at=datetime(2026, 5, 8, 12, 30),
    )
    result = _format_task_list([t1, t2], "Сегодня", "Europe/Moscow")
    assert "Сегодня" in result
    assert "Пробежка" in result
    assert "Обед" in result
    assert "15:30" in result  # 12:30 UTC → 15:30 MSK
    assert "12:30" not in result
    assert "Всего: 2" in result
    assert "🔴" in result
    assert "🟢" in result


def test_format_note_list_empty() -> None:
    result = _format_note_list([])
    assert "Пусто" in result


def test_format_note_list_with_notes() -> None:
    n1 = Note(id=1, user_id=1, title="Идея проекта", category_id=1)
    n2 = Note(id=2, user_id=1, title="Рецепт пирога", category_id=1)
    result = _format_note_list([n1, n2])
    assert "Идея проекта" in result
    assert "Рецепт пирога" in result
    assert "Всего: 2" in result


# ── R-NEW-I-6 regression: single-message horizon view ──────────────


def test_format_task_list_overflow_message_shown_when_paged() -> None:
    """When ``total_count > len(tasks)`` (i.e. more tasks than fit
    on the page), the formatter must surface the overflow line so
    the user knows *some* tasks are hidden — and the line includes
    the actual numbers and a hint to /search.

    Regression for ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-6``.
    """
    visible = [
        Task(
            id=i,
            user_id=1,
            title=f"Task {i}",
            priority="medium",
            category_id=1,
            horizon_id=1,
        )
        for i in range(1, 6)
    ]
    result = _format_task_list(visible, "Сегодня", "UTC", total_count=42)
    assert "Показано 5 из 42" in result
    assert "/search" in result
    # The literal "Всего: 5" line should be replaced by the
    # overflow message — never both.
    assert "Всего:" not in result


def test_format_task_list_no_overflow_when_total_equals_visible() -> None:
    visible = [
        Task(
            id=i,
            user_id=1,
            title=f"Task {i}",
            priority="medium",
            category_id=1,
            horizon_id=1,
        )
        for i in range(1, 4)
    ]
    result = _format_task_list(visible, "Сегодня", "UTC", total_count=3)
    assert "Показано" not in result
    assert "Всего: 3" in result


def test_horizon_list_keyboard_compact_layout() -> None:
    """One row per task, four buttons per row (✅ 🔄 🗑 🏷). The
    callback_data of each button is identical to the per-task
    keyboard (``task:done:<id>``, etc.), so existing handlers in
    ``app/bot/routers/callbacks.py`` work unchanged.

    Regression for R-NEW-I-6: the previous N+1 message blast is
    replaced by a single message with a compact keyboard.
    """
    indices = [(1, 100), (2, 101), (3, 102)]
    kb = horizon_list_keyboard(indices)
    assert len(kb.inline_keyboard) == 3
    for row in kb.inline_keyboard:
        assert len(row) == 4

    # First row: index 1, task_id 100.
    row0 = kb.inline_keyboard[0]
    assert row0[0].text == "1 ✅"
    assert row0[0].callback_data == "task:done:100"
    assert row0[1].callback_data == "task:pick_move:100"
    assert row0[2].callback_data == "task:delete:100"
    assert row0[3].callback_data == "task:pick_category:100"

    # Last row picks up the third task's id.
    last = kb.inline_keyboard[2]
    assert last[0].text == "3 ✅"
    assert last[0].callback_data == "task:done:102"


def test_horizon_page_size_fits_telegram_keyboard_limit() -> None:
    """``HORIZON_PAGE_SIZE`` × 4 buttons must fit Telegram's 100-button
    inline-keyboard limit. R-NEW-I-6: catches accidental future
    increases past the platform ceiling.
    """
    assert HORIZON_PAGE_SIZE > 0
    assert HORIZON_PAGE_SIZE * 4 <= 100
