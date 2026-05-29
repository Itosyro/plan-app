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
from datetime import datetime
from urllib.parse import urlencode

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.router import GroqKeyRouter
from app.bot.services import (
    get_or_create_category,
    get_or_create_horizon,
    get_or_create_user,
)
from app.db.base import session_scope
from app.db.models import InboxEntry, Note, Task, UserSettings
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


@pytest.mark.asyncio
async def test_me_patch_display_name_and_tz(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={"display_name": "Юсуф-2", "tz": "Asia/Almaty"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Юсуф-2"
    assert body["tz"] == "Asia/Almaty"
    # Settings unchanged because nothing was supplied for them.
    assert body["settings"]["critic_mode"] == "confidence"

    # GET reflects the persisted state.
    fresh = await aclient.get("/api/me", headers=auth_headers)
    assert fresh.json()["tz"] == "Asia/Almaty"


@pytest.mark.asyncio
async def test_me_patch_settings_subset(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={
            "settings": {
                "morning_digest_at": "07:00",
                "courier_template_style": "playful",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["settings"]["morning_digest_at"] == "07:00"
    assert body["settings"]["courier_template_style"] == "playful"
    # Untouched fields keep their defaults.
    assert body["settings"]["evening_digest_at"] == "21:00"


@pytest.mark.asyncio
async def test_me_patch_review_enabled(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """Toggling ``review_enabled`` off persists and round-trips via GET."""
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={"settings": {"review_enabled": False}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["settings"]["review_enabled"] is False

    fresh = await aclient.get("/api/me", headers=auth_headers)
    assert fresh.status_code == 200
    assert fresh.json()["settings"]["review_enabled"] is False


@pytest.mark.asyncio
async def test_me_patch_rejects_invalid_tz(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={"tz": "Mars/Phobos"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_patch_rejects_invalid_setting_value(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={"settings": {"critic_mode": "yelling"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_patch_rejects_unknown_field(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """``extra=\"forbid\"`` rejects fields the client made up."""
    resp = await aclient.patch(
        "/api/me",
        headers=auth_headers,
        json={"settings": {"made_up": "1"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_patch_empty_body_is_noop(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.patch("/api/me", headers=auth_headers, json={})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Тестер"


@pytest.mark.asyncio
async def test_me_patch_requires_init_data(aclient: httpx.AsyncClient, seeded: int) -> None:
    resp = await aclient.patch("/api/me", json={"display_name": "X"})
    assert resp.status_code == 401


# ── /api/timezones ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timezones_returns_popular_list(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/timezones", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert {row["iana"] for row in rows} >= {"Europe/Moscow", "Asia/Almaty"}
    # Each row has a friendly Russian label.
    assert any(row["label"] == "Москва" for row in rows)


@pytest.mark.asyncio
async def test_timezones_requires_init_data(aclient: httpx.AsyncClient, seeded: int) -> None:
    resp = await aclient.get("/api/timezones")
    assert resp.status_code == 401


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
async def test_tasks_list_filtered_by_due_at_range(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    # Seed tasks across distinct due dates plus one undated task.
    async with session_scope() as session:
        session.add(
            Task(
                user_id=seeded,
                title="Jan",
                priority="medium",
                due_at=datetime(2026, 1, 15, 12, 0, 0),
            )
        )
        session.add(
            Task(
                user_id=seeded,
                title="Feb",
                priority="medium",
                due_at=datetime(2026, 2, 15, 12, 0, 0),
            )
        )
        session.add(
            Task(
                user_id=seeded,
                title="Mar",
                priority="medium",
                due_at=datetime(2026, 3, 15, 12, 0, 0),
            )
        )
        session.add(Task(user_id=seeded, title="Undated", priority="medium"))
        await session.flush()

    resp = await aclient.get(
        "/api/tasks?due_at_from=2026-02-01T00:00:00&due_at_to=2026-03-01T00:00:00",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    titles = {row["title"] for row in resp.json()}
    assert titles == {"Feb"}  # Jan/Mar out of range; Undated excluded by comparison


@pytest.mark.asyncio
async def test_tasks_list_search_q(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """``q`` filters case-insensitively across title / description / title_original.

    Note: SQLite's ``lower()`` is ASCII-only, so we seed with lowercase
    Cyrillic and use a lowercase Cyrillic query — that matches the actual
    Postgres-prod behaviour without depending on a Cyrillic case-fold
    that only Postgres provides. ASCII case-insensitivity is checked in
    a second assertion that works in both engines.
    """
    async with session_scope() as session:
        session.add(Task(user_id=seeded, title="Купить хлеб", priority="medium"))
        session.add(
            Task(
                user_id=seeded,
                title="Поход в магазин",
                description="взять молоко и хлеб",
                priority="medium",
            )
        )
        session.add(
            Task(
                user_id=seeded,
                title="Помыть посуду",
                title_original="посуда + хлеб на доске",
                priority="medium",
            )
        )
        session.add(Task(user_id=seeded, title="Гулять с собакой", priority="medium"))
        session.add(Task(user_id=seeded, title="Call Bob", priority="medium"))
        await session.flush()

    # Cyrillic substring matches title, description, and title_original.
    resp = await aclient.get("/api/tasks?q=хлеб", headers=auth_headers)
    assert resp.status_code == 200
    titles = {row["title"] for row in resp.json()}
    assert titles == {"Купить хлеб", "Поход в магазин", "Помыть посуду"}

    # ASCII case-insensitivity works in both engines.
    resp = await aclient.get("/api/tasks?q=BOB", headers=auth_headers)
    assert resp.status_code == 200
    assert [row["title"] for row in resp.json()] == ["Call Bob"]

    # Wildcards must be treated as literal characters (escape worked).
    resp = await aclient.get("/api/tasks?q=%25", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


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
async def test_tasks_patch_sets_category(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    # New category to move the card into (kanban drop = recategorize).
    new_cat = await aclient.post(
        "/api/categories",
        headers=auth_headers,
        json={"name": "Учёба"},
    )
    cat_id = new_cat.json()["id"]
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task_id = list_resp.json()[0]["id"]
    resp = await aclient.patch(
        f"/api/tasks/{task_id}",
        headers=auth_headers,
        json={"category_id": cat_id},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == cat_id
    assert resp.json()["category_name"] == "Учёба"


@pytest.mark.asyncio
async def test_tasks_patch_clears_category(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    # Dropping a card into the "Без категории" kanban column clears the
    # category. An *explicit* null in the PATCH body must clear it; an
    # omitted key still means "no change".
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task = list_resp.json()[0]
    assert task["category_id"] is not None  # seeded with «Работа»
    resp = await aclient.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers,
        json={"category_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None
    assert resp.json()["category_name"] is None


@pytest.mark.asyncio
async def test_tasks_patch_omitted_category_unchanged(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    # Omitting category_id must not wipe the existing category.
    list_resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    task = list_resp.json()[0]
    resp = await aclient.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers,
        json={"priority": "high"},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == task["category_id"]
    assert resp.json()["category_name"] == "Работа"


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
async def test_tasks_list_hides_subtasks_by_default(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """Children with non-null ``parent_id`` are excluded from the flat list."""
    # Seed a parent + 2 children directly so we don't depend on the
    # classifier path.
    async with session_scope() as session:
        cat = await get_or_create_category(session, seeded, "Работа")
        hor = await get_or_create_horizon(session, seeded, "today")
        parent = Task(
            user_id=seeded,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Родитель",
            priority="medium",
        )
        session.add(parent)
        await session.flush()
        assert parent.id is not None
        session.add(
            Task(
                user_id=seeded,
                parent_id=parent.id,
                category_id=cat.id,
                horizon_id=hor.id,
                title="Ребёнок 1",
                priority="medium",
            )
        )
        session.add(
            Task(
                user_id=seeded,
                parent_id=parent.id,
                category_id=cat.id,
                horizon_id=hor.id,
                title="Ребёнок 2",
                priority="medium",
                status="done",
            )
        )

    resp = await aclient.get("/api/tasks?horizon=today", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    titles = {r["title"] for r in rows}
    # Parent + the seeded "Тест-задача" appear; children do not.
    assert "Родитель" in titles
    assert "Ребёнок 1" not in titles
    assert "Ребёнок 2" not in titles
    parent_row = next(r for r in rows if r["title"] == "Родитель")
    assert parent_row["subtasks_total"] == 2
    assert parent_row["subtasks_done"] == 1
    assert parent_row["parent_id"] is None


@pytest.mark.asyncio
async def test_tasks_detail_returns_hydrated_subtasks(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """``GET /tasks/{id}`` returns ``subtasks`` array with full child rows."""
    async with session_scope() as session:
        cat = await get_or_create_category(session, seeded, "Учёба")
        hor = await get_or_create_horizon(session, seeded, "week")
        parent = Task(
            user_id=seeded,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Английский",
            priority="high",
        )
        session.add(parent)
        await session.flush()
        assert parent.id is not None
        for title in ["Duolingo", "Подкаст", "Видео"]:
            session.add(
                Task(
                    user_id=seeded,
                    parent_id=parent.id,
                    category_id=cat.id,
                    horizon_id=hor.id,
                    title=title,
                    priority="high",
                )
            )
        parent_id = parent.id

    resp = await aclient.get(f"/api/tasks/{parent_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Английский"
    assert body["subtasks_total"] == 3
    assert body["subtasks_done"] == 0
    titles = [s["title"] for s in body["subtasks"]]
    assert titles == ["Duolingo", "Подкаст", "Видео"]
    for s in body["subtasks"]:
        assert s["parent_id"] == parent_id


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


@pytest.mark.asyncio
async def test_notes_create_minimal(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.post(
        "/api/notes",
        headers=auth_headers,
        json={"title": "Идея на завтра"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Идея на завтра"
    assert body["body"] is None
    assert body["category_id"] is None


@pytest.mark.asyncio
async def test_notes_create_with_body_and_category(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    # Pull the seeded category for «Работа».
    cats = (await aclient.get("/api/categories", headers=auth_headers)).json()
    work = next(c for c in cats if c["name"] == "Работа")
    resp = await aclient.post(
        "/api/notes",
        headers=auth_headers,
        json={"title": "Конспект", "body": "ABC", "category_id": work["id"]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["body"] == "ABC"
    assert body["category_id"] == work["id"]
    assert body["category_name"] == "Работа"


@pytest.mark.asyncio
async def test_notes_create_rejects_empty_title(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.post("/api/notes", headers=auth_headers, json={"title": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_notes_create_404_on_foreign_category(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.post(
        "/api/notes",
        headers=auth_headers,
        json={"title": "X", "category_id": 999999},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_notes_patch_title_and_body(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    listed = (await aclient.get("/api/notes", headers=auth_headers)).json()
    note_id = listed[0]["id"]
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"title": "Изменено", "body": "Новый текст"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Изменено"
    assert body["body"] == "Новый текст"


@pytest.mark.asyncio
async def test_notes_patch_clears_body_with_empty_string(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    listed = (await aclient.get("/api/notes", headers=auth_headers)).json()
    note_id = listed[0]["id"]
    # First set a non-empty body so the clear is observable.
    await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"body": "временно"},
    )
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"body": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["body"] is None


@pytest.mark.asyncio
async def test_notes_patch_404_for_other_user(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    listed = (await aclient.get("/api/notes", headers=auth_headers)).json()
    note_id = listed[0]["id"]
    other_headers = {"X-Telegram-Init-Data": _build_init_data(user_id=_OTHER_TG_USER)}
    # Onboard the other user first so auth itself doesn't 404.
    async with session_scope() as session:
        await get_or_create_user(session, telegram_id=_OTHER_TG_USER, lang_code="ru")
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=other_headers,
        json={"title": "взлом"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_notes_patch_rejects_unknown_field(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    listed = (await aclient.get("/api/notes", headers=auth_headers)).json()
    note_id = listed[0]["id"]
    resp = await aclient.patch(
        f"/api/notes/{note_id}",
        headers=auth_headers,
        json={"created_at": "2026-01-01T00:00:00"},
    )
    assert resp.status_code == 422


# ── /api/inbox ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inbox_404_for_missing(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    resp = await aclient.get("/api/inbox/999999", headers=auth_headers)
    assert resp.status_code == 404


# ── /api/inbox review tab («Входящие») ───────────────────────────────


async def _seed_review_entry(user_id: int, *, n_tasks: int = 2) -> tuple[int, list[int]]:
    """Create a flagged inbox entry with ``n_tasks`` tasks linked to it."""
    async with session_scope() as session:
        hor = await get_or_create_horizon(session, user_id, "today")
        entry = InboxEntry(
            user_id=user_id,
            kind="voice",
            transcript="купить молоко и записаться к врачу",
            needs_review=True,
        )
        session.add(entry)
        await session.flush()
        task_ids: list[int] = []
        for i in range(n_tasks):
            task = Task(
                user_id=user_id,
                horizon_id=hor.id,
                title=f"Задача {i + 1}",
                priority="medium",
                source_inbox_id=entry.id,
            )
            session.add(task)
            await session.flush()
            assert task.id is not None
            task_ids.append(task.id)
        assert entry.id is not None
        return entry.id, task_ids


@pytest.mark.asyncio
async def test_inbox_pending_lists_flagged_entry(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    entry_id, task_ids = await _seed_review_entry(seeded, n_tasks=2)
    resp = await aclient.get("/api/inbox/pending", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    review = body[0]
    assert review["id"] == entry_id
    assert review["text"] == "купить молоко и записаться к врачу"
    assert {t["id"] for t in review["tasks"]} == set(task_ids)


@pytest.mark.asyncio
async def test_inbox_confirm_drops_unchecked_and_clears_flag(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    entry_id, task_ids = await _seed_review_entry(seeded, n_tasks=2)
    keep, drop = task_ids[0], task_ids[1]

    resp = await aclient.post(
        f"/api/inbox/{entry_id}/confirm",
        headers=auth_headers,
        json={"keep_task_ids": [keep]},
    )
    assert resp.status_code == 204

    # Entry leaves the tab.
    pending = (await aclient.get("/api/inbox/pending", headers=auth_headers)).json()
    assert pending == []

    # Kept task survives, dropped task is soft-deleted, flag cleared.
    async with session_scope() as session:
        kept = await session.get(Task, keep)
        dropped = await session.get(Task, drop)
        entry = await session.get(InboxEntry, entry_id)
        assert kept is not None and kept.deleted_at is None
        assert dropped is not None and dropped.deleted_at is not None
        assert entry is not None and entry.needs_review is False


@pytest.mark.asyncio
async def test_inbox_confirm_empty_keep_drops_all(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    entry_id, task_ids = await _seed_review_entry(seeded, n_tasks=2)
    resp = await aclient.post(
        f"/api/inbox/{entry_id}/confirm",
        headers=auth_headers,
        json={"keep_task_ids": []},
    )
    assert resp.status_code == 204
    async with session_scope() as session:
        for tid in task_ids:
            task = await session.get(Task, tid)
            assert task is not None and task.deleted_at is not None


async def _seed_review_entry_with_notes(
    user_id: int,
    *,
    n_tasks: int = 1,
    n_notes: int = 2,
    category_name: str | None = None,
) -> tuple[int, list[int], list[int]]:
    """Seed an inbox entry with both tasks and notes for review tests."""
    async with session_scope() as session:
        hor = await get_or_create_horizon(session, user_id, "today")
        category_id: int | None = None
        if category_name is not None:
            cat = await get_or_create_category(session, user_id, category_name)
            category_id = cat.id
        entry = InboxEntry(
            user_id=user_id,
            kind="text",
            raw_text="смешанная заметка и задача",
            needs_review=True,
        )
        session.add(entry)
        await session.flush()
        task_ids: list[int] = []
        for i in range(n_tasks):
            task = Task(
                user_id=user_id,
                horizon_id=hor.id,
                title=f"Задача {i + 1}",
                priority="medium",
                source_inbox_id=entry.id,
            )
            session.add(task)
            await session.flush()
            assert task.id is not None
            task_ids.append(task.id)
        note_ids: list[int] = []
        for i in range(n_notes):
            note = Note(
                user_id=user_id,
                title=f"Заметка {i + 1}",
                body="тело",
                category_id=category_id,
                source_inbox_id=entry.id,
            )
            session.add(note)
            await session.flush()
            assert note.id is not None
            note_ids.append(note.id)
        assert entry.id is not None
        return entry.id, task_ids, note_ids


@pytest.mark.asyncio
async def test_inbox_pending_lists_notes(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    entry_id, task_ids, note_ids = await _seed_review_entry_with_notes(
        seeded, n_tasks=1, n_notes=2, category_name="Идеи"
    )
    resp = await aclient.get("/api/inbox/pending", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    review = body[0]
    assert review["id"] == entry_id
    assert {t["id"] for t in review["tasks"]} == set(task_ids)
    assert {n["id"] for n in review["notes"]} == set(note_ids)
    # Category name hydrated.
    assert all(n["category_name"] == "Идеи" for n in review["notes"])


@pytest.mark.asyncio
async def test_inbox_confirm_drops_unkept_notes(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    entry_id, _task_ids, note_ids = await _seed_review_entry_with_notes(
        seeded, n_tasks=0, n_notes=2
    )
    keep, drop = note_ids[0], note_ids[1]

    resp = await aclient.post(
        f"/api/inbox/{entry_id}/confirm",
        headers=auth_headers,
        json={"keep_task_ids": [], "keep_note_ids": [keep]},
    )
    assert resp.status_code == 204

    async with session_scope() as session:
        kept = await session.get(Note, keep)
        dropped = await session.get(Note, drop)
        entry = await session.get(InboxEntry, entry_id)
        assert kept is not None and kept.deleted_at is None
        assert dropped is not None and dropped.deleted_at is not None
        assert entry is not None and entry.needs_review is False


@pytest.mark.asyncio
async def test_inbox_confirm_back_compat_no_keep_note_ids(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
) -> None:
    """Older clients that POST without ``keep_note_ids`` drop all notes
    (default empty list = keep nothing) — mirrors current task semantics."""
    entry_id, task_ids, note_ids = await _seed_review_entry_with_notes(seeded, n_tasks=1, n_notes=1)
    resp = await aclient.post(
        f"/api/inbox/{entry_id}/confirm",
        headers=auth_headers,
        json={"keep_task_ids": [task_ids[0]]},
    )
    assert resp.status_code == 204
    async with session_scope() as session:
        kept_task = await session.get(Task, task_ids[0])
        note = await session.get(Note, note_ids[0])
        assert kept_task is not None and kept_task.deleted_at is None
        assert note is not None and note.deleted_at is not None


@pytest.mark.asyncio
async def test_inbox_confirm_rejects_other_user(
    aclient: httpx.AsyncClient,
    seeded: int,
) -> None:
    entry_id, task_ids = await _seed_review_entry(seeded, n_tasks=1)
    other_headers = {"X-Telegram-Init-Data": _build_init_data(user_id=_OTHER_TG_USER)}
    async with session_scope() as session:
        await get_or_create_user(session, telegram_id=_OTHER_TG_USER, lang_code="ru")
    resp = await aclient.post(
        f"/api/inbox/{entry_id}/confirm",
        headers=other_headers,
        json={"keep_task_ids": []},
    )
    assert resp.status_code == 404
    # Task untouched.
    async with session_scope() as session:
        task = await session.get(Task, task_ids[0])
        assert task is not None and task.deleted_at is None


# ── /api/tasks/{id}/split ────────────────────────────────────────────


def _split_groq_response(subtasks: list[str]) -> dict[str, object]:
    """Fake Groq chat-completion response carrying the JSON subtasks payload."""
    body = json.dumps({"subtasks": subtasks})
    return {
        "id": "chatcmpl-split-task",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": body},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110},
    }


@pytest.fixture
def fake_groq_router(monkeypatch: pytest.MonkeyPatch) -> GroqKeyRouter:
    """Install a Groq router with a fake key on the tasks router.

    The production ``get_groq_router`` returns ``None`` in tests
    (no Groq keys are configured), which would short-circuit the
    endpoint with 503. We replace it with a router carrying a
    dummy key so ``respx`` can intercept the actual HTTP call.
    """
    router = GroqKeyRouter(keys=["gsk_test_split_key"])
    monkeypatch.setattr(
        "app.api.routers.tasks.get_groq_router",
        lambda: router,
    )
    return router


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_happy_path(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    fake_groq_router: GroqKeyRouter,
) -> None:
    """LLM returns 3 subtitles → 3 children created with inherited fields."""
    list_resp = (await aclient.get("/api/tasks", headers=auth_headers)).json()
    parent = next(t for t in list_resp if t["title"] == "Тест-задача")
    parent_id = parent["id"]

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=_split_groq_response(
                ["составить план", "написать черновик", "отправить на ревью"]
            ),
        )
    )

    resp = await aclient.post(f"/api/tasks/{parent_id}/split", headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body, list)
    assert 2 <= len(body) <= 5
    assert len(body) == 3
    for child in body:
        assert child["parent_id"] == parent_id
        assert child["category_id"] == parent["category_id"]
        assert child["category_name"] == parent["category_name"]
        assert child["horizon_slug"] == parent["horizon_slug"]
        assert child["priority"] == parent["priority"]

    # Persisted state matches the response.
    async with session_scope() as session:
        children = (await session.exec(select(Task).where(Task.parent_id == parent_id))).all()
        assert len(children) == 3
        for c in children:
            assert c.user_id == seeded


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_404_for_missing_task(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    fake_groq_router: GroqKeyRouter,
) -> None:
    resp = await aclient.post("/api/tasks/9999999/split", headers=auth_headers)
    assert resp.status_code == 404


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_404_for_other_users_task(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    session: AsyncSession,
    fake_groq_router: GroqKeyRouter,
) -> None:
    other, _ = await get_or_create_user(session, telegram_id=_OTHER_TG_USER)
    assert other.id is not None
    other.onboarded_at = utcnow_naive()
    other.tz = "Europe/Moscow"
    session.add(other)
    session.add(UserSettings(user_id=other.id))
    await session.commit()

    list_resp = (await aclient.get("/api/tasks", headers=auth_headers)).json()
    parent_id = list_resp[0]["id"]

    other_headers = {"X-Telegram-Init-Data": _build_init_data(user_id=_OTHER_TG_USER)}
    resp = await aclient.post(f"/api/tasks/{parent_id}/split", headers=other_headers)
    assert resp.status_code == 404


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_409_when_already_has_children(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    fake_groq_router: GroqKeyRouter,
) -> None:
    async with session_scope() as session:
        cat = await get_or_create_category(session, seeded, "Работа")
        hor = await get_or_create_horizon(session, seeded, "today")
        parent = Task(
            user_id=seeded,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Уже разбита",
            priority="medium",
        )
        session.add(parent)
        await session.flush()
        assert parent.id is not None
        session.add(
            Task(
                user_id=seeded,
                parent_id=parent.id,
                category_id=cat.id,
                horizon_id=hor.id,
                title="существующий ребёнок",
                priority="medium",
            )
        )
        parent_id = parent.id

    resp = await aclient.post(f"/api/tasks/{parent_id}/split", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "task already split"


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_409_when_task_is_a_subtask(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    fake_groq_router: GroqKeyRouter,
) -> None:
    async with session_scope() as session:
        cat = await get_or_create_category(session, seeded, "Работа")
        hor = await get_or_create_horizon(session, seeded, "today")
        parent = Task(
            user_id=seeded,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Родитель",
            priority="medium",
        )
        session.add(parent)
        await session.flush()
        assert parent.id is not None
        child = Task(
            user_id=seeded,
            parent_id=parent.id,
            category_id=cat.id,
            horizon_id=hor.id,
            title="Ребёнок",
            priority="medium",
        )
        session.add(child)
        await session.flush()
        assert child.id is not None
        child_id = child.id

    resp = await aclient.post(f"/api/tasks/{child_id}/split", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "task is already a subtask"


@respx.mock
@pytest.mark.asyncio
async def test_tasks_split_422_when_llm_returns_empty(
    aclient: httpx.AsyncClient,
    seeded: int,
    auth_headers: dict[str, str],
    fake_groq_router: GroqKeyRouter,
) -> None:
    list_resp = (await aclient.get("/api/tasks", headers=auth_headers)).json()
    parent_id = list_resp[0]["id"]

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_split_groq_response([]))
    )

    resp = await aclient.post(f"/api/tasks/{parent_id}/split", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "task is already atomic, nothing to split"

    # No children were persisted.
    async with session_scope() as session:
        children = (await session.exec(select(Task).where(Task.parent_id == parent_id))).all()
        assert len(children) == 0
