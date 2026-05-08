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


def init_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Initialise (or reset) the global async engine.

    Bare ``postgresql://`` / ``sqlite:///`` URLs are normalised to the async
    driver flavour. Returns the freshly created engine. The previous engine,
    if any, is *not* disposed automatically — call ``dispose_engine()``
    first if needed.
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(_to_async_url(database_url), echo=echo, future=True)
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
