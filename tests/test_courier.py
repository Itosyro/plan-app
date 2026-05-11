"""Tests for the Courier module. LLM calls mocked via respx."""

from __future__ import annotations

import json

import pytest
import respx
from aiogram.types import InlineKeyboardMarkup

from app.ai.courier import (
    NOTE_PREFIX,
    TASK_DONE_PREFIX,
    TASK_PENDING_PREFIX,
    TEMPLATES,
    SummaryItem,
    build_summary,
    build_summary_keyboard,
    courier_respond,
    flip_item,
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


def _item(
    *,
    kind: str = "task",
    title: str = "Купить хлеб",
    category: str = "Покупки",
    persisted_id: int = 1,
    status: str = "pending",
) -> SummaryItem:
    return SummaryItem(
        kind=kind,  # type: ignore[arg-type]
        title=title,
        category_name=category,
        persisted_id=persisted_id,
        status=status,  # type: ignore[arg-type]
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


def test_templates_no_emoji_parade() -> None:
    """PR-E: at most ONE emoji per template phrase.

    The previous ``playful`` set strung 🤖 / 🥷 / 🧠 together in a single
    line; the user explicitly asked us to stop. We count any character
    in the supplementary-emoji ranges; anything > 1 per template fails.
    """

    def _emoji_count(text: str) -> int:
        count = 0
        for ch in text:
            code = ord(ch)
            if (
                0x1F300 <= code <= 0x1FAFF  # Misc symbols & pictographs … extended
                or 0x2600 <= code <= 0x27BF  # Misc symbols + dingbats
                or 0x1F000 <= code <= 0x1F2FF  # Mahjong, regional indicators, etc.
            ):
                count += 1
        return count

    offenders: list[tuple[str, str, int]] = []
    for style, phrases in TEMPLATES.items():
        for phrase in phrases:
            count = _emoji_count(phrase)
            if count > 1:
                offenders.append((style, phrase, count))
    assert not offenders, f"templates with >1 emoji: {offenders}"


def test_templates_no_dry_acks() -> None:
    """PR-E: drop sterile single-word ack templates like 'Принял.'.

    The user's only hard constraint here was the *dry* / robotic
    "Принял" / "Записал" pair (HANDOFF v13 §1.3). Short variants are
    still allowed for the ``terse`` style — we only fail on the exact
    "Принял." / "Записал." strings.
    """
    forbidden = {"Принял.", "Записал."}
    for style, phrases in TEMPLATES.items():
        for phrase in phrases:
            assert phrase not in forbidden, f"dry ack '{phrase}' in style '{style}'"


# ── build_summary (legacy text helper) ────────────────────────────────


def test_build_summary_empty() -> None:
    assert build_summary([]) == ""


def test_build_summary_single_task() -> None:
    result = build_summary([_cr(title="Купить хлеб", category="Покупки")])
    assert "Задача" in result
    assert "Купить хлеб" in result
    assert "Покупки" in result
    assert "1 элемент" in result


def test_build_summary_mixed() -> None:
    results = [
        _cr(title="Пробежка", category="Здоровье", is_task=True),
        _cr(title="Заметка про книгу", category="Чтение", is_task=False),
    ]
    summary = build_summary(results)
    assert "Задача" in summary
    assert "Заметка" in summary
    assert "2 элемента" in summary


# ── build_summary_keyboard ────────────────────────────────────────────


def test_build_summary_keyboard_one_row_per_item() -> None:
    items = [
        _item(kind="task", title="Купить хлеб", category="Покупки", persisted_id=11),
        _item(kind="task", title="Позвонить маме", category="Личное", persisted_id=12),
        _item(kind="note", title="Идея про книгу", category="Идеи", persisted_id=21),
    ]
    kb = build_summary_keyboard(items)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 3
    for row in kb.inline_keyboard:
        assert len(row) == 1


def test_build_summary_keyboard_callback_data_format() -> None:
    items = [
        _item(kind="task", persisted_id=42),
        _item(kind="note", persisted_id=99),
    ]
    kb = build_summary_keyboard(items)
    callbacks = [row[0].callback_data for row in kb.inline_keyboard]
    assert callbacks == ["summary:toggle:task:42", "summary:toggle:note:99"]


def test_build_summary_keyboard_prefixes() -> None:
    items = [
        _item(kind="task", title="Pending task", status="pending", persisted_id=1),
        _item(kind="task", title="Done task", status="done", persisted_id=2),
        _item(kind="note", title="Some note", persisted_id=3),
    ]
    kb = build_summary_keyboard(items)
    labels = [row[0].text for row in kb.inline_keyboard]
    assert labels[0].startswith(TASK_PENDING_PREFIX)
    assert labels[1].startswith(TASK_DONE_PREFIX)
    assert labels[2].startswith(NOTE_PREFIX)


def test_build_summary_keyboard_trims_long_titles() -> None:
    long_title = "очень длинное название задачи которое должно быть обрезано до 40 символов"
    items = [_item(kind="task", title=long_title, category="Х", persisted_id=1)]
    kb = build_summary_keyboard(items)
    label = kb.inline_keyboard[0][0].text
    # Prefix + trimmed-title + " · " + category. We don't pin a hard
    # length but the title chunk must end with the ellipsis.
    assert "\u2026" in label


def test_build_summary_keyboard_empty() -> None:
    kb = build_summary_keyboard([])
    assert isinstance(kb, InlineKeyboardMarkup)
    assert kb.inline_keyboard == []


# ── flip_item ─────────────────────────────────────────────────────────


def test_flip_item_pending_to_done() -> None:
    items = [_item(kind="task", persisted_id=1, status="pending")]
    flipped = flip_item(items, target_id=1, kind="task")
    assert flipped[0].status == "done"


def test_flip_item_done_to_pending() -> None:
    items = [_item(kind="task", persisted_id=1, status="done")]
    flipped = flip_item(items, target_id=1, kind="task")
    assert flipped[0].status == "pending"


def test_flip_item_non_matching_unchanged() -> None:
    items = [
        _item(kind="task", persisted_id=1, status="pending"),
        _item(kind="task", persisted_id=2, status="pending"),
        _item(kind="note", persisted_id=3),
    ]
    flipped = flip_item(items, target_id=2, kind="task")
    assert flipped[0].status == "pending"
    assert flipped[1].status == "done"
    assert flipped[2].kind == "note"


def test_flip_item_note_kind_is_inert() -> None:
    items = [_item(kind="note", persisted_id=5, status="pending")]
    flipped = flip_item(items, target_id=5, kind="note")
    assert flipped[0].status == "pending"  # Notes don't toggle.


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


# ── courier_respond (returns tuple in PR-E) ───────────────────────────


@pytest.mark.asyncio
async def test_courier_respond_template_with_items() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    items = [_item(kind="task", title="Пробежка", category="Здоровье", persisted_id=1)]
    text, keyboard = await courier_respond(router, items, mode="template_only", style="terse")
    # Confirmation phrase comes from the templates, summary lives in
    # the keyboard now.
    assert text in TEMPLATES["terse"]
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_courier_respond_empty_items_no_keyboard() -> None:
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    text, keyboard = await courier_respond(router, [], mode="template_only", style="neutral")
    assert text in TEMPLATES["neutral"]
    assert keyboard is None


@respx.mock
@pytest.mark.asyncio
async def test_courier_respond_llm_with_items() -> None:
    _mock_courier("Готово, мой господин!")
    router = GroqKeyRouter(keys=_FAKE_KEYS)
    items = [
        _item(kind="task", title="Совещание", category="Работа", persisted_id=1),
        _item(kind="task", title="Звонок маме", category="Личное", persisted_id=2),
    ]
    text, keyboard = await courier_respond(router, items, mode="llm_only", style="formal_master")
    assert text == "Готово, мой господин!"
    assert keyboard is not None
    labels = [row[0].text for row in keyboard.inline_keyboard]
    assert any("Совещание" in label for label in labels)
    assert any("Звонок маме" in label for label in labels)


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
