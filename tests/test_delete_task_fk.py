"""Regression tests for FK ON DELETE policies (R-NEW-C-3 / R-NEW-I-7).

The default test fixtures do not enable SQLite's ``PRAGMA
foreign_keys = ON``, so any FK violation passes silently. These
tests use a dedicated engine with FK enforcement turned on to prove:

* ``delete_task`` works when the task has dependent ``TaskEvent`` and
  ``Reminder`` rows. Before the model change to
  ``ondelete='CASCADE'`` (and the corresponding alembic migration
  ``0007``) this would FK-violate on Postgres — and now would FK-violate
  on SQLite too with FKs enforced. The tests confirm the new behaviour.
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

    # The big call. Must not raise on Postgres / FK-enforcing SQLite.
    await delete_task(fk_session, task, user.id)
    await fk_session.commit()

    # The CASCADE deletes both dependents.
    remaining_tasks = (await fk_session.exec(select(Task))).all()
    assert remaining_tasks == []
    remaining_events = (await fk_session.exec(select(TaskEvent))).all()
    assert remaining_events == []
    remaining_reminders = (await fk_session.exec(select(Reminder))).all()
    assert remaining_reminders == []


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
