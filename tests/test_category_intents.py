"""Tests for voice/text category management: create / rename / delete."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    EDIT_INTENTS_ALL,
    _category_delete_confirmation,
    _execute_create_category,
    _execute_rename_category,
    execute_delete_category,
    execute_edit,
)
from app.bot.services import (
    find_category_by_name,
    get_or_create_category,
    get_or_create_user,
    persist_classification,
)
from app.db.models import Category, Task


def _cr(title: str, category: str) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon="today",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title=title,
    )


def test_category_intents_in_all() -> None:
    assert {"create_category", "rename_category", "delete_category"} <= EDIT_INTENTS_ALL


# ── create_category ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_category_new(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=600)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="create_category", new_category="Финансы", confidence=0.9)
    reply = await _execute_create_category(user.id, intent)
    assert "Создал" in reply and "Финансы" in reply

    found = await find_category_by_name(session, user.id, "финансы")
    assert found is not None


@pytest.mark.asyncio
async def test_create_category_already_exists(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=601)
    await session.commit()
    assert user.id is not None
    await get_or_create_category(session, user.id, "Работа")
    await session.commit()

    # Case-insensitive: "работа" should match the existing "Работа".
    intent = EditIntent(intent="create_category", new_category="работа", confidence=0.9)
    reply = await _execute_create_category(user.id, intent)
    assert "уже есть" in reply


@pytest.mark.asyncio
async def test_create_category_no_name(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=602)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="create_category", confidence=0.9)
    reply = await _execute_create_category(user.id, intent)
    assert "Не понял" in reply


# ── rename_category ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=610)
    await session.commit()
    assert user.id is not None
    await get_or_create_category(session, user.id, "Работа")
    await session.commit()

    intent = EditIntent(
        intent="rename_category",
        category_query="Работа",
        new_category="Дела",
        confidence=0.9,
    )
    reply = await _execute_rename_category(user.id, intent)
    assert "Переименовал" in reply and "Дела" in reply
    assert await find_category_by_name(session, user.id, "Дела") is not None
    assert await find_category_by_name(session, user.id, "Работа") is None


@pytest.mark.asyncio
async def test_rename_category_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=611)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(
        intent="rename_category",
        category_query="Нет такой",
        new_category="Что-то",
        confidence=0.9,
    )
    reply = await _execute_rename_category(user.id, intent)
    assert "Не нашёл" in reply


@pytest.mark.asyncio
async def test_rename_category_clash(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=612)
    await session.commit()
    assert user.id is not None
    await get_or_create_category(session, user.id, "Работа")
    await get_or_create_category(session, user.id, "Дом")
    await session.commit()

    intent = EditIntent(
        intent="rename_category",
        category_query="Работа",
        new_category="Дом",
        confidence=0.9,
    )
    reply = await _execute_rename_category(user.id, intent)
    assert "уже есть" in reply
    # Both categories untouched.
    assert await find_category_by_name(session, user.id, "Работа") is not None
    assert await find_category_by_name(session, user.id, "Дом") is not None


# ── delete_category ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_category_detaches_tasks(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=620)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session, user_id=user.id, cr=_cr("Оплатить счёт", "Финансы"), due_at=None, inbox_id=None
    )
    assert isinstance(row, Task)
    await session.commit()
    cat = await find_category_by_name(session, user.id, "Финансы")
    assert cat is not None and cat.id is not None

    reply = await execute_delete_category(user.id, cat.id)
    assert "Удалил категорию" in reply and "Финансы" in reply
    assert "1 задачу" in reply

    # Category gone; the task survives but is now uncategorised.
    assert await find_category_by_name(session, user.id, "Финансы") is None
    await session.refresh(row)
    assert row.category_id is None


@pytest.mark.asyncio
async def test_delete_category_confirmation_keyboard(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=621)
    await session.commit()
    assert user.id is not None
    await get_or_create_category(session, user.id, "Хобби")
    await session.commit()

    intent = EditIntent(intent="delete_category", category_query="Хобби", confidence=0.9)
    prompt, kb = await _category_delete_confirmation(user.id, intent)
    assert "Удалить категорию" in prompt
    assert kb is not None
    cb_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any(c is not None and c.startswith("edit:catdo:") for c in cb_values)
    assert any(c is not None and c.startswith("edit:catno:") for c in cb_values)


@pytest.mark.asyncio
async def test_delete_category_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=622)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="delete_category", category_query="Призрак", confidence=0.9)
    prompt, kb = await _category_delete_confirmation(user.id, intent)
    assert "Не нашёл" in prompt
    assert kb is None


# ── execute_edit routing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_routes_create_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=630)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="create_category", new_category="Путешествия", confidence=0.95)
    reply, kb = await execute_edit(intent, user.id)
    assert "Создал" in reply and "Путешествия" in reply
    assert kb is None

    rows = (
        await session.exec(
            select(Category).where(Category.user_id == user.id, Category.name == "Путешествия")
        )
    ).all()
    assert len(rows) == 1
