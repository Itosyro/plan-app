"""Tests for the security-headers middleware.

Mirrors ``tests/test_api_endpoints.py`` app construction: build via
``create_app(Settings(...))`` and drive it with an httpx ``AsyncClient``
over ASGITransport. Verifies the headers are present and that nothing
breaks Telegram's WebView embedding (no ``X-Frame-Options: DENY``/
``SAMEORIGIN``; any CSP ``frame-ancestors`` allows Telegram).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.main import create_app
from app.shared.config import Settings

_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


@pytest_asyncio.fixture
async def app_async(engine: None) -> FastAPI:
    settings = Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_BOT_TOKEN,
        telegram_webhook_secret="tg-webhook-secret",
        webhook_base_url=None,
        database_url=None,
    )
    return create_app(settings=settings)


@pytest_asyncio.fixture
async def aclient(app_async: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_async)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_security_headers_present_on_healthz(aclient: httpx.AsyncClient) -> None:
    resp = await aclient.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


@pytest.mark.asyncio
async def test_does_not_break_telegram_embedding(aclient: httpx.AsyncClient) -> None:
    """X-Frame-Options must never block Telegram's WebView/iframe."""
    resp = await aclient.get("/healthz")
    xfo = resp.headers.get("X-Frame-Options", "")
    assert xfo.upper() not in {"DENY", "SAMEORIGIN"}


@pytest.mark.asyncio
async def test_no_csp_on_api_and_meta_paths(aclient: httpx.AsyncClient) -> None:
    """CSP is scoped to ``/app`` so it can't break API/probe responses."""
    resp = await aclient.get("/healthz")
    assert "Content-Security-Policy" not in resp.headers
    # Base hardening headers still apply everywhere.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_healthz_returns_diagnostics(aclient: httpx.AsyncClient) -> None:
    """``/healthz`` returns light diagnostics — useful for debugging from
    a phone with no shell access. Must NOT leak secrets (no DSN, no API
    keys, no webhook secret), only the *fact* that something is configured.
    """
    resp = await aclient.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "env" in body
    assert "groq_keys_configured" in body  # int count, not the keys themselves
    assert "sentry_enabled" in body
    assert "models" in body
    assert {"whisper", "splitter", "classifier", "critic"}.issubset(body["models"].keys())

    # Smoke: no obvious secrets in the response. The body is built
    # from settings without any of the secret-bearing fields, but
    # check explicitly so a future refactor doesn't slip one in.
    raw = resp.text.lower()
    for forbidden in ("sentry_dsn", "tg-webhook-secret", "https://"):
        assert forbidden not in raw, f"healthz leaked: {forbidden}"
