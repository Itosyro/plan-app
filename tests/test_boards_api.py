"""Integration tests for ``/api/boards`` (Excalidraw canvas CRUD).

Reuses the signed-initData + ASGITransport harness from
``test_api_endpoints.py`` via shared fixtures, exercising create / list /
get / patch / delete, owner-scoping, soft-delete, and the scene
size guard.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.bot.services import get_or_create_user
from app.db.base import session_scope
from app.db.models import UserSettings
from app.main import create_app
from app.shared.config import Settings
from app.shared.time import utcnow_naive

_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_TEST_SECRET = "tg-webhook-secret"
_TG_USER = 4242
_OTHER_TG_USER = 99999


def _build_init_data(*, user_id: int, bot_token: str = _BOT_TOKEN) -> str:
    auth_date = int(time.time())
    user_payload = {
        "id": user_id,
        "first_name": "Тест",
        "username": "u" + str(user_id),
        "language_code": "ru",
    }
    fields = {
        "auth_date": str(auth_date),
        "query_id": "Q" + str(user_id),
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    pairs = sorted(fields.items())
    dcs = "\n".join(f"{k}={v}" for k, v in pairs)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, dcs.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = sig
    return urlencode(fields)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Telegram-Init-Data": _build_init_data(user_id=_TG_USER)}


@pytest.fixture
def other_auth_headers() -> dict[str, str]:
    return {"X-Telegram-Init-Data": _build_init_data(user_id=_OTHER_TG_USER)}


async def _onboard(telegram_id: int) -> int:
    async with session_scope() as session:
        user, _ = await get_or_create_user(session, telegram_id=telegram_id, lang_code="ru")
        assert user.id is not None
        user.onboarded_at = utcnow_naive()
        user.tz = "Europe/Moscow"
        session.add(user)
        session.add(UserSettings(user_id=user.id))
        await session.flush()
        return user.id


@pytest_asyncio.fixture
async def seeded(engine: None) -> int:
    """Onboard the primary user (and a second user for scoping tests)."""
    uid = await _onboard(_TG_USER)
    await _onboard(_OTHER_TG_USER)
    return uid


@pytest_asyncio.fixture
async def app_async(engine: None) -> FastAPI:
    settings = Settings(
        env="test",
        log_level="WARNING",
        telegram_bot_token=_BOT_TOKEN,
        telegram_webhook_secret=_TEST_SECRET,
        webhook_base_url=None,
        database_url=None,
    )
    return create_app(settings=settings)


@pytest_asyncio.fixture
async def aclient(app_async: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_async)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


_SAMPLE_SCENE = {
    "type": "excalidraw",
    "version": 2,
    "elements": [
        {"id": "a1", "type": "rectangle", "x": 10, "y": 20, "width": 100, "height": 50},
    ],
    "appState": {"viewBackgroundColor": "#ffffff"},
}


@pytest.mark.asyncio
async def test_board_crud_roundtrip(
    aclient: httpx.AsyncClient, seeded: int, auth_headers: dict[str, str]
) -> None:
    # Create
    resp = await aclient.post("/api/boards", headers=auth_headers, json={"name": "Карта идей"})
    assert resp.status_code == 201, resp.text
    board = resp.json()
    bid = board["id"]
    assert board["name"] == "Карта идей"
    assert board["scene_json"] is None

    # List — light shape, no scene
    resp = await aclient.get("/api/boards", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == bid
    assert "scene_json" not in rows[0]

    # Patch scene + name
    resp = await aclient.patch(
        f"/api/boards/{bid}",
        headers=auth_headers,
        json={"name": "Карта идей v2", "scene_json": _SAMPLE_SCENE},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Карта идей v2"

    # Get detail — scene round-trips
    resp = await aclient.get(f"/api/boards/{bid}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["scene_json"]["elements"][0]["id"] == "a1"

    # Delete (soft) → gone from list
    resp = await aclient.delete(f"/api/boards/{bid}", headers=auth_headers)
    assert resp.status_code == 204
    resp = await aclient.get("/api/boards", headers=auth_headers)
    assert resp.json() == []
    # And detail 404s
    resp = await aclient.get(f"/api/boards/{bid}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_board_create_defaults_name(
    aclient: httpx.AsyncClient, seeded: int, auth_headers: dict[str, str]
) -> None:
    resp = await aclient.post("/api/boards", headers=auth_headers, json={})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Без названия"


@pytest.mark.asyncio
async def test_board_owner_scoped(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    """A board created by user A is invisible / unpatchable by user B."""
    resp = await aclient.post("/api/boards", headers=auth_headers, json={"name": "Моя"})
    bid = resp.json()["id"]

    # User B can't see it in their list
    resp = await aclient.get("/api/boards", headers=other_auth_headers)
    assert resp.json() == []
    # …can't GET it
    assert (await aclient.get(f"/api/boards/{bid}", headers=other_auth_headers)).status_code == 404
    # …can't PATCH it
    resp = await aclient.patch(
        f"/api/boards/{bid}", headers=other_auth_headers, json={"name": "Угон"}
    )
    assert resp.status_code == 404
    # …can't DELETE it
    assert (
        await aclient.delete(f"/api/boards/{bid}", headers=other_auth_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_board_rejects_oversize_scene(
    aclient: httpx.AsyncClient, seeded: int, auth_headers: dict[str, str]
) -> None:
    bid = (await aclient.post("/api/boards", headers=auth_headers, json={})).json()["id"]
    # Build a scene over the 5MB ceiling.
    huge = {"type": "excalidraw", "blob": "x" * (5 * 1024 * 1024 + 10)}
    resp = await aclient.patch(
        f"/api/boards/{bid}", headers=auth_headers, json={"scene_json": huge}
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_board_list_ordered_by_updated(
    aclient: httpx.AsyncClient, seeded: int, auth_headers: dict[str, str]
) -> None:
    a = (await aclient.post("/api/boards", headers=auth_headers, json={"name": "A"})).json()["id"]
    b = (await aclient.post("/api/boards", headers=auth_headers, json={"name": "B"})).json()["id"]
    # Touch A so it becomes most-recently-updated.
    await aclient.patch(f"/api/boards/{a}", headers=auth_headers, json={"name": "A2"})
    rows = (await aclient.get("/api/boards", headers=auth_headers)).json()
    assert [r["id"] for r in rows] == [a, b]
