"""Async database engine and session factory.

Tests call `init_engine()` with `sqlite+aiosqlite:///:memory:` and never
touch the production engine. Production calls `init_engine()` once during
FastAPI lifespan with the Postgres URL from settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

# Глобальные синглтоны: один процесс — один engine.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Initialise (or reset) the global async engine.

    Returns the freshly created engine. The previous engine, if any, is
    *not* disposed automatically — call `dispose_engine()` first if needed.
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url, echo=echo, future=True)
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
