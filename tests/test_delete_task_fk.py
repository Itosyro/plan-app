"""Regression tests for FK ON DELETE policies (R-NEW-C-3 / R-NEW-I-7).

The default test fixtures do not enable SQLite's ``PRAGMA
foreign_keys = ON``, so any FK violation passes silently. These
tests use a dedicated engine with FK enforcement turned on to prove:

* ``delete_task`` soft-deletes the task (sets ``deleted_at``) while
  keeping dependent ``TaskEvent`` and ``Reminder`` rows intact.
* Physical deletion (``session.delete``) still cascades correctly via
  ``ondelete='CASCADE'``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import delete_task, get_or_create_user
from app.db.models import Reminder, Task, TaskEvent
from app.shared.time import utcnow_naive


@pytest_asyncio.fixture
async def fk_session() -> AsyncIterator[AsyncSession]:
    """A throwaway in-memory engine with FK enforcement on.

    A ``StaticPool`` keeps the in-memory DB alive across connections.
    Because the pool serves a single underlying connection for the
    whole test, executing ``PRAGMA foreign_keys = ON`` once at the
    start is enough — every subsequent operation reuses that connection.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        await conn.run_sync(SQLModel.metadata.create_all)

    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        # Belt-and-suspenders: re-issue the PRAGMA on this session's
        # connection in case the begin() above used a different one.
        await session.exec(text("PRAGMA foreign_keys = ON"))  # type: ignore[arg-type, call-overload]
        result = await session.exec(text("PRAGMA foreign_keys"))  # type: ignore[arg-type, call-overload]
        row = result.first()
        assert row is not None and row[0] == 1, "FK enforcement did not stick — fixture is broken"
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_task_with_event_and_reminder_succeeds(
    fk_session: AsyncSession,
) -> None:
    """``delete_task`` must not FK-violate when the task has events
    and pending reminders. ``ondelete='CASCADE'`` on
    ``task_events.task_id`` and ``reminders.task_id`` is what makes
    this possible. See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-3``.
    """
    user, _ = await get_or_create_user(fk_session, telegram_id=900)
    await fk_session.commit()
    assert user.id is not None

    task = Task(user_id=user.id, title="Сделать тест")
    fk_session.add(task)
    await fk_session.flush()
    assert task.id is not None

    # Pre-existing audit row from some earlier action.
    fk_session.add(TaskEvent(task_id=task.id, kind="created"))
    # Pending reminder for the task.
    fk_session.add(
        Reminder(
            user_id=user.id,
            task_id=task.id,
            fire_at=utcnow_naive(),
        )
    )
    await fk_session.commit()

    # Soft-delete: task stays in DB with deleted_at set.
    await delete_task(fk_session, task, user.id)
    await fk_session.commit()

    remaining_tasks = (await fk_session.exec(select(Task))).all()
    assert len(remaining_tasks) == 1
    assert remaining_tasks[0].deleted_at is not None

    # Dependents are untouched (still linked to the soft-deleted task).
    remaining_events = (await fk_session.exec(select(TaskEvent))).all()
    assert len(remaining_events) == 2  # "created" + "deleted"
    remaining_reminders = (await fk_session.exec(select(Reminder))).all()
    assert len(remaining_reminders) == 1

    # Physical delete cascades dependents (purge path).
    await fk_session.delete(remaining_tasks[0])
    await fk_session.commit()
    assert (await fk_session.exec(select(Task))).all() == []
    assert (await fk_session.exec(select(TaskEvent))).all() == []
    assert (await fk_session.exec(select(Reminder))).all() == []


@pytest.mark.asyncio
async def test_orphan_task_event_blocked_without_task(
    fk_session: AsyncSession,
) -> None:
    """Sanity: with FKs enforced, inserting a TaskEvent for a
    non-existent task must fail. Confirms FK enforcement is actually
    active in this fixture (otherwise the test above would be
    vacuous).
    """
    fk_session.add(TaskEvent(task_id=99999, kind="bogus"))
    with pytest.raises(Exception):  # noqa: B017 — sqlalchemy IntegrityError
        await fk_session.commit()
    await fk_session.rollback()
