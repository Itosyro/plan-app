"""Pytest fixtures shared across the suite.

* `settings` — a `Settings` instance pointing at in-memory SQLite plus a
  fake but well-formed Telegram bot token, suitable for unit tests.
* `engine` — initialises the global async engine on `:memory:` SQLite,
  creates all SQLModel tables, yields, then disposes.
* `session` — yields a fresh `AsyncSession` (auto-rollback on teardown is
  achieved by recreating the engine per test).
* `app` / `client` — a configured FastAPI app + TestClient that uses the
  shared engine (no live `setWebhook` because `webhook_base_url` is empty).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.base import dispose_engine, get_sessionmaker, init_engine
from app.main import create_app
from app.shared.config import Settings
from app.shared.logging import configure_logging

# Ensure structlog is configured early — before any test calls
# ``logger.exception()``. Without this, structlog falls back to its
# defaults (Rich ConsoleRenderer with ``show_locals=True``) which hangs
# when formatting tracebacks with complex Groq/instructor objects.
configure_logging()

# Must match `len > 34` so aiogram's token validator is happy. It's a fake
# value: we never actually hit api.telegram.org in tests.
_FAKE_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_TEST_SECRET = "tg-webhook-secret"


@pytest.fixture
def settings() -> Settings:
    """Test settings: fake bot token, no live webhook, no DB auto-init.

    ``database_url`` is left empty so the FastAPI lifespan doesn't try to
    create its own engine — the ``engine`` fixture below owns the engine
    so it can be shared with direct-DB assertions in tests.
    """
    return Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_FAKE_BOT_TOKEN,
        telegram_webhook_secret=_TEST_SECRET,
        webhook_base_url=None,  # suppresses set_webhook in lifespan
        database_url=None,  # engine is owned by the ``engine`` fixture
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[None]:
    """Create a fresh in-memory engine + schema for each test."""
    eng = init_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def session(engine: None) -> AsyncIterator[AsyncSession]:
    """Yield an `AsyncSession` for direct DB assertions in tests."""
    sm = get_sessionmaker()
    async with sm() as s:
        yield s


@pytest.fixture
def client(settings: Settings, engine: None) -> Iterator[TestClient]:
    """A TestClient bound to a freshly-built app using the test settings.

    The ``engine`` fixture has already initialised the global engine. Because
    ``settings.database_url`` is ``None``, the app's lifespan won't replace
    it — handlers and tests will share the same in-memory database.
    """
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c
