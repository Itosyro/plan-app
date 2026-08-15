"""Async database engine and session factory.

Tests call `init_engine()` with `sqlite+aiosqlite:///:memory:` and never
touch the production engine. Production calls `init_engine()` once during
FastAPI lifespan with the Postgres URL from settings.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from app.shared.logging import get_logger

logger = get_logger(__name__)

# Глобальные синглтоны: один процесс — один engine.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _to_async_url(url: str) -> str:
    """Force an async driver onto bare ``postgresql://`` / ``sqlite:///`` URLs.

    Neon (and most managed PG providers) hands out plain ``postgresql://``
    strings, often with libpq-style ``?sslmode=require``. SQLAlchemy's async
    engine refuses those without an async driver suffix. We prefer ``+psycopg``
    (psycopg v3) over ``+asyncpg`` here because psycopg accepts ``sslmode``
    natively, while asyncpg rejects it as an unknown kwarg.
    """
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite:///") and "+" not in url.split("://", 1)[0]:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


# Что sqlite3 может передать в UDF и принять обратно.
_SqliteValue = str | bytes | int | float | None


def _sqlite_lower(value: _SqliteValue) -> _SqliteValue:
    """Unicode-aware ``lower()``: NULL and non-text values pass through."""
    return value.lower() if isinstance(value, str) else value


def _tune_sqlite(engine: AsyncEngine) -> None:
    """Per-connection SQLite fixes: Unicode ``lower()``, WAL, busy timeout.

    SQLite's built-in ``lower()`` folds ASCII only, so ``lower('Купить')`` is a
    no-op and every case-insensitive search misses Cyrillic. Overriding it fixes
    both ``func.lower()`` (Mini App ``?q=``) and ``.ilike()`` (voice edits) —
    SQLAlchemy compiles ilike on SQLite to ``lower(a) LIKE lower(b)``.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: object, _record: object) -> None:
        # aiosqlite отдаёт адаптер, а не голый sqlite3.Connection, но
        # create_function / cursor он прокидывает насквозь.
        conn = cast(sqlite3.Connection, dbapi_connection)
        conn.create_function("lower", 1, _sqlite_lower, deterministic=True)
        cursor = conn.cursor()
        try:
            # WAL + таймаут: три писателя (API, пайплайн, 60-секундный шедулер)
            # иначе ловят "database is locked". У ``:memory:`` журнала нет —
            # PRAGMA вернёт "memory", и это не ошибка.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error as exc:
            logger.warning("db.sqlite.pragma_failed", error=str(exc))
        finally:
            cursor.close()


def init_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Initialise (or reset) the global async engine.

    Bare ``postgresql://`` / ``sqlite:///`` URLs are normalised to the async
    driver flavour. Returns the freshly created engine. The previous engine,
    if any, is *not* disposed automatically — call ``dispose_engine()``
    first if needed.
    """
    global _engine, _sessionmaker
    async_url = _to_async_url(database_url)
    # ``pool_pre_ping``: managed Postgres (Render free tier / Neon) cuts idle
    # server-side connections, and the free-dyno keep-alive means the engine
    # often holds connections across long idle gaps. Without a pre-ping the
    # first query after such a gap throws a stale-connection error (the same
    # family as the ``SSL connection has been closed unexpectedly`` that the
    # alembic startCommand retry papers over). ``pool_recycle`` proactively
    # discards connections older than 30 min so we rarely hand out a dead one.
    # SQLite (tests / local) ignores both — it has no real pool.
    is_sqlite = async_url.startswith("sqlite")
    engine_kwargs: dict[str, object] = {"echo": echo, "future": True}
    if not is_sqlite:
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 1800
    _engine = create_async_engine(async_url, **engine_kwargs)
    if is_sqlite:
        _tune_sqlite(_engine)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Return the configured engine."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised. Call init_engine() first.")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the async sessionmaker."""
    if _sessionmaker is None:
        raise RuntimeError("Database engine not initialised. Call init_engine() first.")
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session and commit on exit (rollback on exception)."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine and clear the singletons."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
