"""Tests for Phase 2.3d: reorder detection + task horizon update."""

from __future__ import annotations

import json

import pytest
import respx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.reorder import detect_reorder
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ReorderRequest
from app.bot.services import (
    find_task_by_query,
    get_or_create_user,
    persist_classification,
    update_task_horizon,
)
from app.db.models import Horizon, Task, TaskEvent

_FAKE_KEYS = ["gsk_test_key_1"]


def _groq_json(payload: dict[str, object]) -> dict[str, object]:
    """Build a fake Groq chat completion response."""
    body = json.dumps(payload)
    return {
        "id": "chatcmpl-test",
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
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


def _mock_reorder(
    is_reorder: bool,
    task_query: str | None = None,
    target_horizon: str | None = None,
    target_raw: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "is_reorder": is_reorder,
        "task_query": task_query,
        "target_horizon": target_horizon,
        "target_raw": target_raw,
    }
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(payload)),
    )


def _cr(
    title: str = "Купить хлеб", category: str = "Покупки", horizon: str = "today"
) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon=horizon,
        priority="medium",
        is_task=True,
        confidence=0.9,
        title=title,
    )


# ── ReorderRequest schema ────────────────────────────────────────────


def test_reorder_request_not_reorder() -> None:
    req = ReorderRequest(is_reorder=False, task_query=None, target_horizon=None, target_raw=None)
    assert not req.is_reorder
    assert req.task_query is None


def test_reorder_request_is_reorder() -> None:
    req = ReorderRequest(
        is_reorder=True, task_query="пробежка", target_horizon="tomorrow", target_raw="на завтра"
    )
    assert req.is_reorder
    assert req.task_query == "пробежка"
    assert req.target_horizon == "tomorrow"


# ── detect_reorder (LLM mock) ────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_detect_reorder_positive() -> None:
    _mock_reorder(True, "пробежка", "tomorrow", "на завтра")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_reorder(router, "перенеси пробежку на завтра")
    assert result.is_reorder
    assert result.task_query == "пробежка"
    assert result.target_horizon == "tomorrow"


@respx.mock
@pytest.mark.asyncio
async def test_detect_reorder_negative() -> None:
    _mock_reorder(False)
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_reorder(router, "купить хлеб и молоко")
    assert not result.is_reorder


@pytest.mark.asyncio
async def test_detect_reorder_short_text() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_reorder(router, "ок")
    assert not result.is_reorder


# ── find_task_by_query (DB) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_task_by_query_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=200)
    await session.commit()
    assert user.id is not None

    await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Утренняя пробежка", "Здоровье"),
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    task = await find_task_by_query(session, user.id, "пробежка")
    assert task is not None
    assert "пробежка" in task.title.lower()


@pytest.mark.asyncio
async def test_find_task_by_query_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=201)
    await session.commit()
    assert user.id is not None

    task = await find_task_by_query(session, user.id, "несуществующая")
    assert task is None


@pytest.mark.asyncio
async def test_find_task_excludes_done(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=202)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Купить хлеб"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    row.status = "done"
    session.add(row)
    await session.commit()

    task = await find_task_by_query(session, user.id, "хлеб")
    assert task is None


# ── update_task_horizon (DB) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_task_horizon(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=203)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Совещание", "Работа", "today"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    old_horizon_id = row.horizon_id
    await session.commit()

    updated = await update_task_horizon(session, row, "week", user.id)
    await session.commit()

    assert updated.horizon_id != old_horizon_id

    new_hor = await session.get(Horizon, updated.horizon_id)
    assert new_hor is not None
    assert new_hor.slug == "week"

    events = (
        await session.exec(
            select(TaskEvent).where(TaskEvent.task_id == row.id, TaskEvent.kind == "reordered"),
        )
    ).all()
    assert len(events) == 1
    assert events[0].payload_json is not None
    assert events[0].payload_json["new_horizon_slug"] == "week"
