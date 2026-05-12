"""End-to-end pipeline tests with typical Russian phrases.

Each test sends a realistic Russian message through the full pipeline
(split → time → classify → persist) with all LLM calls mocked via respx.
The tests verify that the pipeline correctly:
- splits multi-intent messages
- classifies tasks vs notes
- persists results to the DB
- returns a courier-style reply
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from aiogram.types import InlineKeyboardMarkup
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.router import GroqKeyRouter
from app.bot.routers._pipeline import run_pipeline
from app.bot.services import get_or_create_category, get_or_create_user
from app.db.models import Note, Task

_FAKE_KEYS = ["gsk_test_key_1"]


def _kb_labels(kb: InlineKeyboardMarkup | None) -> list[str]:
    """Flatten the recognised-card keyboard to a list of button labels.

    PR-E moved the summary text into an inline keyboard, so the e2e
    assertions that used to look for ``"Купить хлеб" in reply`` now
    have to inspect the keyboard rows. The helper returns one label
    per row, in order; an empty list for ``None`` (no keyboard).
    """
    if kb is None:
        return []
    return [row[0].text for row in kb.inline_keyboard]


def _splitter_response(units: list[dict[str, str]]) -> dict[str, Any]:
    body = json.dumps({"units": units})
    return {
        "id": "chatcmpl-split",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    }


def _classifier_response(result: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(result)
    return {
        "id": "chatcmpl-class",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.3-70b-versatile",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
    }


def _reorder_response(is_reorder: bool = False) -> dict[str, Any]:
    payload = {
        "is_reorder": is_reorder,
        "task_query": None,
        "target_horizon": None,
        "target_raw": None,
    }
    body = json.dumps(payload)
    return {
        "id": "chatcmpl-reorder",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


def _courier_response(text: str) -> dict[str, Any]:
    body = json.dumps({"text": text})
    return {
        "id": "chatcmpl-courier",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    }


def _intent_response(intent: str = "create") -> dict[str, Any]:
    """Fake Groq response for the PR-I1 intent detection call."""
    payload: dict[str, Any] = {"intent": intent, "confidence": 0.95}
    body = json.dumps(payload)
    return {
        "id": "chatcmpl-intent",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.1-8b-instant",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": body}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 15, "total_tokens": 95},
    }


def _cr_dict(
    *,
    category: str,
    horizon: str = "today",
    priority: str = "medium",
    is_task: bool = True,
    confidence: float = 0.9,
    title: str,
) -> dict[str, Any]:
    return {
        "category_name": category,
        "horizon": horizon,
        "priority": priority,
        "is_task": is_task,
        "confidence": confidence,
        "title": title,
        "reminder_offsets": None,
    }


class _CallTracker:
    """Track respx calls and return staged responses in order."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._index = 0

    def side_effect(self, request: httpx.Request) -> httpx.Response:
        if self._index >= len(self._responses):
            raise RuntimeError(f"Unexpected LLM call #{self._index + 1}")
        resp = self._responses[self._index]
        self._index += 1
        return httpx.Response(200, json=resp)


# ── e2e: single task ─────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_single_task_morning_run(session: AsyncSession) -> None:
    """«утром пробежка» → 1 task in Здоровье/today."""
    user, _ = await get_or_create_user(session, telegram_id=300)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "утром пробежка"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="today", title="Утренняя пробежка")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "утром пробежка",
        tg_user_id=300,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text  # non-empty confirmation phrase
    assert any("Утренняя пробежка" in label for label in labels)
    assert any(label.startswith("\u2610 ") for label in labels)  # task prefix

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Утренняя пробежка"


# ── e2e: multiple tasks ──────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_multi_task_shopping_and_doctor(session: AsyncSession) -> None:
    """«купить хлеб и молоко, записаться к врачу» → 2 tasks."""
    user, _ = await get_or_create_user(session, telegram_id=301)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "купить хлеб и молоко"}, {"text": "записаться к врачу"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(_cr_dict(category="Покупки", title="Купить хлеб и молоко")),
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="week", title="Записаться к врачу")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "купить хлеб и молоко, записаться к врачу",
        tg_user_id=301,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert len(labels) == 2
    assert any("Купить хлеб и молоко" in label for label in labels)
    assert any("Записаться к врачу" in label for label in labels)

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 2


# ── e2e: task + note mix ─────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_task_and_note_mix(session: AsyncSession) -> None:
    """«позвонить Олегу, а ещё — книга про AI интересная» → task + note."""
    user, _ = await get_or_create_user(session, telegram_id=302)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "позвонить Олегу"}, {"text": "книга про AI интересная"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(_cr_dict(category="Личное", title="Позвонить Олегу")),
            _classifier_response(
                _cr_dict(
                    category="Хобби",
                    horizon="someday",
                    priority="low",
                    is_task=False,
                    title="Книга про AI интересная",
                )
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "позвонить Олегу, а ещё — книга про AI интересная",
        tg_user_id=302,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert len(labels) == 2
    # one row is a task (☐), the other is a note (📄)
    assert any(label.startswith("\u2610 ") for label in labels)
    assert any(label.startswith("\U0001f4c4 ") for label in labels)

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Позвонить Олегу"

    notes = (await session.exec(select(Note).where(Note.user_id == user.id))).all()
    assert len(notes) == 1
    assert notes[0].title == "Книга про AI интересная"


# ── e2e: work tasks with deadline ────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_work_report_by_friday(session: AsyncSession) -> None:
    """«до пятницы отчёт, в 11 совещание» → 2 tasks in Работа."""
    user, _ = await get_or_create_user(session, telegram_id=303)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "до пятницы отчёт"}, {"text": "в 11 совещание"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(
                _cr_dict(
                    category="Работа", horizon="week", priority="high", title="Отчёт до пятницы"
                )
            ),
            _classifier_response(
                _cr_dict(category="Работа", horizon="today", title="Совещание в 11")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "до пятницы отчёт, в 11 совещание",
        tg_user_id=303,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert len(labels) == 2
    assert any("Отчёт до пятницы" in label for label in labels)
    assert any("Совещание в 11" in label for label in labels)

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert "Отчёт до пятницы" in titles
    assert "Совещание в 11" in titles


# ── e2e: filler message (no tasks) ───────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_filler_message_no_tasks(session: AsyncSession) -> None:
    """«ну так, окей» → no tasks, polite reply."""
    user, _ = await get_or_create_user(session, telegram_id=304)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([]),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "ну так, окей",
        tg_user_id=304,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
    )

    assert "не нашёл" in text.lower()
    assert keyboard is None  # empty units → no recognised-card

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 0


# ── e2e: many items (complex message) ────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_complex_three_items(session: AsyncSession) -> None:
    """«утром йога, вечером ужин с друзьями, записать идею про стартап» → 2 tasks + 1 note."""
    user, _ = await get_or_create_user(session, telegram_id=305)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response(
                [
                    {"text": "утром йога"},
                    {"text": "вечером ужин с друзьями"},
                    {"text": "записать идею про стартап"},
                ]
            ),
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="today", title="Утренняя йога")
            ),
            _classifier_response(
                _cr_dict(category="Личное", horizon="today", title="Ужин с друзьями")
            ),
            _classifier_response(
                _cr_dict(
                    category="Идеи",
                    horizon="someday",
                    priority="low",
                    is_task=False,
                    title="Идея про стартап",
                )
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "утром йога, вечером ужин с друзьями, записать идею про стартап",
        tg_user_id=305,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert len(labels) == 3

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 2

    notes = (await session.exec(select(Note).where(Note.user_id == user.id))).all()
    assert len(notes) == 1


# ── e2e: single note ─────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_single_note(session: AsyncSession) -> None:
    """«интересная мысль про архитектуру проекта» → 1 note."""
    user, _ = await get_or_create_user(session, telegram_id=306)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "интересная мысль про архитектуру проекта"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(
                _cr_dict(
                    category="Работа",
                    horizon="someday",
                    priority="low",
                    is_task=False,
                    confidence=0.85,
                    title="Мысль про архитектуру",
                )
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "интересная мысль про архитектуру проекта",
        tg_user_id=306,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert any(label.startswith("\U0001f4c4 ") for label in labels)  # note prefix
    assert any("Мысль про архитектуру" in label for label in labels)

    notes = (await session.exec(select(Note).where(Note.user_id == user.id))).all()
    assert len(notes) == 1


# ── e2e: partial classify failure ────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_partial_classify_failure_does_not_kill_batch(
    session: AsyncSession,
) -> None:
    """Regression for C-3: a single Groq failure on one of two units must
    not wipe out the whole batch — the surviving unit should still be
    persisted and reported in the courier reply.
    """
    user, _ = await get_or_create_user(session, telegram_id=350)
    await session.commit()
    assert user.id is not None

    call_counter = {"n": 0}

    def staged(request: httpx.Request) -> httpx.Response:
        call_counter["n"] += 1
        n = call_counter["n"]
        if n == 1:
            # intent detection (PR-I1)
            return httpx.Response(200, json=_intent_response("create"))
        if n == 2:
            # reorder
            return httpx.Response(200, json=_reorder_response(False))
        if n == 3:
            # splitter
            return httpx.Response(
                200,
                json=_splitter_response(
                    [
                        {"text": "купить хлеб"},
                        {"text": "записаться к врачу"},
                    ]
                ),
            )
        if n == 4:
            # PR-I3: per-unit intent #1
            return httpx.Response(200, json=_intent_response("create"))
        if n == 5:
            # PR-I3: per-unit intent #2
            return httpx.Response(200, json=_intent_response("create"))
        if n == 6:
            # classifier #1 - succeeds
            return httpx.Response(
                200,
                json=_classifier_response(_cr_dict(category="Покупки", title="Купить хлеб")),
            )
        if n == 7:
            # classifier #2 — fails. Use 400 (not 429) so neither the Groq
            # SDK's internal retry policy nor ``call_with_rotation`` (I-1)
            # waits through exponential-backoff retries: 4xx is treated
            # as a request error and propagated immediately. The test's
            # intent is "one classifier raised, the other still persists"
            # — the specific error code doesn't matter, only that an
            # exception is raised. Switching from 429 → 400 cuts the
            # test runtime from ~2.8 s to ~1.5 s (M-8). Further
            # speed-up is bounded by ``instructor.max_retries=2`` on
            # the validation path; reducing that is the follow-up.
            return httpx.Response(
                400,
                json={"error": {"message": "bad request", "type": "invalid_request_error"}},
            )
        # any extra call (e.g. courier in template_only mode shouldn't happen)
        raise RuntimeError(f"Unexpected LLM call #{n}")  # pragma: no cover

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(side_effect=staged)

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "купить хлеб, записаться к врачу",
        tg_user_id=350,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    # Survivor is reported; failed unit is silently dropped.
    labels = _kb_labels(keyboard)
    assert text
    assert any("Купить хлеб" in label for label in labels)
    assert not any("Записаться к врачу" in label for label in labels)

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Купить хлеб"


# ── e2e: high-priority urgent task ───────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_urgent_task(session: AsyncSession) -> None:
    """«срочно! позвонить в банк до 15:00» → 1 high-priority task."""
    user, _ = await get_or_create_user(session, telegram_id=307)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _reorder_response(False),
            _splitter_response([{"text": "позвонить в банк до 15:00"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(
                _cr_dict(
                    category="Финансы",
                    horizon="today",
                    priority="high",
                    title="Позвонить в банк до 15:00",
                )
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "срочно! позвонить в банк до 15:00",
        tg_user_id=307,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    labels = _kb_labels(keyboard)
    assert text
    assert any(label.startswith("\u2610 ") for label in labels)
    assert any("Позвонить в банк" in label for label in labels)

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].priority == "high"


# ── e2e: classifier receives existing categories (R-NEW-C-4) ─────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_classifier_receives_user_existing_categories(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-C-4: ``run_pipeline`` must fetch the user's
    existing categories and pass them to ``classify_intent`` so the LLM
    can reuse them instead of inventing duplicates ("Работа" /
    "работа" / "Рабочее"). Before the fix the call site hard-coded an
    empty list and the categories table grew unbounded.

    We pre-seed two categories, run the pipeline against a captured
    Groq endpoint, and assert the classifier's request body includes
    both names.
    """
    user, _ = await get_or_create_user(session, telegram_id=400)
    await session.commit()
    assert user.id is not None

    # Seed two existing categories. The classifier prompt must surface
    # both so the LLM can reuse them.
    await get_or_create_category(session, user.id, "Работа")
    await get_or_create_category(session, user.id, "Здоровье")
    await session.commit()

    captured: list[httpx.Request] = []

    def side_effect(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        # First call is intent detection (PR-I1), then reorder, splitter,
        # PR-I3 per-unit intent, then classifier.
        if len(captured) == 1:
            return httpx.Response(200, json=_intent_response("create"))
        if len(captured) == 2:
            return httpx.Response(200, json=_reorder_response(False))
        if len(captured) == 3:
            return httpx.Response(
                200, json=_splitter_response([{"text": "доделать отчёт по работе"}])
            )
        if len(captured) == 4:
            # PR-I3: per-unit intent
            return httpx.Response(200, json=_intent_response("create"))
        return httpx.Response(
            200,
            json=_classifier_response(
                _cr_dict(category="Работа", title="Доделать отчёт по работе")
            ),
        )

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(side_effect=side_effect)

    await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "доделать отчёт по работе",
        tg_user_id=400,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    classifier_request = captured[4]  # shifted by 1 for PR-I3 per-unit intent
    body = classifier_request.read().decode()
    assert "Работа" in body, f"existing category 'Работа' missing from classifier prompt: {body!r}"
    assert "Здоровье" in body, (
        f"existing category 'Здоровье' missing from classifier prompt: {body!r}"
    )
    # Sanity: the bug ships the literal "existing_categories: []" payload.
    assert "existing_categories: []" not in body, (
        "classifier still receives empty user_categories — R-NEW-C-4 not fixed"
    )
