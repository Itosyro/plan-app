"""Tests for Phase 3b/3 finish inline-button callback handlers."""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.routers.callbacks import (
    category_picker_keyboard,
    horizon_picker_keyboard,
    task_action_keyboard,
)
from app.bot.services import (
    delete_task,
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
    get_task_by_id,
    get_tasks_by_horizon,
    get_user_categories_full,
    mark_task_done,
    update_task_category,
    update_task_horizon,
)
from app.db.models import Task

# ── Keyboard builder tests ───────────────────────────────────────────


def test_task_action_keyboard_structure() -> None:
    kb = task_action_keyboard(42)
    assert len(kb.inline_keyboard) == 2
    row = kb.inline_keyboard[0]
    assert len(row) == 3
    assert row[0].text == "✅ Готово"
    assert row[0].callback_data == "task:done:42"
    assert row[1].text == "🔄 Перенести"
    assert row[1].callback_data == "task:pick_move:42"
    assert row[2].text == "🗑 Удалить"
    assert row[2].callback_data == "task:delete:42"
    second = kb.inline_keyboard[1]
    assert len(second) == 1
    assert second[0].text == "🏷 Категория"
    assert second[0].callback_data == "task:pick_category:42"


def test_horizon_picker_keyboard_structure() -> None:
    kb = horizon_picker_keyboard(7)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    data_values = [btn.callback_data for btn in buttons]
    assert "task:move:7:today" in data_values
    assert "task:move:7:tomorrow" in data_values
    assert "task:move:7:week" in data_values
    assert "task:move:7:month" in data_values
    assert "task:move:7:year" in data_values
    assert "task:move:7:someday" in data_values
    assert "task:cancel:7" in data_values


# ── Service-level tests for callback operations ──────────────────────


@pytest.mark.asyncio
async def test_mark_task_done_via_callback(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=200)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Работа")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Задача для кнопки",
        priority="high",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None

    updated = await mark_task_done(session, task, user.id)
    assert updated.status == "done"
    await session.commit()

    remaining = await get_tasks_by_horizon(session, user.id, "today")
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delete_task_via_callback(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=201)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Дом")
    hor = await get_or_create_horizon(session, user.id, "week")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Удалить меня",
        priority="low",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None
    task_id = task.id

    await delete_task(session, task, user.id)
    await session.commit()

    found = await get_task_by_id(session, user.id, task_id)
    assert found is None


@pytest.mark.asyncio
async def test_move_task_to_different_horizon(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=202)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Работа")
    hor_today = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor_today.id,
        title="Перенести на неделю",
        priority="medium",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None

    await update_task_horizon(session, task, "week", user.id)
    await session.commit()

    today_tasks = await get_tasks_by_horizon(session, user.id, "today")
    assert len(today_tasks) == 0

    week_tasks = await get_tasks_by_horizon(session, user.id, "week")
    assert len(week_tasks) == 1
    assert week_tasks[0].title == "Перенести на неделю"


def test_category_picker_keyboard_structure() -> None:
    from app.db.models import Category

    cats = [
        Category(id=10, user_id=1, name="Работа"),
        Category(id=11, user_id=1, name="Дом"),
        Category(id=12, user_id=1, name="Здоровье"),
    ]
    kb = category_picker_keyboard(99, cats)
    data_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "task:set_category:99:10" in data_values
    assert "task:set_category:99:11" in data_values
    assert "task:set_category:99:12" in data_values
    assert kb.inline_keyboard[-1][0].callback_data == "task:cancel:99"
    assert kb.inline_keyboard[-1][0].text == "↩ Назад"


@pytest.mark.asyncio
async def test_update_task_category_via_callback(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=205)
    await session.commit()
    assert user.id is not None

    cat_old = await get_or_create_category(session, user.id, "Старая")
    cat_new = await get_or_create_category(session, user.id, "Новая")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat_old.id,
        horizon_id=hor.id,
        title="Перекинуть категорию",
        priority="medium",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None
    assert cat_new.id is not None

    updated = await update_task_category(session, task, cat_new.id, user.id)
    await session.commit()
    assert updated.category_id == cat_new.id

    cats = await get_user_categories_full(session, user.id)
    assert {c.name for c in cats} == {"Старая", "Новая"}


@pytest.mark.asyncio
async def test_get_task_by_id_wrong_user(session: AsyncSession) -> None:
    user1, _ = await get_or_create_user(session, telegram_id=203)
    user2, _ = await get_or_create_user(session, telegram_id=204)
    await session.commit()
    assert user1.id is not None
    assert user2.id is not None

    cat = await get_or_create_category(session, user1.id, "Личное")
    hor = await get_or_create_horizon(session, user1.id, "today")
    task = Task(
        user_id=user1.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Чужая задача",
        priority="low",
    )
    session.add(task)
    await session.commit()
    assert task.id is not None

    found = await get_task_by_id(session, user2.id, task.id)
    assert found is None
