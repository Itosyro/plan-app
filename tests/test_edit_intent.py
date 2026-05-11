"""Tests for PR-I1: edit intent detection + complete/delete/reopen executors."""

from __future__ import annotations

import json

import pytest
import respx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.intent import detect_intent
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, EditIntent
from app.bot.edit_executor import (
    EDIT_INTENTS_I1,
    _execute_complete,
    _execute_delete,
    _execute_reopen,
    execute_edit,
)
from app.bot.services import (
    find_tasks_by_query,
    get_or_create_user,
    mark_task_done,
    persist_classification,
)
from app.db.models import Task

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


def _mock_intent(intent: str, **kwargs: object) -> None:
    payload: dict[str, object] = {"intent": intent, "confidence": 0.95, **kwargs}
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(payload)),
    )


def _cr(
    title: str = "Купить хлеб",
    category: str = "Покупки",
    horizon: str = "today",
) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon=horizon,
        priority="medium",
        is_task=True,
        confidence=0.9,
        title=title,
    )


# ── EditIntent schema ────────────────────────────────────────────────


def test_edit_intent_schema_complete() -> None:
    intent = EditIntent(intent="complete", task_query="йога", confidence=0.95)
    assert intent.intent == "complete"
    assert intent.task_query == "йога"
    assert intent.new_horizon is None


def test_edit_intent_schema_create_default() -> None:
    intent = EditIntent(intent="create", confidence=0.9)
    assert intent.intent == "create"
    assert intent.task_query is None


def test_edit_intent_set_i1() -> None:
    assert "complete" in EDIT_INTENTS_I1
    assert "delete" in EDIT_INTENTS_I1
    assert "reopen" in EDIT_INTENTS_I1


# ── detect_intent (LLM mock) ────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_detect_intent_complete() -> None:
    _mock_intent("complete", task_query="йога")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_intent(router, "сделал йогу")
    assert result.intent == "complete"
    assert result.task_query == "йога"


@respx.mock
@pytest.mark.asyncio
async def test_detect_intent_delete() -> None:
    _mock_intent("delete", task_query="пробежку")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_intent(router, "удали пробежку")
    assert result.intent == "delete"


@respx.mock
@pytest.mark.asyncio
async def test_detect_intent_reopen() -> None:
    _mock_intent("reopen", task_query="йогу")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_intent(router, "верни йогу")
    assert result.intent == "reopen"


@respx.mock
@pytest.mark.asyncio
async def test_detect_intent_create() -> None:
    _mock_intent("create")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_intent(router, "утром пробежка 5 км")
    assert result.intent == "create"


@pytest.mark.asyncio
async def test_detect_intent_short_text() -> None:
    """Single-char text returns ``none`` without hitting the LLM."""
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await detect_intent(router, ".")
    assert result.intent == "none"


# ── find_tasks_by_query (multi-match) ────────────────────────────────


@pytest.mark.asyncio
async def test_find_tasks_by_query_multi(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=300)
    await session.commit()
    assert user.id is not None

    await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Утренняя пробежка"),
        due_at=None,
        inbox_id=None,
    )
    await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Вечерняя пробежка"),
        due_at=None,
        inbox_id=None,
    )
    await session.commit()

    matches = await find_tasks_by_query(session, user.id, "пробежка")
    assert len(matches) == 2


@pytest.mark.asyncio
async def test_find_tasks_by_query_includes_done(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=301)
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

    matches = await find_tasks_by_query(session, user.id, "хлеб")
    assert len(matches) == 0

    matches_all = await find_tasks_by_query(session, user.id, "хлеб", include_done=True)
    assert len(matches_all) == 1


# ── Executors (task_id based) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_complete(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=302)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Тестовая задача"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    reply = await _execute_complete(row.id, user.id)
    assert "Закрыл" in reply


@pytest.mark.asyncio
async def test_execute_complete_already_done(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=303)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Готовая задача"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    row.status = "done"
    session.add(row)
    await session.commit()

    reply = await _execute_complete(row.id, user.id)
    assert "уже" in reply


@pytest.mark.asyncio
async def test_execute_delete(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=304)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Удалить эту"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    reply = await _execute_delete(row.id, user.id)
    assert "Удалил" in reply


@pytest.mark.asyncio
async def test_execute_reopen(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=305)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Закрытая задача"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await mark_task_done(session, row, user.id)
    await session.commit()

    reply = await _execute_reopen(row.id, user.id)
    assert "Вернул" in reply


@pytest.mark.asyncio
async def test_execute_reopen_already_active(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=306)
    await session.commit()
    assert user.id is not None

    row = await persist_classification(
        session,
        user_id=user.id,
        cr=_cr("Активная задача"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(row, Task)
    assert row.id is not None
    await session.commit()

    reply = await _execute_reopen(row.id, user.id)
    assert "и так" in reply


# ── execute_edit dispatch ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_edit_no_query() -> None:
    intent = EditIntent(intent="complete", task_query="", confidence=0.9)
    reply, kb = await execute_edit(intent, user_id=1)
    assert "Не понял" in reply
    assert kb is None


@pytest.mark.asyncio
async def test_execute_edit_not_found(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=307)
    await session.commit()
    assert user.id is not None

    intent = EditIntent(intent="complete", task_query="несуществующая", confidence=0.9)
    reply, _kb = await execute_edit(intent, user.id)
    assert "Не нашёл" in reply
