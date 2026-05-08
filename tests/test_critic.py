"""Tests for the Critic. All Groq calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, CriticVerdict

_FAKE_KEYS = ["gsk_test_key_1"]


def _cr(
    *,
    confidence: float = 0.9,
    category: str = "Покупки",
    horizon: str = "someday",
    priority: str = "medium",
    is_task: bool = True,
    title: str = "Купить хлеб",
) -> ClassifierResult:
    return ClassifierResult(
        category_name=category,
        horizon=horizon,
        priority=priority,
        is_task=is_task,
        confidence=confidence,
        title=title,
        reminder_offsets=None,
    )


def _groq_json(result: dict[str, object]) -> dict[str, object]:
    body = json.dumps(result)
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "qwen-qwq-32b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": body},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 300, "completion_tokens": 80, "total_tokens": 380},
    }


def _mock_critic(result: dict[str, object]) -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(result)),
    )


# ── should_run_critic ─────────────────────────────────────────────────


def test_should_run_confidence_below_threshold() -> None:
    cr = _cr(confidence=0.5)
    assert should_run_critic(cr, critic_mode="confidence", confidence_threshold=0.7)


def test_should_not_run_confidence_above_threshold() -> None:
    cr = _cr(confidence=0.9)
    assert not should_run_critic(cr, critic_mode="confidence", confidence_threshold=0.7)


def test_should_run_always_mode() -> None:
    cr = _cr(confidence=0.99)
    assert should_run_critic(cr, critic_mode="always", confidence_threshold=0.7)


def test_should_not_run_unknown_mode() -> None:
    cr = _cr(confidence=0.5)
    assert not should_run_critic(cr, critic_mode="off", confidence_threshold=0.7)


# ── apply_verdict ─────────────────────────────────────────────────────


def test_apply_verdict_approved() -> None:
    cr = _cr()
    verdict = CriticVerdict(approved=True, reason="Всё верно", corrected=None)
    assert apply_verdict(cr, verdict) is cr


def test_apply_verdict_corrected() -> None:
    original = _cr(category="Личное")
    corrected = _cr(category="Покупки")
    verdict = CriticVerdict(
        approved=False,
        reason="Неправильная категория",
        corrected=corrected,
    )
    result = apply_verdict(original, verdict)
    assert result.category_name == "Покупки"
    assert result is not original


def test_apply_verdict_rejected_but_no_corrected() -> None:
    cr = _cr()
    verdict = CriticVerdict(approved=False, reason="Что-то не так", corrected=None)
    assert apply_verdict(cr, verdict) is cr


# ── critique_classification ───────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_critique_approved() -> None:
    _mock_critic(
        {
            "approved": True,
            "reason": "Классификация корректна.",
            "corrected": None,
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    cr = _cr()
    verdict = await critique_classification(router, "купить хлеб", cr, None, "Europe/Moscow")
    assert verdict.approved is True
    assert verdict.corrected is None


@respx.mock
@pytest.mark.asyncio
async def test_critique_corrected() -> None:
    _mock_critic(
        {
            "approved": False,
            "reason": "Горизонт неправильный — 'завтра' указывает на tomorrow.",
            "corrected": {
                "category_name": "Покупки",
                "horizon": "tomorrow",
                "priority": "medium",
                "is_task": True,
                "confidence": 0.92,
                "title": "Купить хлеб завтра",
                "reminder_offsets": None,
            },
        }
    )
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    cr = _cr(horizon="someday")
    verdict = await critique_classification(router, "завтра купить хлеб", cr, None, "Europe/Moscow")
    assert verdict.approved is False
    assert verdict.corrected is not None
    assert verdict.corrected.horizon == "tomorrow"
