"""Tests for the Splitter. All Groq calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.router import GroqKeyRouter
from app.ai.schemas import SplitterResult
from app.ai.splitter import split_message

_FAKE_KEYS = ["gsk_test_key_1"]


def _groq_json(units: list[dict[str, str]]) -> dict[str, object]:
    """Fake Groq chat.completions JSON payload."""
    body = json.dumps({"units": units})
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    }


def _mock_groq(units: list[dict[str, str]]) -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(units)),
    )


@respx.mock
@pytest.mark.asyncio
async def test_split_multiple_intents() -> None:
    _mock_groq(
        [{"text": "утром пробежка"}, {"text": "в 11 совещание"}, {"text": "до пятницы отчёт"}]
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await split_message(router, "утром пробежка, в 11 совещание, до пятницы отчёт")
    assert isinstance(result, SplitterResult)
    assert len(result.units) == 3
    assert result.units[0].text == "утром пробежка"


@respx.mock
@pytest.mark.asyncio
async def test_split_single_intent() -> None:
    _mock_groq([{"text": "купить хлеб"}])
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await split_message(router, "купить хлеб")
    assert len(result.units) == 1
    assert result.units[0].text == "купить хлеб"


@pytest.mark.asyncio
async def test_split_empty_message_no_llm_call() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    assert (await split_message(router, "")).units == []
    assert (await split_message(router, "а")).units == []


@respx.mock
@pytest.mark.asyncio
async def test_split_filler_returns_empty() -> None:
    _mock_groq([])
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    assert (await split_message(router, "окей")).units == []


@respx.mock
@pytest.mark.asyncio
async def test_split_mixed_intents() -> None:
    _mock_groq([{"text": "позвонить маме"}, {"text": "заметка — книга про котов"}])
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await split_message(router, "позвонить маме, заметка — книга про котов")
    assert len(result.units) == 2
    assert "маме" in result.units[0].text
