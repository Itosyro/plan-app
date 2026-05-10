"""Integration tests for the Mini-App REST API.

Uses ``httpx.AsyncClient`` with ASGITransport so the test event loop is
shared with the SQLAlchemy async engine that conftest spins up. Each
test seeds an onboarded user (telegram_id=4242) and a small dataset,
then exercises the endpoints with a Telegram-spec-compliant signed
``initData`` header.
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
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.services import (
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
)
from app.db.base import session_scope
from app.db.models import Note, Task, UserSettings
from app.main import create_app
from app.shared.config import Settings
from app.shared.time import utcnow_naive

# Must match conftest's ``_FAKE_BOT_TOKEN`` so signatures verify.
_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_TEST_SECRET = "tg-webhook-secret"
_TG_USER = 4242
_OTHER_TG_USER = 99999


def _build_init_data(
    *,
    user_id: int,
    bot_token: str = _BOT_TOKEN,
    first_name: str = "Юсуф",
    auth_date: int | None = None,
) -> str:
    """Build a signed Telegram ``initData`` query string for a user."""
    auth_date = auth_date if auth_date is not None else int(time.time())
    user_payload = {
        "id": user_id,
        "first_name": first_name,
        "username": "u" + str(user_id),
        "language_code": "ru",
    }
    fields = {
        "auth_date": str(auth_date),
        "query_id": "Q" + str(user_id),
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    pairs = sorted(fields.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Telegram-Init-Data": _build_init_data(user_id=_TG_USER)}


@pytest_asyncio.fixture
async def seeded(engine: None) -> int:
    """Insert an onboarded user with a sample task / note / category."""
    async with session_scope() as session:
        user, _ = await get_or_create_user(session, telegram_id=_TG_USER, lang_code="ru")
        assert user.id is not None
        user.display_name = "Тестер"
        user.tz = "Europe/Moscow"
        user.onboarded_at = utcnow_naive()
        session.add(user)
        session.add(UserSettings(user_id=user.id))
        await session.flush()

        cat = await get_or_create_category(session, user.id, "Работа")
        hor = await get_or_create_horizon(session, user.id, "today")
        session.add(
            Task(
                user_id=user.id,
                category_id=cat.id,
                horizon_id=hor.id,
                title="Тест-задача",
                priority="medium",
            )
        )
        session.add(
            Note(
                user_id=user.id,
                category_id=cat.id,
                title="Тест-заметка",
            )
        )
        await session.flush()
        return user.id


@pytest_asyncio.fixture
async def app_async(engine: None) -> FastAPI:
    """Build a FastAPI app sharing the in-memory engine. No live webhook."""
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


# ── Auth tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_requires_init_data(aclient: httpx.AsyncClient, seeded: int) -> None:
    resp = await aclient.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_bad_signature(aclient: httpx.AsyncClient, seeded: int) -> None:
    headers = {"X-Telegram-Init-Data": "auth_date=1&user=%7B%22id%22%3A1%7D&hash=deadbeef"}
    resp = await aclient.get("/api/me", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_unknown_user(aclient: httpx.AsyncClient, seeded: int) -> None:
    """Valid signature but no User row — 404."""
    headers = {"X-Telegram-Init-Data": _build_init_data(user_id=11111)}
    resp = await aclient.get("/api/me", headers=headers)
    assert resp.status_code == 404


# ── /api/me ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_happy(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_id"] == _TG_USER
    assert body["display_name"] == "Тестер"
    assert body["onboarded"] is True
    assert body["settings"] is not None
    assert "critic_mode" in body["settings"]


# ── /api/horizons ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_horizons_returns_builtin_vocabulary(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/horizons", headers=auth_headers)
    assert resp.status_code == 200
    slugs = [row["slug"] for row in resp.json()]
    assert {"today", "tomorrow", "week", "month", "year", "someday"} <= set(slugs)


# ── /api/categories ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_categories_lists_with_counts(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/categories", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert any(row["name"] == "Работа" and row["task_count"] == 1 for row in body)


@pytest.mark.asyncio
async def test_categories_create_idempotent(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp1 = await aclient.post(
        "/api/categories",
        headers=auth_headers,
        json={"name": "Личное"},
    )
    assert resp1.status_code == 201
    resp2 = await aclient.post(
        "/api/categories",
        headers=auth_headers,
        json={"name": "Личное"},
    )
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


# ── /api/tasks ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tasks_list_filtered_by_horizon(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "Тест-задача"
    assert rows[0]["horizon_slug"] == "today"
    assert rows[0]["category_name"] == "Работа"


@pytest.mark.asyncio
async def test_tasks_unknown_horizon_empty(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/tasks?horizon=ALIEN", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_tasks_patch_moves_horizon(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task_id = list_resp.json()[0]["id"]
    resp = await aclient.patch(
        f"/api/tasks/{task_id}",
        headers=auth_headers,
        json={"horizon_slug": "week"},
    )
    assert resp.status_code == 200
    assert resp.json()["horizon_slug"] == "week"


@pytest.mark.asyncio
async def test_tasks_patch_marks_done(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task_id = list_resp.json()[0]["id"]
    resp = await aclient.patch(
        f"/api/tasks/{task_id}",
        headers=auth_headers,
        json={"status": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    list_again = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    assert list_again.json() == []
    list_done = await aclient.get(
        "/api/tasks?horizon=today&include_done=true",
        headers=auth_headers,
    )
    assert any(t["id"] == task_id for t in list_done.json())


@pytest.mark.asyncio
async def test_tasks_patch_unknown_id_404(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch(
        "/api/tasks/99999",
        headers=auth_headers,
        json={"status": "done"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tasks_delete_then_404(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task_id = list_resp.json()[0]["id"]
    resp = await aclient.delete(f"/api/tasks/{task_id}", headers=auth_headers)
    assert resp.status_code == 204
    after = await aclient.get(f"/api/tasks/{task_id}", headers=auth_headers)
    assert after.status_code == 404


@pytest.mark.asyncio
async def test_tasks_counts_groups_by_horizon(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    """``GET /api/tasks/counts`` returns one bucket per horizon.

    The seeded fixture inserts one ``today`` task. We add a few more
    across horizons to exercise the GROUP BY, including a ``done``
    task that must NOT count and a horizon-less task that lands in
    ``no_horizon``.
    """
    user_id = seeded
    tomorrow = await get_or_create_horizon(session, user_id, "tomorrow")
    week = await get_or_create_horizon(session, user_id, "week")
    today = await get_or_create_horizon(session, user_id, "today")
    session.add(
        Task(
            user_id=user_id,
            horizon_id=tomorrow.id,
            title="Завтра-1",
            priority="medium",
        )
    )
    session.add(
        Task(
            user_id=user_id,
            horizon_id=week.id,
            title="Неделя-1",
            priority="medium",
        )
    )
    session.add(
        Task(
            user_id=user_id,
            horizon_id=week.id,
            title="Неделя-2",
            priority="medium",
        )
    )
    session.add(
        Task(
            user_id=user_id,
            horizon_id=today.id,
            title="Готовая",
            priority="medium",
            status="done",
        )
    )
    session.add(
        Task(
            user_id=user_id,
            horizon_id=None,
            title="Без горизонта",
            priority="medium",
        )
    )
    await session.commit()

    resp = await aclient.get("/api/tasks/counts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"] == 1  # the seeded one only; ``done`` excluded
    assert body["tomorrow"] == 1
    assert body["week"] == 2
    assert body["month"] == 0
    assert body["year"] == 0
    assert body["someday"] == 0
    assert body["no_horizon"] == 1


@pytest.mark.asyncio
async def test_tasks_counts_requires_auth(aclient: httpx.AsyncClient, seeded: int) -> None:
    resp = await aclient.get("/api/tasks/counts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tasks_counts_isolated_per_user(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    """A different user's counts must never leak across the auth boundary."""
    other, _ = await get_or_create_user(session, telegram_id=_OTHER_TG_USER)
    assert other.id is not None
    other.display_name = "Другой"
    other.tz = "Europe/Moscow"
    other.onboarded_at = utcnow_naive()
    session.add(other)
    session.add(UserSettings(user_id=other.id))
    other_today = await get_or_create_horizon(session, other.id, "today")
    session.add(
        Task(
            user_id=other.id,
            horizon_id=other_today.id,
            title="Чужая задача",
            priority="medium",
        )
    )
    await session.commit()

    # First user still sees only their own one ``today`` task.
    resp = await aclient.get("/api/tasks/counts", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["today"] == 1


@pytest.mark.asyncio
async def test_tasks_cross_user_isolation(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    """A second onboarded user must not see / mutate the first user's tasks."""
    other, _ = await get_or_create_user(session, telegram_id=_OTHER_TG_USER)
    assert other.id is not None
    other.display_name = "Другой"
    other.tz = "Europe/Moscow"
    other.onboarded_at = utcnow_naive()
    session.add(other)
    session.add(UserSettings(user_id=other.id))
    await session.commit()

    other_headers = {"X-Telegram-Init-Data": _build_init_data(user_id=_OTHER_TG_USER)}
    list_resp = (await aclient.get("/api/tasks", headers=auth_headers)).json()
    assert len(list_resp) == 1
    task_id = list_resp[0]["id"]
    other_view = await aclient.get(f"/api/tasks/{task_id}", headers=other_headers)
    assert other_view.status_code == 404
    other_patch = await aclient.patch(
        f"/api/tasks/{task_id}",
        headers=other_headers,
        json={"status": "done"},
    )
    assert other_patch.status_code == 404


# ── /api/notes ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notes_list(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/notes", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert any(n["title"] == "Тест-заметка" for n in rows)


# ── /api/inbox ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inbox_404_for_missing(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/inbox/999999", headers=auth_headers)
    assert resp.status_code == 404
