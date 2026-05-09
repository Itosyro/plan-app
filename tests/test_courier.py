"""Tests for the Courier module. LLM calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.courier import (
    TEMPLATES,
    build_summary,
    courier_respond,
    generate_courier_reply,
)
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult

_FAKE_KEYS = ["gsk_test_key_1"]


def _cr(
    *,
    category: str = "Покупки",
    horizon: str = "today",
    priority: str = "medium",
    is_task: bool = True,
    title: str = "Купить хлеб",
    confidence: float = 0.9,
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


def _groq_json(text: str) -> dict[str, object]:
    body = json.dumps({"text": text})
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


def _mock_courier(text: str) -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=respx.MockResponse(200, json=_groq_json(text)),
    )


# ── TEMPLATES ────────────────────────────────────────────────────────


def test_templates_all_styles_have_at_least_five() -> None:
    expected_styles = {"neutral", "formal_master", "friendly", "playful", "terse", "respectful"}
    assert set(TEMPLATES.keys()) == expected_styles
    for style, phrases in TEMPLATES.items():
        assert len(phrases) >= 5, f"Style '{style}' has only {len(phrases)} templates"


def test_templates_total_at_least_thirty() -> None:
    total = sum(len(v) for v in TEMPLATES.values())
    assert total >= 30


# ── build_summary ────────────────────────────────────────────────────


def test_build_summary_empty() -> None:
    assert build_summary([]) == ""


def test_build_summary_single_task() -> None:
    result = build_summary([_cr(title="Купить хлеб", category="Покупки")])
    assert "📌 задача" in result
    assert "Купить хлеб" in result
    assert "Покупки" in result
    assert "1 элемент" in result


def test_build_summary_mixed() -> None:
    results = [
        _cr(title="Пробежка", category="Здоровье", is_task=True),
        _cr(title="Заметка про книгу", category="Чтение", is_task=False),
    ]
    summary = build_summary(results)
    assert "📌 задача" in summary
    assert "📝 заметка" in summary
    assert "2 элемента" in summary


# ── generate_courier_reply (template_only) ────────────────────────────


@pytest.mark.asyncio
async def test_generate_reply_template_only() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    reply = await generate_courier_reply(router, "neutral", mode="template_only")
    assert reply in TEMPLATES["neutral"]


@pytest.mark.asyncio
async def test_generate_reply_template_only_formal() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    reply = await generate_courier_reply(router, "formal_master", mode="template_only")
    assert reply in TEMPLATES["formal_master"]


# ── generate_courier_reply (llm_only) ────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_generate_reply_llm_only() -> None:
    _mock_courier("Принял к сведению, всё записано!")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    reply = await generate_courier_reply(router, "neutral", mode="llm_only")
    assert reply == "Принял к сведению, всё записано!"


# ── courier_respond (full) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_courier_respond_template_with_summary() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    results = [_cr(title="Пробежка", category="Здоровье")]
    reply = await courier_respond(router, results, mode="template_only", style="terse")
    assert "📌 задача" in reply
    assert "Пробежка" in reply
    # confirmation is on the first line
    first_line = reply.split("\n")[0]
    assert first_line in TEMPLATES["terse"]


@pytest.mark.asyncio
async def test_courier_respond_empty_results() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    reply = await courier_respond(router, [], mode="template_only", style="neutral")
    assert reply in TEMPLATES["neutral"]
    assert "📌" not in reply


@respx.mock
@pytest.mark.asyncio
async def test_courier_respond_llm_with_summary() -> None:
    _mock_courier("Готово, мой господин!")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    results = [
        _cr(title="Совещание", category="Работа"),
        _cr(title="Звонок маме", category="Личное"),
    ]
    reply = await courier_respond(router, results, mode="llm_only", style="formal_master")
    assert "Готово, мой господин!" in reply
    assert "📌 задача" in reply
    assert "Совещание" in reply
    assert "Звонок маме" in reply


# ── C-1 regression: unknown mode degrades to template_only ───────────


@pytest.mark.asyncio
async def test_generate_reply_unknown_mode_falls_back_to_template() -> None:
    """C-1 regression: pre-2026-05-09 the UI shipped ``formal``/``casual``
    as ``response_style_source`` values. Those silently fell through both
    ``if`` branches in :func:`generate_courier_reply` and degenerated to
    template-only output. The allow-list now rejects them at write-time
    (see ``test_settings.py``), but :func:`generate_courier_reply` should
    still degrade safely if a stale value somehow reaches it — i.e. it
    must NOT crash and must NOT call the LLM.
    """
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    # If this hit the LLM, respx (not @respx.mock here) would surface an
    # unmocked-request error. Reaching template branch keeps the test
    # offline.
    reply = await generate_courier_reply(router, "neutral", mode="formal")
    assert reply in TEMPLATES["neutral"]


@pytest.mark.asyncio
async def test_generate_reply_unknown_style_falls_back_to_neutral() -> None:
    """C-1 companion: an unknown *style* (e.g. typo, drift between
    keyboard and TEMPLATES) must fall back to ``neutral`` rather than
    raising ``KeyError``.
    """
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    reply = await generate_courier_reply(router, "totally-unknown-style", mode="template_only")
    assert reply in TEMPLATES["neutral"]
