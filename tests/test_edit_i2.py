"""Tests for PR-I2: rename, set_due, set_priority, set_category, reorder_time executors."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    EDIT_INTENTS_ALL,
    EDIT_INTENTS_I2,
    _execute_rename,
    _execute_reorder_time,
    _execute_set_category,
    _execute_set_due,
    _execute_set_priority,
    execute_edit,
)
from app.bot.services import (
    get_or_create_user,
    persist_classification,
    update_task_due_at,
    update_task_priority,
    update_task_title,
)
from app.db.models import Task


def _cr(
    title: str = "Тестовая задача",
    category: str = "Покупки",
    horizon: str = "today",
) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon=horizon,
        priority="medium",
        is_task=True,
        confidence=0.9,
        title=title,
    )


# ── EDIT_INTENTS sets ─────────────────────────────────────────────────


def test_edit_intents_i2_set() -> None:
    assert "rename" in EDIT_INTENTS_I2
    assert "set_due" in EDIT_INTENTS_I2
    assert "set_priority" in EDIT_INTENTS_I2
    assert "set_category" in EDIT_INTENTS_I2
    assert "reorder_time" in EDIT_INTENTS_I2


def test_edit_intents_all_superset() -> None:
    assert "complete" in EDIT_INTENTS_ALL
    assert "rename" in EDIT_INTENTS_ALL
    assert len(EDIT_INTENTS_ALL) == 9


# ── Service functions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_task_title(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=400)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Старое имя"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    await update_task_title(session, row, "Новое имя", user.id)
    await session.commit()
    assert row.title == "Новое имя"


@pytest.mark.asyncio
async def test_update_task_priority(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=401)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    await session.commit()

    await update_task_priority(session, row, "high", user.id)
    await session.commit()
    assert row.priority == "high"


@pytest.mark.asyncio
async def test_update_task_due_at(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=402)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    await session.commit()

    new_due = datetime(2026, 5, 15, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    await update_task_due_at(session, row, new_due, user.id)
    await session.commit()
    assert row.due_at == new_due


# ── Executors ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_rename(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=410)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Старое название"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="rename",
        task_query="Старое название",
        new_title="Новое название",
        confidence=0.9,
    )
    reply = await _execute_rename(row.id, user.id, intent)
    assert "Переименовал" in reply
    assert "Новое название" in reply


@pytest.mark.asyncio
async def test_execute_rename_no_title(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=411)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(intent="rename", task_query="Задача", confidence=0.9)
    reply = await _execute_rename(row.id, user.id, intent)
    assert "Не понял" in reply


@pytest.mark.asyncio
async def test_execute_set_due(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=412)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Отчёт"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="set_due",
        task_query="Отчёт",
        new_due_raw="завтра в 10",
        confidence=0.9,
    )
    reply = await _execute_set_due(row.id, user.id, intent)
    assert "дедлайн" in reply or "Поставил" in reply


@pytest.mark.asyncio
async def test_execute_set_due_no_raw(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=413)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(intent="set_due", task_query="Задача", confidence=0.9)
    reply = await _execute_set_due(row.id, user.id, intent)
    assert "Не понял" in reply


@pytest.mark.asyncio
async def test_execute_set_priority(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=414)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="set_priority",
        task_query="Задача",
        new_priority="high",
        confidence=0.9,
    )
    reply = await _execute_set_priority(row.id, user.id, intent)
    assert "Приоритет" in reply
    assert "высокий" in reply


@pytest.mark.asyncio
async def test_execute_set_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=415)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Задача"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="set_category",
        task_query="Задача",
        new_category="Работа",
        confidence=0.9,
    )
    reply = await _execute_set_category(row.id, user.id, intent)
    assert "категорию" in reply
    assert "Работа" in reply


@pytest.mark.asyncio
async def test_execute_reorder_time(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=416)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Встреча"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="reorder_time",
        task_query="Встреча",
        new_due_raw="в 14:00",
        confidence=0.9,
    )
    reply = await _execute_reorder_time(row.id, user.id, intent)
    assert "Перенёс" in reply


# ── execute_edit dispatch for I2 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_rename_dispatch(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=420)
    await session.commit()
    assert user.id is not None

    await persist_classification(
        session, user_id=user.id, cr=_cr("Моя задача"), due_at=None, inbox_id=None
    )
    await session.commit()

    intent = EditIntent(
        intent="rename",
        task_query="Моя задача",
        new_title="Обновлённая задача",
        confidence=0.9,
    )
    reply, kb = await execute_edit(intent, user.id)
    assert "Переименовал" in reply
    assert kb is None
