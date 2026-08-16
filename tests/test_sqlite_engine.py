"""SQLite-specific engine tuning (`app.db.base._tune_sqlite`).

Production is self-hosted on a plain SQLite file, so two SQLite-only
defects bite there and nowhere else: the built-in ASCII-only ``lower()``
(breaks every case-insensitive Cyrillic search) and the default
``journal_mode=DELETE`` + short busy timeout (three concurrent writers
trip over ``database is locked``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, or_, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import (
    find_task_by_query,
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
)
from app.db.base import dispose_engine, init_engine
from app.db.models import Task


@pytest.mark.asyncio
async def test_cyrillic_search_is_case_insensitive(session: AsyncSession) -> None:
    """Uppercase Cyrillic titles must be findable by a lowercase query.

    Without the Unicode ``lower()`` override SQLite leaves ``Купить``
    untouched, so both the voice-edit path (``.ilike`` → ``lower(a) LIKE
    lower(b)``) and the Mini App path (explicit ``func.lower``) miss it.
    """
    user, _ = await get_or_create_user(session, telegram_id=910)
    await session.commit()
    assert user.id is not None
    cat = await get_or_create_category(session, user.id, "Тесты")
    hor = await get_or_create_horizon(session, user.id, "today")
    session.add(
        Task(
            user_id=user.id,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Купить молоко",
            priority="medium",
        )
    )
    await session.commit()

    # 1. Real bot path: «отметь Купить молоко выполненным» arrives lowercased.
    found = await find_task_by_query(session, user.id, "купить молоко")
    assert found is not None
    assert found.title == "Купить молоко"

    # 2. Mini App path (app/api/routers/tasks.py) — same query, spelled out.
    pattern = "%купить%"
    result = await session.exec(
        select(Task).where(
            Task.user_id == user.id,
            or_(
                func.lower(Task.title).like(pattern, escape="\\"),
                func.lower(Task.description).like(pattern, escape="\\"),
            ),
        )
    )
    assert [t.title for t in result.all()] == ["Купить молоко"]


@pytest.mark.asyncio
async def test_file_engine_uses_wal_and_memory_engine_still_works(tmp_path: Path) -> None:
    """A file-backed SQLite engine runs in WAL; ``:memory:`` stays usable."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'plan.db').as_posix()}"
    engine = init_engine(db_url)
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
            assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000
    finally:
        await dispose_engine()

    # ``:memory:`` has no journal file — WAL is a no-op there and must not
    # blow up engine creation (the whole test suite depends on it).
    engine = init_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "memory"
            assert (await conn.execute(text("SELECT lower('Ж')"))).scalar() == "ж"
    finally:
        await dispose_engine()
