"""Shared pipeline helpers for the text and voice routers.

``app/bot/routers/text.py`` and ``app/bot/routers/voice.py`` were
sharing the same Groq pipeline (split → time → classify → critic →
persist → courier reply) plus a couple of small utilities (lazy
``GroqKeyRouter`` singleton, background-task exception logger).
Voice imported these from text.py via leading-underscore (private)
names, which is a layering violation.

This module hosts those helpers under public names. Both routers
import from here. See ``docs/REVIEW-2026-05-09.md::I-4``.

Backpressure (R-NEW-I-8): every ``run_pipeline`` invocation passes
through two semaphores — a per-user one (``PER_USER_PIPELINE_LIMIT``,
default 1) that serialises requests from the same user, and a
global one (``GLOBAL_PIPELINE_LIMIT``, default 8) that caps total
concurrent pipelines across the whole worker. Without these, a user
spam-tapping voice messages or a coordinated burst of webhooks
could fan out hundreds of in-flight Groq requests, exhaust file
descriptors, and trip the rate-limiter for every other user.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from aiogram.types import InlineKeyboardMarkup
from sqlmodel import select

from app.ai.classifier import classify_intent
from app.ai.courier import SummaryItem, courier_respond
from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.intent import detect_intent
from app.ai.models import get_models
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ResolvedTime
from app.ai.splitter import split_message
from app.ai.time_resolver import resolve_time
from app.bot.edit_executor import EDIT_INTENTS_ALL, execute_edit, touch_last_task
from app.bot.services import (
    get_user_categories,
    log_ai_run,
    persist_classification,
)
from app.db.base import session_scope
from app.db.models import InboxEntry, Note, Task
from app.shared.config import get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

# ── Pipeline backpressure (R-NEW-I-8) ────────────────────────────────

# Per-user limit: how many pipeline runs the same user can have
# in-flight simultaneously. 1 = strict serialisation (the simplest
# semantics: a user's Nth message waits for their (N-1)th to finish
# its courier reply). Higher values would let two voice messages
# from the same user run concurrently — useful for throughput, but
# breaks the "one reply per message in order" UX guarantee.
PER_USER_PIPELINE_LIMIT = 1

# Global limit: caps total concurrent pipelines across all users.
# Sized to leave headroom on a single Render instance (Groq client
# pool, DB connection pool, file descriptors). 8 is a conservative
# default for the current single-worker deploy; raise once the
# instance is profiled under burst load.
GLOBAL_PIPELINE_LIMIT = 8

_groq_router: GroqKeyRouter | None = None
_global_pipeline_semaphore: asyncio.Semaphore | None = None
_user_pipeline_semaphores: dict[int, asyncio.Semaphore] = {}
_user_semaphores_lock: asyncio.Lock | None = None


def _get_global_pipeline_semaphore() -> asyncio.Semaphore:
    """Return the lazily-initialised global semaphore.

    Must be called from inside a running asyncio loop on first use
    (the semaphore binds to the current loop on construction in
    older Python versions; on 3.12 the loop is resolved at acquire
    time, but lazy-init still avoids creating it during import).
    """
    global _global_pipeline_semaphore
    if _global_pipeline_semaphore is None:
        _global_pipeline_semaphore = asyncio.Semaphore(GLOBAL_PIPELINE_LIMIT)
    return _global_pipeline_semaphore


async def _get_user_pipeline_semaphore(user_id: int) -> asyncio.Semaphore:
    """Return the per-user semaphore, creating it under a lock so two
    concurrent first-message arrivals can't each install a fresh
    semaphore and race past the per-user limit.
    """
    global _user_semaphores_lock
    if _user_semaphores_lock is None:
        _user_semaphores_lock = asyncio.Lock()
    async with _user_semaphores_lock:
        sem = _user_pipeline_semaphores.get(user_id)
        if sem is None:
            sem = asyncio.Semaphore(PER_USER_PIPELINE_LIMIT)
            _user_pipeline_semaphores[user_id] = sem
        return sem


def reset_pipeline_semaphores_for_tests() -> None:
    """Test-only hook: drop the cached semaphores so each test gets
    a fresh limit-counter and (more importantly) one bound to the
    test's event loop instead of a previous test's closed loop.
    """
    global _global_pipeline_semaphore, _user_semaphores_lock
    _global_pipeline_semaphore = None
    _user_semaphores_lock = None
    _user_pipeline_semaphores.clear()


def get_groq_router() -> GroqKeyRouter | None:
    """Return the singleton ``GroqKeyRouter`` (lazy init).

    ``None`` if the deployment has no Groq keys configured (treated as
    'AI temporarily unavailable' by callers).
    """
    global _groq_router
    if _groq_router is not None:
        return _groq_router
    keys = get_settings().groq_keys_list
    if not keys:
        return None
    _groq_router = GroqKeyRouter(keys=keys)
    return _groq_router


def log_task_exception(task: asyncio.Task[object]) -> None:
    """Log any exception raised by a fire-and-forget background task.

    Used as a ``Task.add_done_callback`` so unhandled exceptions in
    background pipelines surface in logs instead of being silently
    swallowed by ``asyncio``.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "background_task.unhandled",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


PipelineReply = tuple[str, InlineKeyboardMarkup | None]

# Callback the router supplies to receive progressive status updates while
# the pipeline runs (live-draft). Best-effort: the pipeline never blocks
# on it and swallows nothing — the router decides how to render (edit the
# placeholder). ``None`` disables progress reporting.
StageCallback = Callable[[str], Awaitable[None]]


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Russian plural for a count: 1 пункт, 2 пункта, 5 пунктов."""
    if 11 <= (n % 100) <= 14:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


async def run_pipeline(
    groq_router: GroqKeyRouter,
    text: str,
    tg_user_id: int,
    user_id: int,
    user_tz: str,
    inbox_id: int | None,
    *,
    critic_mode: str = "confidence",
    confidence_threshold: float = 0.7,
    courier_mode: str = "mix",
    courier_style: str = "neutral",
    default_reminder_offsets: dict[str, list[int]] | None = None,
    morning_anchor: str = "09:00",
    evening_anchor: str = "19:00",
    concretize_tasks: bool = False,
    review_enabled: bool = True,
    on_stage: StageCallback | None = None,
) -> PipelineReply:
    """Detect reorder or run split → time → classify → critic → persist → reply.

    The full Groq pipeline. Used by both the text router and the voice
    router (post-Whisper). Returns ``(reply_text, summary_keyboard)``
    where ``summary_keyboard`` is ``None`` for short / error replies
    (no classified items to show) and a populated
    :class:`InlineKeyboardMarkup` otherwise (PR-E recognised-card).

    Backpressure: a per-user semaphore + a global semaphore gate the
    actual work (see R-NEW-I-8). Acquisitions are nested (per-user
    *outside* the global) so a flood from one user can't deadlock
    other users — the per-user wait blocks before any global slot is
    held. Acquire timing is logged at info level on contention.
    """
    user_sem = await _get_user_pipeline_semaphore(user_id)
    global_sem = _get_global_pipeline_semaphore()
    if user_sem.locked() or global_sem.locked():
        logger.info(
            "pipeline.backpressure_wait",
            user_id=user_id,
            user_locked=user_sem.locked(),
            global_locked=global_sem.locked(),
        )
    async with user_sem, global_sem:
        return await _run_pipeline_inner(
            groq_router,
            text,
            tg_user_id,
            user_id,
            user_tz,
            inbox_id,
            critic_mode=critic_mode,
            confidence_threshold=confidence_threshold,
            courier_mode=courier_mode,
            courier_style=courier_style,
            default_reminder_offsets=default_reminder_offsets,
            morning_anchor=morning_anchor,
            evening_anchor=evening_anchor,
            concretize_tasks=concretize_tasks,
            review_enabled=review_enabled,
            on_stage=on_stage,
        )


async def _run_pipeline_inner(
    groq_router: GroqKeyRouter,
    text: str,
    tg_user_id: int,
    user_id: int,
    user_tz: str,
    inbox_id: int | None,
    *,
    critic_mode: str = "confidence",
    confidence_threshold: float = 0.7,
    courier_mode: str = "mix",
    courier_style: str = "neutral",
    default_reminder_offsets: dict[str, list[int]] | None = None,
    morning_anchor: str = "09:00",
    evening_anchor: str = "19:00",
    concretize_tasks: bool = False,
    review_enabled: bool = True,
    on_stage: StageCallback | None = None,
) -> PipelineReply:
    """Inner pipeline body, called only while both semaphores are held."""

    async def _emit_stage(text: str) -> None:
        """Best-effort progress ping — never let it break the pipeline."""
        if on_stage is None:
            return
        try:
            await on_stage(text)
        except Exception:
            logger.debug("pipeline.stage_emit_failed", exc_info=True)

    # PR-I1: detect edit intent before falling through to create-path.
    # detect_intent and split_message both call the 8b model on the raw
    # text and don't depend on each other, so run them concurrently — this
    # shaves a full LLM round-trip off the critical path. On the rarer edit
    # path the split result is simply discarded; that extra call is cheap
    # and was already in flight.
    edit_intent, split_result = await asyncio.gather(
        detect_intent(groq_router, text),
        split_message(groq_router, text),
    )
    if edit_intent.intent in EDIT_INTENTS_ALL:
        return await execute_edit(edit_intent, user_id)
    logger.info(
        "pipeline.split",
        tg_user_id=tg_user_id,
        units_count=len(split_result.units),
    )

    if not split_result.units:
        return (
            "Слышу тебя, но не нашёл в сообщении конкретных задач или заметок — "
            "попробуй переформулировать."
        ), None

    # PR-I3: multi-intent — detect_intent each unit, separate edits from creates.
    edit_replies: list[str] = []
    create_units = []
    if len(split_result.units) == 1:
        # Single-unit short-circuit: the whole-message detect_intent above
        # already ran; an edit would have returned earlier, so a lone unit
        # is necessarily a create. Re-detecting would be a redundant
        # round-trip.
        create_units = [split_result.units[0]]
    else:
        # Detect intent for every unit in parallel, then split edits from
        # creates while preserving order. ``execute_edit`` stays sequential
        # so edit replies keep their order.
        unit_intents = await asyncio.gather(
            *[detect_intent(groq_router, unit.text) for unit in split_result.units]
        )
        for unit, unit_intent in zip(split_result.units, unit_intents, strict=True):
            if unit_intent.intent in EDIT_INTENTS_ALL:
                reply_text, _kb = await execute_edit(unit_intent, user_id)
                edit_replies.append(reply_text)
            else:
                create_units.append(unit)

    if not create_units:
        # All units were edits — return combined replies.
        return "\n".join(edit_replies), None

    # Live-draft: for multi-item messages, tell the user what we found
    # before the slower classify+critic pass runs. Single-item messages
    # are fast enough that an extra edit would just be noise — skip them.
    create_count = len(create_units)
    if create_count >= 2:
        word = _plural_ru(create_count, "пункт", "пункта", "пунктов")
        await _emit_stage(f"✍️ Нашёл {create_count} {word}, раскладываю по полочкам…")

    # Resolve time for each remaining create-unit (pure Python, fast)
    resolved_list: list[ResolvedTime | None] = [
        resolve_time(
            unit.text,
            user_tz,
            morning_anchor=morning_anchor,
            evening_anchor=evening_anchor,
        )
        for unit in create_units
    ]

    # Fetch the user's existing categories so the classifier can reuse
    # them instead of inventing fresh near-duplicates ("Работа" /
    # "работа" / "Рабочее"). Empty list on the first message ever; that
    # is fine — the classifier will seed new categories. See
    # ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-4``.
    async with session_scope() as session:
        user_categories = await get_user_categories(session, user_id)

    # Classify all units in parallel. ``return_exceptions=True`` keeps a single
    # transient Groq failure (429, 5xx) from killing the whole batch — we drop
    # the failed unit and continue with the rest.
    classify_tasks = [
        classify_intent(groq_router, unit.text, resolved, user_categories, user_tz)
        for unit, resolved in zip(create_units, resolved_list, strict=True)
    ]
    raw_results = await asyncio.gather(*classify_tasks, return_exceptions=True)

    survivors: list[tuple[ClassifierResult, ResolvedTime | None, str]] = []
    for unit, resolved, item in zip(create_units, resolved_list, raw_results, strict=True):
        if isinstance(item, BaseException):
            logger.exception(
                "pipeline.classify_failed",
                user_id=user_id,
                exc_info=(type(item), item, item.__traceback__),
            )
            continue
        survivors.append((item, resolved, unit.text))

    if not survivors:
        return (
            "Не удалось разобрать сообщение — сохранил его целиком во входящие, позже разберясь."
        ), None

    # Critic: review classifications that need it (only survivors). Critic
    # calls run in parallel; ``return_exceptions=True`` keeps a single
    # transient failure from killing the batch (mirrors the classifier
    # gather above). ``reviewed`` preserves ``survivors`` order.
    critic_needed = [
        should_run_critic(cr, critic_mode=critic_mode, confidence_threshold=confidence_threshold)
        for cr, _resolved, _unit_text in survivors
    ]
    critic_tasks = [
        critique_classification(groq_router, unit_text, cr, resolved, user_tz)
        for (cr, resolved, unit_text), needed in zip(survivors, critic_needed, strict=True)
        if needed
    ]
    critic_results = await asyncio.gather(*critic_tasks, return_exceptions=True)

    reviewed: list[tuple[ClassifierResult, ResolvedTime | None]] = []
    critic_iter = iter(critic_results)
    for (cr, resolved, _unit_text), needed in zip(survivors, critic_needed, strict=True):
        if needed:
            verdict = next(critic_iter)
            if isinstance(verdict, BaseException):
                logger.exception(
                    "pipeline.critic_failed",
                    user_id=user_id,
                    exc_info=(type(verdict), verdict, verdict.__traceback__),
                )
            else:
                cr = apply_verdict(cr, verdict)
        reviewed.append((cr, resolved))

    # Persist surviving units. Under the review model (вариант Б),
    # low-confidence items are persisted immediately rather than deferred
    # to an in-chat «создать? да/нет» prompt. Instead, when a message
    # produces ≥2 tasks or anything came back below the confidence
    # threshold, we flag the inbox entry ``needs_review`` so the Mini-App
    # «Входящие» tab surfaces it for a quick confirm / cleanup.
    items: list[SummaryItem] = []
    created_task_count = 0
    created_note_count = 0
    any_low_confidence = False
    review_flagged = False

    async with session_scope() as session:
        await log_ai_run(
            session,
            user_id=user_id,
            inbox_id=inbox_id,
            stage="splitter",
            model=get_models().splitter,
            key_index=groq_router.current_key_id,
        )

        for cr, resolved in reviewed:
            due_at = resolved.resolved_dt if resolved else None

            # When the user said «напомни …» (or «напоминание»), the
            # canonical behaviour is to fire ONE reminder at the
            # ``due_at`` itself — not the user's default advance offsets.
            # If the classifier already supplied explicit offsets we
            # respect them; otherwise we synthesise ``[0]`` so the
            # reminder is scheduled. Without this branch, ``is_reminder``
            # was set on ``ResolvedTime`` but never actually translated
            # into a row in the ``reminders`` table.
            if (
                resolved is not None
                and resolved.is_reminder
                and cr.is_task
                and due_at is not None
                and not cr.reminder_offsets
            ):
                cr = cr.model_copy(update={"reminder_offsets": [0]})

            if cr.confidence < confidence_threshold:
                any_low_confidence = True

            row = await persist_classification(
                session,
                user_id=user_id,
                cr=cr,
                due_at=due_at,
                inbox_id=inbox_id,
                default_reminder_offsets=default_reminder_offsets,
                concretize_tasks=concretize_tasks,
            )
            if row.id is not None:
                # PR-I3: update LAST_TASK so the user can refer back.
                if isinstance(row, Task):
                    touch_last_task(user_id, row.id)
                    created_task_count += 1
                elif isinstance(row, Note):
                    created_note_count += 1
                # PR-Subtask-Tree: pull just-created child titles so
                # courier can render a Unicode tree under the
                # confirmation. Same-session SELECT is cheap and avoids
                # duplicating the dedup / cap logic from
                # ``_persist_subtasks``.
                subtask_titles: tuple[str, ...] = ()
                if isinstance(row, Task) and cr.subtasks:
                    child_rows = (
                        await session.exec(
                            select(Task.title)
                            .where(Task.parent_id == row.id)
                            .order_by(Task.created_at.asc())  # type: ignore[attr-defined]
                        )
                    ).all()
                    subtask_titles = tuple(child_rows)
                items.append(
                    SummaryItem(
                        kind="task" if isinstance(row, Task) else "note",
                        title=cr.title,
                        category_name=cr.category_name,
                        persisted_id=row.id,
                        subtask_titles=subtask_titles,
                    )
                )
            else:
                # Defensive: ``persist_classification`` flushes the row, so
                # ``id`` is always populated. If somehow it's not, skip
                # adding to the keyboard rather than crashing the reply.
                logger.warning(
                    "pipeline.persisted_row_missing_id",
                    user_id=user_id,
                    kind="task" if isinstance(row, Task) else "note",
                )
            await log_ai_run(
                session,
                user_id=user_id,
                inbox_id=inbox_id,
                stage="classifier",
                model=get_models().classifier,
                key_index=groq_router.current_key_id,
            )

        # Flag the inbox entry for review when the message produced
        # several tasks or anything came back unsure. The tasks already
        # exist (вариант Б) — the flag just routes them to the Mini-App
        # «Входящие» tab for a confirm / cleanup pass.
        if (
            review_enabled
            and inbox_id is not None
            and ((created_task_count + created_note_count) >= 2 or any_low_confidence)
        ):
            entry = await session.get(InboxEntry, inbox_id)
            if entry is not None:
                entry.needs_review = True
                session.add(entry)
                review_flagged = True

    # Skip the courier LLM coin-flip for the trivial single-item case: a
    # one-line confirmation doesn't justify a blocking ~100-200ms round-trip.
    effective_courier_mode = (
        "template_only" if (created_task_count + created_note_count) == 1 else courier_mode
    )
    text_reply, keyboard = await courier_respond(
        groq_router,
        items,
        mode=effective_courier_mode,
        style=courier_style,
    )

    if review_flagged:
        review_note = "📥 Отправил на проверку — открой «Входящие» в приложении."
        text_reply = f"{text_reply}\n\n{review_note}" if text_reply else review_note

    # PR-I3: prepend edit replies when message contained mixed intents.
    if edit_replies:
        text_reply = "\n".join(edit_replies) + "\n\n" + text_reply

    return text_reply, keyboard


# Re-export ``Note``/``Task`` only so static type-checkers don't strip the
# import as unused (they're referenced in ``isinstance`` checks above).
__all__ = [
    "GLOBAL_PIPELINE_LIMIT",
    "PER_USER_PIPELINE_LIMIT",
    "PipelineReply",
    "get_groq_router",
    "log_task_exception",
    "reset_pipeline_semaphores_for_tests",
    "run_pipeline",
]
