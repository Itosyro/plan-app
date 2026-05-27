"""Tests for the Critic. All Groq calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, CriticVerdict, FieldCheck

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


# ── CriticVerdict.checks (per-field CoT) ──────────────────────────────


def test_verdict_checks_default_empty() -> None:
    verdict = CriticVerdict(approved=True, reason="ок", corrected=None)
    assert verdict.checks == []


def test_verdict_checks_roundtrip() -> None:
    verdict = CriticVerdict(
        checks=[
            FieldCheck(field="is_task", ok=True, note="это задача"),
            FieldCheck(field="horizon", ok=False, note="должно быть tomorrow"),
        ],
        approved=False,
        reason="неверный горизонт",
        corrected=_cr(horizon="tomorrow"),
    )
    dumped = verdict.model_dump_json()
    restored = CriticVerdict.model_validate_json(dumped)
    assert len(restored.checks) == 2
    assert restored.checks[0].field == "is_task"
    assert restored.checks[0].ok is True
    assert restored.checks[1].field == "horizon"
    assert restored.checks[1].ok is False


def test_verdict_validates_without_checks() -> None:
    restored = CriticVerdict.model_validate_json(
        '{"approved": true, "reason": "ок", "corrected": null}'
    )
    assert restored.checks == []


# ── apply_verdict ─────────────────────────────────────────────────────


def test_apply_verdict_approved() -> None:
    cr = _cr()
    verdict = CriticVerdict(
        checks=[FieldCheck(field="horizon", ok=True, note="верно")],
        approved=True,
        reason="Всё верно",
        corrected=None,
    )
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
            "checks": [
                {"field": "is_task", "ok": True, "note": "это задача"},
                {"field": "horizon", "ok": True, "note": "someday корректно"},
            ],
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
    assert len(verdict.checks) == 2
    assert all(c.ok for c in verdict.checks)
    # all-ok / approved → apply_verdict returns the original unchanged
    assert apply_verdict(cr, verdict) is cr


@respx.mock
@pytest.mark.asyncio
async def test_critique_corrected() -> None:
    _mock_critic(
        {
            "checks": [
                {"field": "is_task", "ok": True, "note": "это задача"},
                {"field": "horizon", "ok": False, "note": "'завтра' → tomorrow, не someday"},
            ],
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
    # a failing check (ok=False) drives the correction through apply_verdict
    assert any(not c.ok for c in verdict.checks)
    assert apply_verdict(cr, verdict).horizon == "tomorrow"
