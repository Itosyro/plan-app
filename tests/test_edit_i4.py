"""Tests for PR-I4: TaskEditSnapshot + Undo support."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    _execute_complete,
    _execute_delete,
    _execute_rename,
    _save_snapshot,
    _undo_keyboard,
    execute_edit,
)
from app.bot.routers.callbacks import _apply_undo, parse_edit_undo_callback
from app.bot.services import get_or_create_user, persist_classification
from app.db.models import Task, TaskEditSnapshot


def _cr(
    title: str,
    *,
    category: str = "Тест",
    horizon: str = "today",
    priority: str = "medium",
) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon=horizon,
        priority=priority,
        is_task=True,
        confidence=0.95,
        title=title,
    )


# ── _save_snapshot ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_snapshot_creates_row(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=700)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Snapshot task"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    snap_id = await _save_snapshot(row.id, user.id, "status", "open", "done")
    assert snap_id is not None

    result = await session.exec(
        select(TaskEditSnapshot).where(TaskEditSnapshot.id == snap_id),
    )
    snap = result.first()
    assert snap is not None
    assert snap.field == "status"
    assert snap.old_value == "open"
    assert snap.new_value == "done"
    assert snap.task_id == row.id
    assert snap.user_id == user.id


# ── _undo_keyboard ──────────────────────────────────────────────────


def test_undo_keyboard_structure() -> None:
    kb = _undo_keyboard(42)
    assert len(kb.inline_keyboard) == 1
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "Отменить"
    assert btn.callback_data == "edit:undo:42"


# ── parse_edit_undo_callback ─────────────────────────────────────────


def test_parse_edit_undo_callback_valid() -> None:
    assert parse_edit_undo_callback("edit:undo:123") == 123


def test_parse_edit_undo_callback_invalid() -> None:
    assert parse_edit_undo_callback("edit:undo:abc") is None
    assert parse_edit_undo_callback("edit:undo:") is None
    assert parse_edit_undo_callback("edit:resolve:complete:1") is None
    assert parse_edit_undo_callback("foo:undo:1") is None


# ── executor returns snapshot_id ──────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_complete_returns_snapshot(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=701)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Complete me"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    reply, snap_id = await _execute_complete(row.id, user.id)
    assert "Закрыл" in reply
    assert snap_id is not None


@pytest.mark.asyncio
async def test_execute_delete_returns_snapshot(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=702)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Delete me"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    reply, snap_id = await _execute_delete(row.id, user.id)
    assert "Удалил" in reply
    assert snap_id is not None


@pytest.mark.asyncio
async def test_execute_rename_returns_snapshot(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=703)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Old name"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="rename",
        task_query="Old name",
        new_title="New name",
        confidence=0.9,
    )
    reply, snap_id = await _execute_rename(row.id, user.id, intent)
    assert "Переименовал" in reply
    assert snap_id is not None


# ── execute_edit returns undo keyboard ────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_returns_undo_kb(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=704)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Undo test"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    intent = EditIntent(
        intent="complete",
        task_query="Undo test",
        confidence=0.9,
    )
    reply, kb = await execute_edit(intent, user.id)
    assert "Закрыл" in reply
    assert kb is not None
    assert kb.inline_keyboard[0][0].text == "Отменить"
    assert kb.inline_keyboard[0][0].callback_data.startswith("edit:undo:")


# ── _apply_undo ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_undo_status(session: AsyncSession) -> None:
    """Undo a complete action restores status to 'open'."""
    user, _ = await get_or_create_user(session, telegram_id=705)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Undo status"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    snap = TaskEditSnapshot(
        task_id=row.id, user_id=user.id, field="status", old_value="open", new_value="done"
    )
    reply = _apply_undo(row, snap)
    assert "активных" in reply
    assert row.status == "open"


@pytest.mark.asyncio
async def test_apply_undo_title(session: AsyncSession) -> None:
    """Undo a rename restores old title."""
    user, _ = await get_or_create_user(session, telegram_id=706)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Original"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    row.title = "Changed"
    await session.commit()

    snap = TaskEditSnapshot(
        task_id=row.id, user_id=user.id, field="title", old_value="Original", new_value="Changed"
    )
    reply = _apply_undo(row, snap)
    assert "переименование" in reply.lower()
    assert row.title == "Original"


@pytest.mark.asyncio
async def test_apply_undo_delete(session: AsyncSession) -> None:
    """Undo a delete clears deleted_at."""
    from app.shared.time import utcnow_naive

    user, _ = await get_or_create_user(session, telegram_id=707)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Deleted"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    row.deleted_at = utcnow_naive()
    await session.commit()

    snap = TaskEditSnapshot(
        task_id=row.id,
        user_id=user.id,
        field="deleted_at",
        old_value=None,
        new_value="soft_deleted",
    )
    reply = _apply_undo(row, snap)
    assert "удаление" in reply.lower()
    assert row.deleted_at is None


@pytest.mark.asyncio
async def test_apply_undo_priority(session: AsyncSession) -> None:
    """Undo a priority change restores old priority."""
    user, _ = await get_or_create_user(session, telegram_id=708)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Prio task"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    row.priority = "high"
    await session.commit()

    snap = TaskEditSnapshot(
        task_id=row.id,
        user_id=user.id,
        field="priority",
        old_value="medium",
        new_value="high",
    )
    reply = _apply_undo(row, snap)
    assert "приоритет" in reply.lower()
    assert row.priority == "medium"
