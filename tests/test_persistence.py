"""Tests for Phase 2.2b persistence functions."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult
from app.bot.services import (
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
    get_user_categories,
    log_ai_run,
    persist_classification,
)
from app.db.models import AiRun, Category, Horizon, Note, Task, TaskEvent


@pytest.mark.asyncio
async def test_get_or_create_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=100)
    await session.commit()
    assert user.id is not None

    cat = await get_or_create_category(session, user.id, "Работа")
    await session.commit()
    assert cat.id is not None
    assert cat.name == "Работа"

    same = await get_or_create_category(session, user.id, "Работа")
    assert same.id == cat.id


@pytest.mark.asyncio
async def test_get_or_create_horizon(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=101)
    await session.commit()
    assert user.id is not None

    hor = await get_or_create_horizon(session, user.id, "today")
    await session.commit()
    assert hor.id is not None
    assert hor.slug == "today"
    assert hor.label == "Сегодня"

    same = await get_or_create_horizon(session, user.id, "today")
    assert same.id == hor.id


@pytest.mark.asyncio
async def test_get_user_categories(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=102)
    await session.commit()
    assert user.id is not None

    cats = await get_user_categories(session, user.id)
    assert cats == []

    await get_or_create_category(session, user.id, "Дом")
    await get_or_create_category(session, user.id, "Учёба")
    await session.commit()

    cats = await get_user_categories(session, user.id)
    assert sorted(cats) == ["Дом", "Учёба"]


@pytest.mark.asyncio
async def test_persist_task(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=103)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Покупки",
        horizon="today",
        priority="high",
        is_task=True,
        confidence=0.95,
        title="Купить хлеб",
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.title == "Купить хлеб"
    assert row.priority == "high"
    assert row.confidence == pytest.approx(0.95)

    tasks = (await session.exec(select(Task))).all()
    assert len(tasks) == 1

    events = (await session.exec(select(TaskEvent))).all()
    assert len(events) == 1
    assert events[0].kind == "created"

    cats = (await session.exec(select(Category))).all()
    assert len(cats) == 1
    assert cats[0].name == "Покупки"


@pytest.mark.asyncio
async def test_persist_note(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=104)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Идеи",
        horizon="someday",
        priority="low",
        is_task=False,
        confidence=0.8,
        title="Написать статью про Python",
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Note)
    assert row.title == "Написать статью про Python"

    notes = (await session.exec(select(Note))).all()
    assert len(notes) == 1

    events = (await session.exec(select(TaskEvent))).all()
    assert len(events) == 0


@pytest.mark.asyncio
async def test_log_ai_run(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=105)
    await session.commit()
    assert user.id is not None

    await log_ai_run(
        session,
        user_id=user.id,
        inbox_id=None,
        stage="classifier",
        model="llama-3.3-70b-versatile",
        key_index=1,
        latency_ms=450,
    )
    await session.commit()

    rows = (await session.exec(select(AiRun))).all()
    assert len(rows) == 1
    assert rows[0].stage == "classifier"
    assert rows[0].model == "llama-3.3-70b-versatile"
    assert rows[0].latency_ms == 450
    assert rows[0].key_index == 1


@pytest.mark.asyncio
async def test_persist_reuses_existing_category(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=106)
    await session.commit()
    assert user.id is not None

    cr1 = ClassifierResult(
        category_name="Работа",
        horizon="week",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title="Задача 1",
    )
    cr2 = ClassifierResult(
        category_name="Работа",
        horizon="tomorrow",
        priority="low",
        is_task=True,
        confidence=0.85,
        title="Задача 2",
    )
    await persist_classification(session, user_id=user.id, cr=cr1, due_at=None, inbox_id=None)
    await persist_classification(session, user_id=user.id, cr=cr2, due_at=None, inbox_id=None)
    await session.commit()

    cats = (await session.exec(select(Category))).all()
    assert len(cats) == 1

    tasks = (await session.exec(select(Task))).all()
    assert len(tasks) == 2

    horizons = (await session.exec(select(Horizon))).all()
    assert len(horizons) == 2
