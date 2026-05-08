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
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.router import GroqKeyRouter
from app.bot.routers.text import _run_pipeline
from app.bot.services import get_or_create_user
from app.db.models import Note, Task

_FAKE_KEYS = ["gsk_test_key_1"]


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
            _reorder_response(False),
            _splitter_response([{"text": "утром пробежка"}]),
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="today", title="Утренняя пробежка")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "утром пробежка",
        tg_user_id=300,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "📌 задача" in reply
    assert "Утренняя пробежка" in reply

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
            _reorder_response(False),
            _splitter_response([{"text": "купить хлеб и молоко"}, {"text": "записаться к врачу"}]),
            _classifier_response(_cr_dict(category="Покупки", title="Купить хлеб и молоко")),
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="week", title="Записаться к врачу")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "купить хлеб и молоко, записаться к врачу",
        tg_user_id=301,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "2 элемента" in reply
    assert "Купить хлеб и молоко" in reply
    assert "Записаться к врачу" in reply

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
            _reorder_response(False),
            _splitter_response([{"text": "позвонить Олегу"}, {"text": "книга про AI интересная"}]),
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

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "позвонить Олегу, а ещё — книга про AI интересная",
        tg_user_id=302,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "📌 задача" in reply
    assert "📝 заметка" in reply
    assert "2 элемента" in reply

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
            _reorder_response(False),
            _splitter_response([{"text": "до пятницы отчёт"}, {"text": "в 11 совещание"}]),
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

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "до пятницы отчёт, в 11 совещание",
        tg_user_id=303,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "2 элемента" in reply
    assert "Отчёт до пятницы" in reply
    assert "Совещание в 11" in reply

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
            _reorder_response(False),
            _splitter_response([]),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "ну так, окей",
        tg_user_id=304,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
    )

    assert "не нашёл" in reply.lower()

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
            _reorder_response(False),
            _splitter_response(
                [
                    {"text": "утром йога"},
                    {"text": "вечером ужин с друзьями"},
                    {"text": "записать идею про стартап"},
                ]
            ),
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

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "утром йога, вечером ужин с друзьями, записать идею про стартап",
        tg_user_id=305,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "3 элемента" in reply

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
            _reorder_response(False),
            _splitter_response([{"text": "интересная мысль про архитектуру проекта"}]),
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

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "интересная мысль про архитектуру проекта",
        tg_user_id=306,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "📝 заметка" in reply
    assert "Мысль про архитектуру" in reply

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
            # reorder
            return httpx.Response(200, json=_reorder_response(False))
        if n == 2:
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
        if n == 3:
            # classifier #1 - succeeds
            return httpx.Response(
                200,
                json=_classifier_response(_cr_dict(category="Покупки", title="Купить хлеб")),
            )
        if n == 4:
            # classifier #2 - fails (rate limit)
            return httpx.Response(
                429,
                json={"error": {"message": "rate limit", "type": "rate_limit_exceeded"}},
            )
        # any extra call (e.g. courier in template_only mode shouldn't happen)
        raise RuntimeError(f"Unexpected LLM call #{n}")

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(side_effect=staged)

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "купить хлеб, записаться к врачу",
        tg_user_id=350,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    # Survivor is reported; failed unit is silently dropped.
    assert "Купить хлеб" in reply
    assert "Записаться к врачу" not in reply

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
            _reorder_response(False),
            _splitter_response([{"text": "позвонить в банк до 15:00"}]),
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

    reply = await _run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "срочно! позвонить в банк до 15:00",
        tg_user_id=307,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
    )

    assert "📌 задача" in reply
    assert "Позвонить в банк" in reply

    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].priority == "high"
