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

from typing import Any

import httpx
import pytest
import respx
from aiogram.types import InlineKeyboardMarkup
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.router import GroqKeyRouter
from app.bot.routers._pipeline import (
    _plural_ru,
    flag_needs_review,
    run_pipeline,
)
from app.bot.services import get_or_create_category, get_or_create_user
from app.db.models import InboxEntry, Note, Task
from tests._groq_mock import groq_tool_response

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
    return groq_tool_response("SplitterResult", {"units": units})


def _classifier_response(result: dict[str, Any]) -> dict[str, Any]:
    return groq_tool_response("ClassifierResult", result)


def _courier_response(text: str) -> dict[str, Any]:
    return groq_tool_response("CourierReply", {"text": text})


def _critic_response(result: dict[str, Any]) -> dict[str, Any]:
    return groq_tool_response(
        "CriticVerdict", {"approved": True, "reason": "ok", "corrected": result}
    )


def _intent_response(intent: str = "create") -> dict[str, Any]:
    """Fake Groq response for the PR-I1 intent detection call."""
    return groq_tool_response("EditIntent", {"intent": intent, "confidence": 0.95})


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
            _splitter_response([{"text": "утром пробежка"}]),
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


@respx.mock
@pytest.mark.asyncio
async def test_e2e_low_confidence_persists_and_flags_review(session: AsyncSession) -> None:
    """Low-confidence result is persisted immediately (вариант Б) and its
    inbox entry is flagged for the «Входящие» review tab — no in-chat
    «создать? да/нет» prompt anymore."""
    user, _ = await get_or_create_user(session, telegram_id=309)
    await session.commit()
    assert user.id is not None

    entry = InboxEntry(user_id=user.id, kind="voice", transcript="созвон с командой")
    session.add(entry)
    await session.commit()
    assert entry.id is not None
    entry_id = entry.id

    low_conf = _cr_dict(
        category="Работа",
        horizon="today",
        title="Созвон с командой",
        confidence=0.4,
    )
    tracker = _CallTracker(
        [
            _intent_response("create"),
            _splitter_response([{"text": "созвон с командой"}]),
            _classifier_response(low_conf),
            _critic_response(low_conf),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, _keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "созвон с командой",
        tg_user_id=309,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=entry_id,
        courier_mode="template_only",
    )

    # No clarification prompt; instead a pointer to the review tab.
    assert "Я не совсем уверен" not in text
    assert "Входящие" in text

    # The task exists right away.
    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Созвон с командой"

    # The inbox entry is flagged for review.
    session.expire_all()
    refreshed = await session.get(InboxEntry, entry_id)
    assert refreshed is not None
    assert refreshed.needs_review is True


@respx.mock
@pytest.mark.asyncio
async def test_e2e_low_confidence_review_disabled_does_not_flag(
    session: AsyncSession,
) -> None:
    """With ``review_enabled=False`` the same low-confidence message
    persists its task but the inbox entry stays unflagged and the reply
    omits the «Входящие» review pointer."""
    user, _ = await get_or_create_user(session, telegram_id=310)
    await session.commit()
    assert user.id is not None

    entry = InboxEntry(user_id=user.id, kind="voice", transcript="созвон с командой")
    session.add(entry)
    await session.commit()
    assert entry.id is not None
    entry_id = entry.id

    low_conf = _cr_dict(
        category="Работа",
        horizon="today",
        title="Созвон с командой",
        confidence=0.4,
    )
    tracker = _CallTracker(
        [
            _intent_response("create"),
            _splitter_response([{"text": "созвон с командой"}]),
            _classifier_response(low_conf),
            _critic_response(low_conf),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, _keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "созвон с командой",
        tg_user_id=310,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=entry_id,
        courier_mode="template_only",
        review_enabled=False,
    )

    # No review pointer when the gate is off.
    assert "Входящие" not in text

    # The task still exists right away.
    tasks = (await session.exec(select(Task).where(Task.user_id == user.id))).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Созвон с командой"

    # The inbox entry is NOT flagged for review.
    session.expire_all()
    refreshed = await session.get(InboxEntry, entry_id)
    assert refreshed is not None
    assert refreshed.needs_review is False


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
            # PR-I3: per-unit intent #1
            return httpx.Response(200, json=_intent_response("create"))
        if n == 4:
            # PR-I3: per-unit intent #2
            return httpx.Response(200, json=_intent_response("create"))
        if n == 5:
            # classifier #1 - succeeds
            return httpx.Response(
                200,
                json=_classifier_response(_cr_dict(category="Покупки", title="Купить хлеб")),
            )
        if n == 6:
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


# ── e2e: two notes flag the entry for review ─────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_two_notes_flag_review(session: AsyncSession) -> None:
    """Two notes (no tasks) from one inbox entry still trigger
    ``needs_review`` — the count now covers tasks + notes."""
    user, _ = await get_or_create_user(session, telegram_id=311)
    await session.commit()
    assert user.id is not None

    entry = InboxEntry(user_id=user.id, kind="text", raw_text="две заметки")
    session.add(entry)
    await session.commit()
    assert entry.id is not None
    entry_id = entry.id

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _splitter_response([{"text": "мысль один"}, {"text": "мысль два"}]),
            _intent_response("create"),
            _intent_response("create"),
            _classifier_response(
                _cr_dict(
                    category="Идеи",
                    horizon="someday",
                    priority="low",
                    is_task=False,
                    title="Мысль один",
                )
            ),
            _classifier_response(
                _cr_dict(
                    category="Идеи",
                    horizon="someday",
                    priority="low",
                    is_task=False,
                    title="Мысль два",
                )
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    text, _keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "мысль один, мысль два",
        tg_user_id=311,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=entry_id,
        courier_mode="template_only",
    )

    assert "Входящие" in text

    notes = (await session.exec(select(Note).where(Note.user_id == user.id))).all()
    assert len(notes) == 2

    session.expire_all()
    refreshed = await session.get(InboxEntry, entry_id)
    assert refreshed is not None
    assert refreshed.needs_review is True


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
        # First call is intent detection (PR-I1), then splitter, then
        # classifier. Single-unit messages short-circuit the per-unit
        # intent pass.
        if len(captured) == 1:
            return httpx.Response(200, json=_intent_response("create"))
        if len(captured) == 2:
            return httpx.Response(
                200, json=_splitter_response([{"text": "доделать отчёт по работе"}])
            )
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

    classifier_request = captured[2]  # intent, splitter, classifier
    body = classifier_request.read().decode()
    assert "Работа" in body, f"existing category 'Работа' missing from classifier prompt: {body!r}"
    assert "Здоровье" in body, (
        f"existing category 'Здоровье' missing from classifier prompt: {body!r}"
    )
    # Sanity: the bug ships the literal "existing_categories: []" payload.
    assert "existing_categories: []" not in body, (
        "classifier still receives empty user_categories — R-NEW-C-4 not fixed"
    )


# ── live-draft: on_stage progress callback ───────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_e2e_on_stage_called_once_for_multi_unit(session: AsyncSession) -> None:
    """Two create-units → ``on_stage`` fires exactly once, before classify,
    with a «Нашёл 2» live-draft progress string."""
    user, _ = await get_or_create_user(session, telegram_id=320)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _splitter_response([{"text": "купить хлеб"}, {"text": "записаться к врачу"}]),
            _intent_response("create"),  # PR-I3: per-unit intent
            _intent_response("create"),  # PR-I3: per-unit intent
            _classifier_response(_cr_dict(category="Покупки", title="Купить хлеб")),
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="week", title="Записаться к врачу")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    stages: list[str] = []

    async def on_stage(message: str) -> None:
        stages.append(message)

    text, _keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "купить хлеб, записаться к врачу",
        tg_user_id=320,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
        on_stage=on_stage,
    )

    assert text  # pipeline ran to completion
    assert len(stages) == 1
    assert "Нашёл 2" in stages[0]


@respx.mock
@pytest.mark.asyncio
async def test_e2e_on_stage_not_called_for_single_unit(session: AsyncSession) -> None:
    """A single create-unit is fast enough that no live-draft ping is
    emitted — ``on_stage`` is never invoked."""
    user, _ = await get_or_create_user(session, telegram_id=321)
    await session.commit()
    assert user.id is not None

    tracker = _CallTracker(
        [
            _intent_response("create"),
            _splitter_response([{"text": "утром пробежка"}]),
            _classifier_response(
                _cr_dict(category="Здоровье", horizon="today", title="Утренняя пробежка")
            ),
        ]
    )
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=tracker.side_effect
    )

    stages: list[str] = []

    async def on_stage(message: str) -> None:
        stages.append(message)

    text, _keyboard = await run_pipeline(
        GroqKeyRouter(keys=_FAKE_KEYS),
        "утром пробежка",
        tg_user_id=321,
        user_id=user.id,
        user_tz="Europe/Moscow",
        inbox_id=None,
        courier_mode="template_only",
        on_stage=on_stage,
    )

    assert text  # pipeline ran to completion
    assert stages == []


# ── unit: Russian pluralization helper ───────────────────────────────


def test_plural_ru() -> None:
    """``_plural_ru`` picks the correct Russian plural form for a count."""
    assert _plural_ru(1, "пункт", "пункта", "пунктов") == "пункт"
    assert _plural_ru(2, "пункт", "пункта", "пунктов") == "пункта"
    assert _plural_ru(5, "пункт", "пункта", "пунктов") == "пунктов"
    assert _plural_ru(11, "пункт", "пункта", "пунктов") == "пунктов"
    assert _plural_ru(22, "пункт", "пункта", "пунктов") == "пункта"


# ── flag_needs_review: the promise behind «лежит во Входящих» ────────


@pytest.mark.asyncio
async def test_flag_needs_review_sets_the_flag(session: AsyncSession) -> None:
    """The routers' crash-path reply tells the user their message is in
    «Входящие». That tab (``app/api/routers/inbox.py``) only returns
    rows with ``needs_review=True``, so the helper must actually set it.
    """
    user, _ = await get_or_create_user(session, telegram_id=9101)
    await session.commit()
    assert user.id is not None

    entry = InboxEntry(user_id=user.id, kind="text", raw_text="что-то важное")
    session.add(entry)
    await session.commit()
    entry_id = entry.id

    await flag_needs_review(entry_id, review_enabled=True)

    session.expire_all()
    refreshed = await session.get(InboxEntry, entry_id)
    assert refreshed is not None
    assert refreshed.needs_review is True


@pytest.mark.asyncio
async def test_flag_needs_review_respects_review_disabled(session: AsyncSession) -> None:
    """With review turned off the flag stays down — we must not shove
    rows into a tab the user switched off.
    """
    user, _ = await get_or_create_user(session, telegram_id=9102)
    await session.commit()
    assert user.id is not None

    entry = InboxEntry(user_id=user.id, kind="text", raw_text="что-то важное")
    session.add(entry)
    await session.commit()
    entry_id = entry.id

    await flag_needs_review(entry_id, review_enabled=False)

    session.expire_all()
    refreshed = await session.get(InboxEntry, entry_id)
    assert refreshed is not None
    assert refreshed.needs_review is False


@pytest.mark.asyncio
async def test_flag_needs_review_tolerates_missing_entry() -> None:
    """``inbox_id`` is ``int | None`` at the call sites — a crash before
    the inbox write must not turn into a second exception.
    """
    await flag_needs_review(None, review_enabled=True)
