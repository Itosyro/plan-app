"""Tests for PR-I3: LAST_TASK anaphora, PENDING_EDITS, list_completed_today, multi-intent."""

from __future__ import annotations

import time

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    EDIT_INTENTS_ALL,
    LAST_TASK,
    PENDING_EDITS,
    _execute_list_completed_today,
    execute_edit,
    pop_last_task,
    pop_pending_edit,
    store_pending_edit,
    touch_last_task,
)
from app.bot.services import (
    get_or_create_user,
    mark_task_done,
    persist_classification,
)
from app.db.models import Task


def _cr(
    title: str = "Тест",
    category: str = "Дела",
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


# ── LAST_TASK helpers ────────────────────────────────────────────────


def test_touch_and_pop_last_task() -> None:
    LAST_TASK.clear()
    touch_last_task(999, 42)
    assert pop_last_task(999) == 42


def test_pop_last_task_expired() -> None:
    LAST_TASK.clear()
    LAST_TASK[999] = (42, time.monotonic() - 61)
    assert pop_last_task(999) is None


def test_pop_last_task_missing() -> None:
    LAST_TASK.clear()
    assert pop_last_task(123) is None


# ── PENDING_EDITS helpers ────────────────────────────────────────────


def test_store_and_pop_pending_edit() -> None:
    PENDING_EDITS.clear()
    intent = EditIntent(intent="rename", task_query="тест", new_title="Новое", confidence=0.9)
    store_pending_edit(999, intent)
    result = pop_pending_edit(999)
    assert result is not None
    assert result.intent == "rename"
    assert result.new_title == "Новое"
    # Second pop returns None (consumed).
    assert pop_pending_edit(999) is None


def test_pop_pending_edit_expired() -> None:
    PENDING_EDITS.clear()
    intent = EditIntent(intent="rename", task_query="тест", confidence=0.9)
    PENDING_EDITS[999] = (intent, time.monotonic() - 61)
    assert pop_pending_edit(999) is None


# ── LAST_TASK anaphora in execute_edit ───────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_anaphora(session: AsyncSession) -> None:
    """Empty task_query uses LAST_TASK to resolve the target task."""
    LAST_TASK.clear()
    user, _ = await get_or_create_user(session, telegram_id=600)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Задача для анафоры"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    touch_last_task(user.id, row.id)

    intent = EditIntent(intent="complete", task_query="", confidence=0.85)
    reply, kb = await execute_edit(intent, user.id)
    assert "Закрыл" in reply
    # PR-I4: undo keyboard now returned after successful edit.
    assert kb is not None


@pytest.mark.asyncio
async def test_execute_edit_anaphora_no_last_task(session: AsyncSession) -> None:
    """Empty task_query without LAST_TASK returns a helpful error."""
    LAST_TASK.clear()
    user, _ = await get_or_create_user(session, telegram_id=601)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="complete", task_query="", confidence=0.85)
    reply, _kb = await execute_edit(intent, user.id)
    assert "Уточни" in reply


# ── Multi-match stores PENDING_EDITS ─────────────────────────────────


@pytest.mark.asyncio
async def test_multi_match_stores_pending_edit(session: AsyncSession) -> None:
    """When >1 task matches, the intent is stored in PENDING_EDITS."""
    PENDING_EDITS.clear()
    user, _ = await get_or_create_user(session, telegram_id=602)
    await session.commit()
    assert user.id is not None

    await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Утренняя пробежка"),
        due_at=None,
        inbox_id=None,
    )
    await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Вечерняя пробежка"),
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    intent = EditIntent(
        intent="set_priority",
        task_query="пробежка",
        new_priority="high",
        confidence=0.9,
    )
    reply, kb = await execute_edit(intent, user.id)
    assert "Нашёл несколько" in reply
    assert kb is not None
    # Verify intent was stored.
    stored = pop_pending_edit(user.id)
    assert stored is not None
    assert stored.intent == "set_priority"
    assert stored.new_priority == "high"


# ── list_completed_today ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_completed_today_empty(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=603)
    await session.commit()
    assert user.id is not None

    reply, kb = await _execute_list_completed_today(user.id)
    assert "ничего не завершено" in reply
    assert kb is None


@pytest.mark.asyncio
async def test_list_completed_today_with_tasks(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=604)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Закрытая задача"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    await session.commit()

    await mark_task_done(session, row, user.id)
    await session.commit()

    reply, kb = await _execute_list_completed_today(user.id)
    assert "Закрытая задача" in reply
    assert "1" in reply
    assert kb is None


# ── list_done via execute_edit ───────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_list_done(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=605)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="list_done", confidence=0.95)
    reply, _kb = await execute_edit(intent, user.id)
    assert "ничего не завершено" in reply


# ── EDIT_INTENTS_ALL includes list_done ──────────────────────────────


def test_edit_intents_all_includes_list_done() -> None:
    assert "list_done" in EDIT_INTENTS_ALL
