"""Tests for the Courier module. LLM calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx

from app.ai.courier import (
    TEMPLATES,
    SummaryItem,
    build_check_keyboard,
    build_summary,
    courier_respond,
    generate_courier_reply,
)
from app.ai.router import GroqKeyRouter

_FAKE_KEYS = ["gsk_test_key_1"]


def _si(
    *,
    item_id: int = 1,
    kind: str = "task",
    title: str = "Купить хлеб",
    category_name: str = "Покупки",
    done: bool = False,
) -> SummaryItem:
    return SummaryItem(
        item_id=item_id,
        kind=kind,
        title=title,
        category_name=category_name,
        done=done,
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
    result = build_summary([_si(title="Купить хлеб", category_name="Покупки")])
    assert "задача" in result
    assert "Купить хлеб" in result
    assert "Покупки" in result
    assert "1 элемент" in result


def test_build_summary_mixed() -> None:
    items = [
        _si(item_id=1, kind="task", title="Пробежка", category_name="Здоровье"),
        _si(item_id=2, kind="note", title="Заметка про книгу", category_name="Чтение"),
    ]
    summary = build_summary(items)
    assert "задача" in summary
    assert "заметка" in summary
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
    items = [_si(title="Пробежка", category_name="Здоровье")]
    result = await courier_respond(router, items, mode="template_only", style="terse")
    assert "задача" in result.text
    assert "Пробежка" in result.text
    first_line = result.text.split("\n")[0]
    assert first_line in TEMPLATES["terse"]


@pytest.mark.asyncio
async def test_courier_respond_empty_results() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    result = await courier_respond(router, [], mode="template_only", style="neutral")
    assert result.text in TEMPLATES["neutral"]
    assert "☐" not in result.text


@respx.mock
@pytest.mark.asyncio
async def test_courier_respond_llm_with_summary() -> None:
    _mock_courier("Готово, мой господин!")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    items = [
        _si(item_id=1, title="Совещание", category_name="Работа"),
        _si(item_id=2, title="Звонок маме", category_name="Личное"),
    ]
    result = await courier_respond(router, items, mode="llm_only", style="formal_master")
    assert "Готово, мой господин!" in result.text
    assert "задача" in result.text
    assert "Совещание" in result.text
    assert "Звонок маме" in result.text


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


# \u2500\u2500 build_check_keyboard \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500


def test_build_check_keyboard_empty() -> None:
    assert build_check_keyboard([]) is None


def test_build_check_keyboard_single_task() -> None:
    items = [
        _si(
            item_id=42,
            kind="task",
            title="\u041a\u0443\u043f\u0438\u0442\u044c \u0445\u043b\u0435\u0431",
        )
    ]
    kb = build_check_keyboard(items)
    assert kb is not None
    assert len(kb.inline_keyboard) == 1
    btn = kb.inline_keyboard[0][0]
    assert "\u2610" in btn.text
    assert "\u041a\u0443\u043f\u0438\u0442\u044c \u0445\u043b\u0435\u0431" in btn.text
    assert btn.callback_data == "summary:toggle:task:42"


def test_build_check_keyboard_done_item() -> None:
    items = [_si(item_id=7, kind="task", title="\u0413\u043e\u0442\u043e\u0432\u043e", done=True)]
    kb = build_check_keyboard(items)
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert "\u2611" in btn.text


def test_build_check_keyboard_mixed() -> None:
    items = [
        _si(item_id=1, kind="task", title="\u0417\u0430\u0434\u0430\u0447\u0430"),
        _si(item_id=2, kind="note", title="\u0417\u0430\u043c\u0435\u0442\u043a\u0430"),
    ]
    kb = build_check_keyboard(items)
    assert kb is not None
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "summary:toggle:task:1"
    assert kb.inline_keyboard[1][0].callback_data == "summary:toggle:note:2"


def test_build_check_keyboard_long_title_truncated() -> None:
    long_title = "\u0410" * 100
    items = [_si(item_id=1, title=long_title)]
    kb = build_check_keyboard(items)
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert len(btn.text) <= 60


@pytest.mark.asyncio
async def test_courier_respond_returns_items() -> None:
    """courier_respond should return items in the result."""
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    items = [
        _si(
            item_id=1,
            title="\u041f\u0440\u043e\u0431\u0435\u0436\u043a\u0430",
            category_name="\u0417\u0434\u043e\u0440\u043e\u0432\u044c\u0435",
        )
    ]
    result = await courier_respond(router, items, mode="template_only", style="terse")
    assert len(result.items) == 1
    assert result.items[0].title == "\u041f\u0440\u043e\u0431\u0435\u0436\u043a\u0430"
