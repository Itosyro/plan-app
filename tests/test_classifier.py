"""Tests for the Classifier. All Groq calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.classifier import classify_intent
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ResolvedTime

_FAKE_KEYS = ["gsk_test_key_1"]


def _groq_json(result: dict[str, object]) -> dict[str, object]:
    """Fake Groq chat.completions JSON payload."""
    body = json.dumps(result)
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.3-70b-versatile",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
    }


def _mock_groq(result: dict[str, object]) -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(result)),
    )


@respx.mock
@pytest.mark.asyncio
async def test_classify_task_with_time() -> None:
    _mock_groq(
        {
            "category_name": "здоровье",
            "horizon": "today",
            "priority": "medium",
            "is_task": True,
            "confidence": 0.9,
            "title": "пробежка",
            "reminder_offsets": None,
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    resolved = ResolvedTime(
        original_text="утром",
        resolved_dt=datetime(2026, 5, 9, 8, 0, tzinfo=ZoneInfo("Europe/Moscow")),
        is_reminder=False,
        horizon_hint="today",
    )
    result = await classify_intent(
        router,
        "утром пробежка",
        resolved,
        [],
        "Europe/Moscow",
    )
    assert isinstance(result, ClassifierResult)
    assert result.is_task is True
    assert result.category_name == "здоровье"
    assert result.horizon == "today"


@respx.mock
@pytest.mark.asyncio
async def test_classify_note_without_time() -> None:
    _mock_groq(
        {
            "category_name": "хобби",
            "horizon": "someday",
            "priority": "low",
            "is_task": False,
            "confidence": 0.85,
            "title": "книга про котов",
            "reminder_offsets": None,
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await classify_intent(
        router,
        "книга про котов интересная",
        None,
        ["работа"],
        "Europe/Moscow",
    )
    assert result.is_task is False
    assert result.priority == "low"
    assert result.horizon == "someday"


@respx.mock
@pytest.mark.asyncio
async def test_classify_new_category() -> None:
    _mock_groq(
        {
            "category_name": "покупки",
            "horizon": "someday",
            "priority": "medium",
            "is_task": True,
            "confidence": 0.92,
            "title": "купить хлеб",
            "reminder_offsets": None,
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await classify_intent(
        router,
        "купить хлеб",
        None,
        ["работа", "здоровье"],
        "Europe/Moscow",
    )
    assert result.category_name == "покупки"
    assert result.is_task is True


@respx.mock
@pytest.mark.asyncio
async def test_classify_low_confidence() -> None:
    _mock_groq(
        {
            "category_name": "личное",
            "horizon": "someday",
            "priority": "medium",
            "is_task": True,
            "confidence": 0.55,
            "title": "что-то непонятное",
            "reminder_offsets": None,
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await classify_intent(
        router,
        "ну типа вот это вот",
        None,
        [],
        "Europe/Moscow",
    )
    assert result.confidence < 0.7
