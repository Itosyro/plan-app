"""Tests for the soft-delete / trash-bin feature (PR-D).

Covers:
* ``test_soft_delete_filters_lists`` — deleted items vanish from API lists.
* ``test_purge_after_24h`` — the scheduler worker physically removes
  records older than 24 h.
* ``test_restore_idempotent`` — restoring the same item twice is safe.
* ``test_trash_lists_only_users_own`` — /api/trash respects ownership.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel import select

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
from app.workers.scheduler import purge_trash

_BOT_TOKEN = "123456789:AAEt-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_TEST_SECRET = "tg-webhook-secret"
_TG_USER_A = 5001
_TG_USER_B = 5002


def _build_init_data(user_id: int) -> str:
    auth_date = int(time.time())
    user_payload = {
        "id": user_id,
        "first_name": "Test",
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
    secret_key = hmac.new(b"WebAppData", _BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


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


@pytest_asyncio.fixture
async def seeded_two_users(engine: None) -> tuple[int, int]:
    """Seed two onboarded users each with a task and a note."""
    async with session_scope() as session:
        user_a, _ = await get_or_create_user(session, telegram_id=_TG_USER_A, lang_code="ru")
        assert user_a.id is not None
        user_a.onboarded_at = utcnow_naive()
        session.add(user_a)
        session.add(UserSettings(user_id=user_a.id))

        cat_a = await get_or_create_category(session, user_a.id, "Work")
        hor_a = await get_or_create_horizon(session, user_a.id, "today")
        session.add(
            Task(
                user_id=user_a.id,
                category_id=cat_a.id,
                horizon_id=hor_a.id,
                title="Task A",
            )
        )
        session.add(Note(user_id=user_a.id, title="Note A"))
        await session.flush()

        user_b, _ = await get_or_create_user(session, telegram_id=_TG_USER_B, lang_code="ru")
        assert user_b.id is not None
        user_b.onboarded_at = utcnow_naive()
        session.add(user_b)
        session.add(UserSettings(user_id=user_b.id))

        hor_b = await get_or_create_horizon(session, user_b.id, "today")
        session.add(
            Task(
                user_id=user_b.id,
                horizon_id=hor_b.id,
                title="Task B",
            )
        )
        session.add(Note(user_id=user_b.id, title="Note B"))
        await session.flush()

        return user_a.id, user_b.id


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_soft_delete_filters_lists(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """After DELETE, the item disappears from list endpoints but remains in DB."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    # Get the task id.
    tasks_before = (await aclient.get("/api/tasks", headers=h)).json()
    assert len(tasks_before) == 1
    task_id = tasks_before[0]["id"]

    # Get the note id.
    notes_before = (await aclient.get("/api/notes", headers=h)).json()
    assert len(notes_before) == 1
    note_id = notes_before[0]["id"]

    # Soft-delete the task.
    resp = await aclient.delete(f"/api/tasks/{task_id}", headers=h)
    assert resp.status_code == 204

    # Soft-delete the note.
    resp = await aclient.delete(f"/api/notes/{note_id}", headers=h)
    assert resp.status_code == 204

    # Lists are now empty.
    assert (await aclient.get("/api/tasks", headers=h)).json() == []
    assert (await aclient.get("/api/notes", headers=h)).json() == []

    # Counts show zero.
    counts = (await aclient.get("/api/tasks/counts", headers=h)).json()
    assert counts["today"] == 0

    # But the rows still exist in the DB.
    async with session_scope() as session:
        task = (await session.exec(select(Task).where(Task.id == task_id))).first()
        assert task is not None
        assert task.deleted_at is not None

        note = (await session.exec(select(Note).where(Note.id == note_id))).first()
        assert note is not None
        assert note.deleted_at is not None


@pytest.mark.asyncio
async def test_purge_after_24h(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """Records deleted > 24 h ago are physically removed by purge_trash."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    tasks = (await aclient.get("/api/tasks", headers=h)).json()
    task_id = tasks[0]["id"]
    notes = (await aclient.get("/api/notes", headers=h)).json()
    note_id = notes[0]["id"]

    # Soft-delete both.
    await aclient.delete(f"/api/tasks/{task_id}", headers=h)
    await aclient.delete(f"/api/notes/{note_id}", headers=h)

    # Set deleted_at to 25 hours ago.
    old_ts = utcnow_naive() - timedelta(hours=25)
    async with session_scope() as session:
        task = (await session.exec(select(Task).where(Task.id == task_id))).first()
        assert task is not None
        task.deleted_at = old_ts
        session.add(task)

        note = (await session.exec(select(Note).where(Note.id == note_id))).first()
        assert note is not None
        note.deleted_at = old_ts
        session.add(note)
        await session.flush()

    # Purge.
    result = await purge_trash()
    assert result["tasks"] == 1
    assert result["notes"] == 1

    # Rows are gone from DB.
    async with session_scope() as session:
        assert (await session.exec(select(Task).where(Task.id == task_id))).first() is None
        assert (await session.exec(select(Note).where(Note.id == note_id))).first() is None


@pytest.mark.asyncio
async def test_purge_ignores_recent(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """Records deleted < 24 h ago are NOT purged."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    tasks = (await aclient.get("/api/tasks", headers=h)).json()
    task_id = tasks[0]["id"]
    await aclient.delete(f"/api/tasks/{task_id}", headers=h)

    result = await purge_trash()
    assert result["tasks"] == 0

    async with session_scope() as session:
        task = (await session.exec(select(Task).where(Task.id == task_id))).first()
        assert task is not None
        assert task.deleted_at is not None


@pytest.mark.asyncio
async def test_restore_idempotent(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """Restoring an already-restored item returns 404 (not in trash)."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    tasks = (await aclient.get("/api/tasks", headers=h)).json()
    task_id = tasks[0]["id"]

    # Soft-delete.
    await aclient.delete(f"/api/tasks/{task_id}", headers=h)

    # Restore once.
    resp = await aclient.post(f"/api/trash/task/{task_id}/restore", headers=h)
    assert resp.status_code == 200

    # Task is back in list.
    tasks_after = (await aclient.get("/api/tasks", headers=h)).json()
    assert len(tasks_after) == 1

    # Second restore → 404 (already restored).
    resp2 = await aclient.post(f"/api/trash/task/{task_id}/restore", headers=h)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_trash_lists_only_users_own(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """GET /api/trash only returns items owned by the authenticated user."""
    h_a = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}
    h_b = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_B)}

    # User A soft-deletes their task.
    tasks_a = (await aclient.get("/api/tasks", headers=h_a)).json()
    task_a_id = tasks_a[0]["id"]
    await aclient.delete(f"/api/tasks/{task_a_id}", headers=h_a)

    # User B soft-deletes their note.
    notes_b = (await aclient.get("/api/notes", headers=h_b)).json()
    note_b_id = notes_b[0]["id"]
    await aclient.delete(f"/api/notes/{note_b_id}", headers=h_b)

    # User A sees only their own trash.
    trash_a = (await aclient.get("/api/trash", headers=h_a)).json()
    assert len(trash_a) == 1
    assert trash_a[0]["kind"] == "task"
    assert trash_a[0]["id"] == task_a_id

    # User B sees only their own trash.
    trash_b = (await aclient.get("/api/trash", headers=h_b)).json()
    assert len(trash_b) == 1
    assert trash_b[0]["kind"] == "note"
    assert trash_b[0]["id"] == note_b_id

    # User B cannot restore user A's task.
    resp = await aclient.post(f"/api/trash/task/{task_a_id}/restore", headers=h_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trash_counts(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """GET /api/trash/counts returns per-kind counts."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    # Initially empty.
    counts = (await aclient.get("/api/trash/counts", headers=h)).json()
    assert counts["tasks"] == 0
    assert counts["notes"] == 0

    # Delete task + note.
    tasks = (await aclient.get("/api/tasks", headers=h)).json()
    notes = (await aclient.get("/api/notes", headers=h)).json()
    await aclient.delete(f"/api/tasks/{tasks[0]['id']}", headers=h)
    await aclient.delete(f"/api/notes/{notes[0]['id']}", headers=h)

    counts = (await aclient.get("/api/trash/counts", headers=h)).json()
    assert counts["tasks"] == 1
    assert counts["notes"] == 1


@pytest.mark.asyncio
async def test_hard_delete_from_trash(
    aclient: httpx.AsyncClient,
    seeded_two_users: tuple[int, int],
) -> None:
    """DELETE /api/trash/{kind}/{id} permanently removes the item."""
    h = {"X-Telegram-Init-Data": _build_init_data(_TG_USER_A)}

    tasks = (await aclient.get("/api/tasks", headers=h)).json()
    task_id = tasks[0]["id"]
    await aclient.delete(f"/api/tasks/{task_id}", headers=h)

    # Hard-delete from trash.
    resp = await aclient.delete(f"/api/trash/task/{task_id}", headers=h)
    assert resp.status_code == 204

    # Gone from trash.
    trash = (await aclient.get("/api/trash", headers=h)).json()
    assert len(trash) == 0

    # Gone from DB.
    async with session_scope() as session:
        assert (await session.exec(select(Task).where(Task.id == task_id))).first() is None
