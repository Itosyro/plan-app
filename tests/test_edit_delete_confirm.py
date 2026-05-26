"""Tests for G3: two-step confirmation on LLM/free-text ``delete`` intent.

Excessive-Agency mitigation. A ``delete`` parsed from free user text never
soft-deletes immediately; instead :func:`execute_edit` surfaces a confirm/
cancel inline keyboard (``edit:deldo:<id>`` / ``edit:delno:<id>``). Only the
confirm callback (which calls :func:`_execute_delete`) soft-deletes. The
explicit 🗑 inline button (``task:delete:<id>``) is a deliberate tap and stays
immediate — that path is untouched here.
"""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import EditIntent
from app.bot.edit_executor import (
    _delete_confirmation,
    _execute_delete,
    execute_edit,
)
from app.bot.routers.callbacks import parse_edit_delete_confirm_callback
from app.bot.services import get_or_create_user, get_task_by_id, persist_classification
from app.db.models import Task

from .test_edit_intent import _cr

# ── callback_data parser ─────────────────────────────────────────────


def test_parse_edit_delete_confirm_callback_confirm() -> None:
    assert parse_edit_delete_confirm_callback("edit:deldo:42") == ("deldo", 42)


def test_parse_edit_delete_confirm_callback_cancel() -> None:
    assert parse_edit_delete_confirm_callback("edit:delno:7") == ("delno", 7)


def test_parse_edit_delete_confirm_callback_invalid() -> None:
    assert parse_edit_delete_confirm_callback("edit:deldo:abc") is None
    assert parse_edit_delete_confirm_callback("edit:undo:1") is None
    assert parse_edit_delete_confirm_callback("task:delete:1") is None
    assert parse_edit_delete_confirm_callback("edit:deldo") is None
    assert parse_edit_delete_confirm_callback("edit:deldo:1:2") is None


# ── delete intent → confirmation, no mutation ────────────────────────


@pytest.mark.asyncio
async def test_delete_intent_creates_confirmation_not_deletion(
    session: AsyncSession,
) -> None:
    """A resolved free-text ``delete`` returns a confirm keyboard and leaves
    ``deleted_at`` as None — the task must survive until the user confirms."""
    user, _ = await get_or_create_user(session, telegram_id=400)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Удалить через подтверждение"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    task_id = row.id
    await session.commit()

    intent = EditIntent(intent="delete", task_query="подтверждение", confidence=0.95)
    reply, kb = await execute_edit(intent, user.id)

    assert "Удалить" in reply and "?" in reply
    assert kb is not None
    callbacks = [btn.callback_data for r in kb.inline_keyboard for btn in r]
    assert f"edit:deldo:{task_id}" in callbacks
    assert f"edit:delno:{task_id}" in callbacks

    # Task is intact: still findable, deleted_at None.
    found = await get_task_by_id(session, user.id, task_id)
    assert found is not None
    assert found.deleted_at is None


@pytest.mark.asyncio
async def test_delete_confirmation_helper_does_not_mutate(
    session: AsyncSession,
) -> None:
    user, _ = await get_or_create_user(session, telegram_id=401)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Не трогать пока"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    task_id = row.id
    await session.commit()

    prompt, kb = await _delete_confirmation(task_id, user.id)
    assert prompt.startswith("Удалить «")
    assert kb is not None

    found = await get_task_by_id(session, user.id, task_id)
    assert found is not None
    assert found.deleted_at is None


# ── confirm callback path → soft-delete ──────────────────────────────


@pytest.mark.asyncio
async def test_confirm_soft_deletes(session: AsyncSession) -> None:
    """The confirm callback runs :func:`_execute_delete`, soft-deleting."""
    user, _ = await get_or_create_user(session, telegram_id=402)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Подтверждённое удаление"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    task_id = row.id
    await session.commit()

    # Mirror cb_edit_delete_confirm: parse "deldo" then _execute_delete.
    parsed = parse_edit_delete_confirm_callback(f"edit:deldo:{task_id}")
    assert parsed is not None
    action, parsed_id = parsed
    assert action == "deldo"

    reply, snap_id = await _execute_delete(parsed_id, user.id)
    assert "Удалил" in reply
    assert snap_id is not None

    # Now soft-deleted: get_task_by_id (deleted-filtering) returns None.
    found = await get_task_by_id(session, user.id, task_id)
    assert found is None


# ── cancel callback path → task intact ───────────────────────────────


@pytest.mark.asyncio
async def test_cancel_leaves_task_intact(session: AsyncSession) -> None:
    """The cancel callback never calls ``_execute_delete`` — task survives."""
    user, _ = await get_or_create_user(session, telegram_id=403)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Отменённое удаление"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    task_id = row.id
    await session.commit()

    parsed = parse_edit_delete_confirm_callback(f"edit:delno:{task_id}")
    assert parsed is not None
    action, _parsed_id = parsed
    assert action == "delno"
    # delno never triggers a delete — assert the task remains untouched.

    found = await get_task_by_id(session, user.id, task_id)
    assert found is not None
    assert found.deleted_at is None
