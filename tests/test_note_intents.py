"""Tests for voice/text note management: rename / delete / set_category."""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    EDIT_INTENTS_ALL,
    _execute_rename_note,
    _execute_set_note_category,
    _note_delete_confirmation,
    execute_delete_note,
    execute_edit,
)
from app.bot.services import (
    find_category_by_name,
    find_note_by_query,
    get_or_create_user,
    persist_classification,
)
from app.db.models import Note


def _note_cr(title: str, category: str = "Идеи") -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon="someday",
        priority="low",
        is_task=False,  # note, not a task
        confidence=0.9,
        title=title,
    )


async def _make_note(session: AsyncSession, user_id: int, title: str) -> Note:
    row = await persist_classification(
        session, user_id=user_id, cr=_note_cr(title), due_at=None, inbox_id=None
    )
    assert isinstance(row, Note)
    await session.commit()
    return row


def test_note_intents_in_all() -> None:
    assert {"rename_note", "delete_note", "set_note_category"} <= EDIT_INTENTS_ALL


# ── rename_note ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_note(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=700)
    await session.commit()
    assert user.id is not None
    await _make_note(session, user.id, "Идея для подарка")

    intent = EditIntent(
        intent="rename_note",
        task_query="подарка",
        new_title="Подарок маме",
        confidence=0.9,
    )
    reply = await _execute_rename_note(user.id, intent)
    assert "Переименовал заметку" in reply and "Подарок маме" in reply
    assert await find_note_by_query(session, user.id, "Подарок маме") is not None


@pytest.mark.asyncio
async def test_rename_note_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=701)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="rename_note", task_query="нет такой", new_title="X", confidence=0.9)
    reply = await _execute_rename_note(user.id, intent)
    assert "Не нашёл заметку" in reply


@pytest.mark.asyncio
async def test_rename_note_no_title(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=702)
    await session.commit()
    assert user.id is not None
    await _make_note(session, user.id, "Заметка")

    intent = EditIntent(intent="rename_note", task_query="Заметка", confidence=0.9)
    reply = await _execute_rename_note(user.id, intent)
    assert "новое название" in reply.lower()


# ── set_note_category ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_note_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=710)
    await session.commit()
    assert user.id is not None
    await _make_note(session, user.id, "Список книг")

    intent = EditIntent(
        intent="set_note_category",
        task_query="книг",
        new_category="Хобби",
        confidence=0.9,
    )
    reply = await _execute_set_note_category(user.id, intent)
    assert "Перенёс заметку" in reply and "Хобби" in reply

    note = await find_note_by_query(session, user.id, "книг")
    cat = await find_category_by_name(session, user.id, "Хобби")
    assert note is not None and cat is not None
    await session.refresh(note)
    assert note.category_id == cat.id


@pytest.mark.asyncio
async def test_set_note_category_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=711)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(
        intent="set_note_category", task_query="призрак", new_category="X", confidence=0.9
    )
    reply = await _execute_set_note_category(user.id, intent)
    assert "Не нашёл заметку" in reply


# ── delete_note ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_note_confirmation_and_delete(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=720)
    await session.commit()
    assert user.id is not None
    note = await _make_note(session, user.id, "Черновик письма")
    assert note.id is not None

    intent = EditIntent(intent="delete_note", task_query="письма", confidence=0.9)
    prompt, kb = await _note_delete_confirmation(user.id, intent)
    assert "Удалить заметку" in prompt and kb is not None
    cb_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any(c is not None and c.startswith("edit:ndeldo:") for c in cb_values)
    assert any(c is not None and c.startswith("edit:ndelno:") for c in cb_values)

    reply = await execute_delete_note(user.id, note.id)
    assert "Удалил заметку" in reply
    # Soft-deleted → no longer found by query.
    assert await find_note_by_query(session, user.id, "письма") is None


@pytest.mark.asyncio
async def test_delete_note_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=721)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="delete_note", task_query="призрак", confidence=0.9)
    prompt, kb = await _note_delete_confirmation(user.id, intent)
    assert "Не нашёл заметку" in prompt and kb is None


# ── execute_edit routing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_routes_rename_note(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=730)
    await session.commit()
    assert user.id is not None
    await _make_note(session, user.id, "Старая заметка")

    intent = EditIntent(
        intent="rename_note",
        task_query="Старая",
        new_title="Новая заметка",
        confidence=0.95,
    )
    reply, kb = await execute_edit(intent, user.id)
    assert "Переименовал заметку" in reply and "Новая заметка" in reply
    assert kb is None
