"""Tests for the `POST /tg/<secret>` Telegram webhook endpoint.

We exercise the security checks (path secret + header secret) and the
``update_id`` idempotency cache without driving aiogram all the way
through to ``sendMessage``. End-to-end handler tests are covered by
``test_services.py`` (services are tested directly).

To stop aiogram from making real HTTP calls we replace ``Bot.session`` with
a session whose ``make_request`` is a no-op stub.
"""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.client.session.base import BaseSession
from fastapi.testclient import TestClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import TelegramUpdate

_TEST_SECRET = "tg-webhook-secret"


class _NullSession(BaseSession):
    """Aiogram session that records calls and never hits the network."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Any] = []

    async def make_request(self, bot, method, timeout=None):  # type: ignore[override]
        self.calls.append(method)
        return None  # aiogram tolerates None for fire-and-forget tests

    async def stream_content(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        raise NotImplementedError

    async def close(self) -> None:  # type: ignore[override]
        return None


def _make_update_payload(update_id: int, text: str = "/start") -> dict[str, Any]:
    """Minimal valid Telegram Update JSON for a text message."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 555, "is_bot": False, "first_name": "T"},
            "text": text,
        },
    }


@pytest.fixture
def patched_client(client: TestClient) -> TestClient:
    """Replace the bot's network session with a no-op so handlers don't 500."""
    bot = None
    for route in client.app.routes:
        # Locate the bot by introspecting the closure of telegram_webhook.
        # `create_app` keeps `bot` in the enclosing scope of the endpoint.
        if getattr(route, "name", "") == "telegram_webhook":
            cell = route.endpoint.__closure__  # type: ignore[union-attr]
            if cell is None:
                continue
            for c in cell:
                contents = c.cell_contents
                if contents.__class__.__name__ == "Bot":
                    bot = contents
                    break
    assert bot is not None, "could not find Bot in app routes"
    bot.session = _NullSession()
    return client


def test_webhook_rejects_bad_path_secret(patched_client: TestClient) -> None:
    resp = patched_client.post(
        "/tg/wrong",
        json=_make_update_payload(1),
        headers={"X-Telegram-Bot-Api-Secret-Token": _TEST_SECRET},
    )
    assert resp.status_code == 403
    assert "path" in resp.json()["detail"].lower()


def test_webhook_rejects_bad_header(patched_client: TestClient) -> None:
    resp = patched_client.post(
        f"/tg/{_TEST_SECRET}",
        json=_make_update_payload(2),
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
    )
    assert resp.status_code == 403
    assert "header" in resp.json()["detail"].lower()


def test_webhook_accepts_valid_request(patched_client: TestClient) -> None:
    resp = patched_client.post(
        f"/tg/{_TEST_SECRET}",
        json=_make_update_payload(3),
        headers={"X-Telegram-Bot-Api-Secret-Token": _TEST_SECRET},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_webhook_idempotent_on_update_id(
    patched_client: TestClient, session: AsyncSession
) -> None:
    """Same ``update_id`` arriving twice is processed exactly once."""
    payload = _make_update_payload(4242, text="hello")

    for _ in range(2):
        resp = patched_client.post(
            f"/tg/{_TEST_SECRET}",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": _TEST_SECRET},
        )
        assert resp.status_code == 200

    rows = (
        await session.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == 4242))
    ).all()
    assert len(rows) == 1
