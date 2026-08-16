"""Regression test for «clear the category» on ``PATCH /api/notes/{id}``.

Reuses the signed-initData + ASGITransport harness of the other API test
modules. Covers the three-way contract the Mini-App «Без категории» row
depends on: set → omitted key keeps it → explicit ``null`` clears it.
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

from app.bot.services import get_or_create_category, get_or_create_user
from app.db.base import session_scope
from app.db.models import UserSettings
from app.main import create_app
from app.shared.config import Settings
from app.shared.time import utcnow_naive

_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_TEST_SECRET = "tg-webhook-secret"
_TG_USER = 4242


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
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, dcs.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Telegram-Init-Data": _build_init_data(user_id=_TG_USER)}


@pytest_asyncio.fixture
async def seeded_category(engine: None) -> int:
    """Onboard the user with one category and return its id."""
    async with session_scope() as session:
        user, _ = await get_or_create_user(session, telegram_id=_TG_USER, lang_code="ru")
        assert user.id is not None
        user.onboarded_at = utcnow_naive()
        user.tz = "Europe/Moscow"
        session.add(user)
        session.add(UserSettings(user_id=user.id))
        await session.flush()
        cat = await get_or_create_category(session, user.id, "Работа")
        assert cat.id is not None
        return cat.id


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


@pytest.mark.asyncio
async def test_patch_note_category_set_unset_and_omitted(
    aclient: httpx.AsyncClient,
    seeded_category: int,
    auth_headers: dict[str, str],
) -> None:
    """Explicit ``category_id: null`` clears it; an omitted key does not."""
    created = await aclient.post(
        "/api/notes",
        headers=auth_headers,
        json={"title": "Заметка"},
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    # set
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"category_id": seeded_category},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == seeded_category
    assert resp.json()["category_name"] == "Работа"

    # omitted key — must not touch the category
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"title": "Переименована"},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == seeded_category

    # explicit null — clears it
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"category_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None
    assert resp.json()["category_name"] is None

    # …and the clear is persisted, not just echoed
    fresh = await aclient.get(f"/api/notes/{note_id}", headers=auth_headers)
    assert fresh.status_code == 200
    assert fresh.json()["category_id"] is None
