"""Tests for Phase 2.2b persistence functions."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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
    mark_task_done,
    mark_task_undone,
    persist_classification,
)
from app.db.base import get_sessionmaker
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
async def test_get_or_create_category_concurrent_safe(engine: None) -> None:
    """Regression for R-NEW-I-2: parallel ``get_or_create_category`` calls
    for the same ``(user_id, name)`` from different sessions must all
    return the same row, never propagate ``IntegrityError`` to the
    caller. Mirrors the multi-pipeline race that occurs when several
    webhook deliveries arrive for one user simultaneously.
    """
    sm = get_sessionmaker()
    async with sm() as setup:
        user, _ = await get_or_create_user(setup, telegram_id=300)
        await setup.commit()
        user_id = user.id
        assert user_id is not None

    async def one_pipeline() -> int | None:
        async with sm() as session:
            cat = await get_or_create_category(session, user_id, "Работа")
            await session.commit()
            return cat.id

    results = await asyncio.gather(*[one_pipeline() for _ in range(5)])
    assert len(set(results)) == 1, f"races produced different ids: {results}"
    assert results[0] is not None


@pytest.mark.asyncio
async def test_get_or_create_category_recovers_from_unique_conflict(
    engine: None,
) -> None:
    """Regression for R-NEW-I-2: when a concurrent transaction inserts
    the same row between our SELECT and our own INSERT, the SAVEPOINT
    must roll back our INSERT and we must re-SELECT the winning row
    instead of letting ``IntegrityError`` propagate.

    We simulate the stale-snapshot scenario by faking the first
    ``session.exec`` call to return an empty result, while a real row
    already exists in the database (committed by a separate session).
    """
    sm = get_sessionmaker()
    async with sm() as s:
        user, _ = await get_or_create_user(s, telegram_id=301)
        await s.commit()
        user_id = user.id
        assert user_id is not None

    async with sm() as winner:
        winner_cat = Category(user_id=user_id, name="Работа")
        winner.add(winner_cat)
        await winner.commit()
        winner_id = winner_cat.id
        assert winner_id is not None

    async with sm() as loser:
        real_exec = loser.exec
        calls = {"n": 0}

        class _FakeResult:
            def first(self) -> None:
                return None

            def all(self) -> list[Any]:
                return []

            def __iter__(self) -> Any:
                return iter(())

        async def fake_exec(stmt: Any, *args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                # Stale snapshot: pretend SELECT-before-INSERT saw nothing,
                # while the real DB already has the winner's row.
                return _FakeResult()
            return await real_exec(stmt, *args, **kwargs)  # type: ignore[no-any-return]

        loser.exec = fake_exec  # type: ignore[method-assign]

        cat = await get_or_create_category(loser, user_id, "Работа")
        assert cat.id == winner_id
        assert cat.name == "Работа"
        # The savepoint rolled back; the outer transaction is still
        # usable — we can issue further queries on the same session.
        result = await real_exec(
            select(Category).where(Category.user_id == user_id, Category.name == "Работа")
        )
        assert result.first() is not None


@pytest.mark.asyncio
async def test_get_or_create_horizon_concurrent_safe(engine: None) -> None:
    """Regression for R-NEW-I-2 (horizon flavour): parallel
    ``get_or_create_horizon`` calls for the same ``(user_id, slug)`` from
    different sessions must all return the same row.
    """
    sm = get_sessionmaker()
    async with sm() as setup:
        user, _ = await get_or_create_user(setup, telegram_id=302)
        await setup.commit()
        user_id = user.id
        assert user_id is not None

    async def one_pipeline() -> int | None:
        async with sm() as session:
            hor = await get_or_create_horizon(session, user_id, "today")
            await session.commit()
            return hor.id

    results = await asyncio.gather(*[one_pipeline() for _ in range(5)])
    assert len(set(results)) == 1, f"races produced different ids: {results}"
    assert results[0] is not None


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


# ── C-2 regression: due_at is normalised to naive UTC on persist ─────


@pytest.mark.asyncio
async def test_persist_classification_normalises_aware_due_to_naive_utc(
    session: AsyncSession,
) -> None:
    """C-2: dateparser returns tz-aware MSK; ``Task.due_at`` must be UTC.

    Pre-2026-05-09 the aware-MSK datetime was passed straight through to
    ``Task(...)``, where SQLAlchemy silently dropped the tzinfo. The
    column then held a naive value at MSK clock-time but our schema
    contract says naive == UTC, so any later ``now()`` comparison or
    JSON export would be off by 3 hours.
    """
    user, _ = await get_or_create_user(session, telegram_id=205)
    await session.commit()
    assert user.id is not None

    # Aware MSK 12:00 \u2192 must become naive UTC 09:00 in storage.
    msk = ZoneInfo("Europe/Moscow")
    aware_msk = datetime(2026, 5, 9, 12, 0, tzinfo=msk)

    cr = ClassifierResult(
        category_name="\u0420\u0430\u0431\u043e\u0442\u0430",
        horizon="today",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title="\u0421\u043e\u0432\u0435\u0449\u0430\u043d\u0438\u0435",
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=aware_msk,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.due_at is not None
    assert row.due_at.tzinfo is None  # naive
    assert row.due_at == datetime(2026, 5, 9, 9, 0)  # UTC


@pytest.mark.asyncio
async def test_persist_classification_naive_due_at_passes_through(
    session: AsyncSession,
) -> None:
    """C-2 companion: a naive value (already UTC by contract) is stored verbatim."""
    user, _ = await get_or_create_user(session, telegram_id=206)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Работа",
        horizon="today",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title="Задача",
    )
    naive_utc = datetime(2026, 5, 9, 9, 0)
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=naive_utc,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.due_at == naive_utc
    assert row.due_at.tzinfo is None


@pytest.mark.asyncio
async def test_persist_classification_none_due_at_stays_none(
    session: AsyncSession,
) -> None:
    """C-2 companion: ``due_at=None`` must not raise inside the normaliser."""
    user, _ = await get_or_create_user(session, telegram_id=207)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Работа",
        horizon="someday",
        priority="low",
        is_task=True,
        confidence=0.7,
        title="Без дедлайна",
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
    assert row.due_at is None


@pytest.mark.asyncio
async def test_persist_first_step_swap(session: AsyncSession) -> None:
    """``concretize_tasks=True`` + ``first_step`` → swap title with rewrite.

    The actionable rewrite becomes ``Task.title`` and the user's
    original abstract phrasing is preserved in ``Task.title_original``
    so the Mini-App can render the 🎯 badge + subtitle. The redundant
    "Шаг 1:" description prefix is dropped — the title now carries
    the first step itself.
    """
    user, _ = await get_or_create_user(session, telegram_id=910)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Учёба",
        horizon="someday",
        priority="medium",
        is_task=True,
        confidence=0.8,
        title="Разобраться с английским",
        first_step="Установить Duolingo и пройти один урок",
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
        concretize_tasks=True,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.title == "Установить Duolingo и пройти один урок"
    assert row.title_original == "Разобраться с английским"
    assert row.description is None


@pytest.mark.asyncio
async def test_persist_first_step_off_no_swap(session: AsyncSession) -> None:
    """``concretize_tasks=False`` → no swap, even if ``first_step`` set."""
    user, _ = await get_or_create_user(session, telegram_id=911)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Учёба",
        horizon="someday",
        priority="medium",
        is_task=True,
        confidence=0.8,
        title="Разобраться с английским",
        first_step="Установить Duolingo и пройти один урок",
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
        concretize_tasks=False,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.title == "Разобраться с английским"
    assert row.title_original is None


@pytest.mark.asyncio
async def test_persist_concretize_on_but_no_first_step(session: AsyncSession) -> None:
    """``concretize_tasks=True`` but classifier didn't propose a step → no swap."""
    user, _ = await get_or_create_user(session, telegram_id=912)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Покупки",
        horizon="today",
        priority="high",
        is_task=True,
        confidence=0.95,
        title="Купить хлеб",
        first_step=None,
    )
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
        concretize_tasks=True,
    )
    await session.commit()

    assert isinstance(row, Task)
    assert row.title == "Купить хлеб"
    assert row.title_original is None


@pytest.mark.asyncio
async def test_persist_subtasks_inherits_parent_fields(session: AsyncSession) -> None:
    """Classifier-proposed subtasks become child Tasks with inherited fields."""
    user, _ = await get_or_create_user(session, telegram_id=920)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Личное",
        horizon="week",
        priority="high",
        is_task=True,
        confidence=0.9,
        title="Организовать день рождения",
        subtasks=[
            "Составить список гостей",
            "Заказать торт",
            "Купить украшения",
        ],
    )
    parent = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(parent, Task)
    assert parent.parent_id is None

    children = (await session.exec(select(Task).where(Task.parent_id == parent.id))).all()
    assert len(children) == 3
    titles = sorted(c.title for c in children)
    assert titles == [
        "Заказать торт",
        "Купить украшения",
        "Составить список гостей",
    ]
    for c in children:
        assert c.user_id == parent.user_id
        assert c.category_id == parent.category_id
        assert c.horizon_id == parent.horizon_id
        assert c.priority == parent.priority


@pytest.mark.asyncio
async def test_persist_subtasks_caps_at_five(session: AsyncSession) -> None:
    """Runaway classifier output is truncated to MAX_SUBTASKS_PER_PARENT."""
    user, _ = await get_or_create_user(session, telegram_id=921)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Работа",
        horizon="week",
        priority="medium",
        is_task=True,
        confidence=0.7,
        title="Большой проект",
        subtasks=[f"Шаг {i}" for i in range(1, 11)],  # 10 items
    )
    parent = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(parent, Task)
    children = (await session.exec(select(Task).where(Task.parent_id == parent.id))).all()
    assert len(children) == 5


@pytest.mark.asyncio
async def test_persist_subtasks_dedup_and_skip_blank(session: AsyncSession) -> None:
    """Duplicate titles and blank strings are dropped before insert."""
    user, _ = await get_or_create_user(session, telegram_id=922)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Работа",
        horizon="today",
        priority="medium",
        is_task=True,
        confidence=0.8,
        title="Проект",
        subtasks=["Тест", "", "  ", "Тест", "Документация"],
    )
    parent = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(parent, Task)
    children = (await session.exec(select(Task).where(Task.parent_id == parent.id))).all()
    titles = sorted(c.title for c in children)
    assert titles == ["Документация", "Тест"]


@pytest.mark.asyncio
async def test_persist_no_subtasks_when_null(session: AsyncSession) -> None:
    """``subtasks=None`` means atomic task, no children inserted."""
    user, _ = await get_or_create_user(session, telegram_id=923)
    await session.commit()
    assert user.id is not None

    cr = ClassifierResult(
        category_name="Покупки",
        horizon="today",
        priority="low",
        is_task=True,
        confidence=0.9,
        title="Купить молоко",
        subtasks=None,
    )
    parent = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(parent, Task)
    children = (await session.exec(select(Task).where(Task.parent_id == parent.id))).all()
    assert children == []


async def _make_parent_with_children(
    session: AsyncSession, telegram_id: int, n_children: int
) -> tuple[Task, list[Task]]:
    """Helper: persist a parent task with ``n_children`` subtasks."""
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.commit()
    assert user.id is not None
    cr = ClassifierResult(
        category_name="Проект",
        horizon="week",
        priority="medium",
        is_task=True,
        confidence=0.9,
        title="Большой проект",
        subtasks=[f"Шаг {i}" for i in range(1, n_children + 1)],
    )
    parent = await persist_classification(
        session, user_id=user.id, cr=cr, due_at=None, inbox_id=None
    )
    await session.commit()
    assert isinstance(parent, Task)
    children = list((await session.exec(select(Task).where(Task.parent_id == parent.id))).all())
    return parent, children


@pytest.mark.asyncio
async def test_parent_auto_completes_when_last_child_done(session: AsyncSession) -> None:
    parent, children = await _make_parent_with_children(session, 930, 2)
    assert len(children) == 2

    # Completing the first child leaves the parent open.
    await mark_task_done(session, children[0], parent.user_id)
    await session.commit()
    refreshed_parent = await session.get(Task, parent.id)
    assert refreshed_parent is not None
    assert refreshed_parent.status != "done"

    # Completing the last child auto-completes the parent.
    await mark_task_done(session, children[1], parent.user_id)
    await session.commit()
    refreshed_parent = await session.get(Task, parent.id)
    assert refreshed_parent is not None
    assert refreshed_parent.status == "done"


@pytest.mark.asyncio
async def test_parent_reopens_when_child_reopened(session: AsyncSession) -> None:
    parent, children = await _make_parent_with_children(session, 931, 2)

    await mark_task_done(session, children[0], parent.user_id)
    await mark_task_done(session, children[1], parent.user_id)
    await session.commit()
    refreshed_parent = await session.get(Task, parent.id)
    assert refreshed_parent is not None and refreshed_parent.status == "done"

    # Reopening any child must reopen the auto-completed parent.
    await mark_task_undone(session, children[0], parent.user_id)
    await session.commit()
    refreshed_parent = await session.get(Task, parent.id)
    assert refreshed_parent is not None
    assert refreshed_parent.status == "new"


@pytest.mark.asyncio
async def test_completing_atomic_task_does_not_touch_parent(session: AsyncSession) -> None:
    """A top-level task (parent_id is None) completes without side effects."""
    user, _ = await get_or_create_user(session, telegram_id=932)
    await session.commit()
    assert user.id is not None
    cat = await get_or_create_category(session, user.id, "Покупки")
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(
        user_id=user.id,
        category_id=cat.id,
        horizon_id=hor.id,
        title="Купить хлеб",
        priority="medium",
    )
    session.add(task)
    await session.commit()

    updated = await mark_task_done(session, task, user.id)
    assert updated.status == "done"
    assert updated.parent_id is None


@pytest.mark.asyncio
async def test_mark_done_sets_and_clears_completed_at(session: AsyncSession) -> None:
    """completed_at is stamped on done, cleared on reopen (Phase 7e/C)."""
    user, _ = await get_or_create_user(session, telegram_id=940)
    await session.commit()
    assert user.id is not None
    hor = await get_or_create_horizon(session, user.id, "today")
    task = Task(user_id=user.id, horizon_id=hor.id, title="Задача", priority="medium")
    session.add(task)
    await session.commit()
    assert task.completed_at is None

    await mark_task_done(session, task, user.id)
    await session.commit()
    assert task.completed_at is not None

    await mark_task_undone(session, task, user.id)
    await session.commit()
    assert task.completed_at is None


@pytest.mark.asyncio
async def test_parent_cascade_sets_completed_at(session: AsyncSession) -> None:
    """Auto-completing the parent stamps its completed_at; reopen clears it."""
    parent, children = await _make_parent_with_children(session, 941, 2)

    await mark_task_done(session, children[0], parent.user_id)
    await mark_task_done(session, children[1], parent.user_id)
    await session.commit()
    refreshed = await session.get(Task, parent.id)
    assert refreshed is not None and refreshed.status == "done"
    assert refreshed.completed_at is not None

    await mark_task_undone(session, children[0], parent.user_id)
    await session.commit()
    refreshed = await session.get(Task, parent.id)
    assert refreshed is not None and refreshed.status == "new"
    assert refreshed.completed_at is None
