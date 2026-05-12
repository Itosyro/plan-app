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

from aiogram.types import InlineKeyboardMarkup

from app.ai.classifier import classify_intent
from app.ai.courier import SummaryItem, courier_respond
from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.intent import detect_intent
from app.ai.reorder import detect_reorder
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ResolvedTime
from app.ai.splitter import split_message
from app.ai.time_resolver import resolve_time
from app.bot.edit_executor import EDIT_INTENTS_ALL, execute_edit, touch_last_task
from app.bot.services import (
    find_task_by_query,
    get_user_categories,
    log_ai_run,
    persist_classification,
    update_task_horizon,
)
from app.db.base import session_scope
from app.db.models import Task
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


async def _try_reorder(
    groq_router: GroqKeyRouter,
    text: str,
    user_id: int,
) -> str | None:
    """Detect reorder intent and execute if found. Returns reply or None."""
    reorder_req = await detect_reorder(groq_router, text)
    if not reorder_req.is_reorder or not reorder_req.task_query or not reorder_req.target_horizon:
        return None

    async with session_scope() as session:
        task = await find_task_by_query(session, user_id, reorder_req.task_query)
        if task is None:
            return f"Не нашёл задачу «{reorder_req.task_query}» — возможно, она уже выполнена или не существует."

        await update_task_horizon(session, task, reorder_req.target_horizon, user_id)
        horizon_labels = {
            "today": "сегодня",
            "tomorrow": "завтра",
            "week": "на эту неделю",
            "month": "на этот месяц",
            "year": "на этот год",
            "someday": "когда-нибудь",
        }
        label = horizon_labels.get(reorder_req.target_horizon, reorder_req.target_horizon)
        return f"Перенёс «{task.title}» → {label}."


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
) -> PipelineReply:
    """Inner pipeline body, called only while both semaphores are held."""
    # PR-I1: detect edit intent before falling through to create-path.
    edit_intent = await detect_intent(groq_router, text)
    if edit_intent.intent in EDIT_INTENTS_ALL:
        return await execute_edit(edit_intent, user_id)

    # Legacy reorder path — kept as fallback for intents not yet in
    # the intent router (or when detect_intent returns create/none).
    if edit_intent.intent in ("create", "none"):
        reorder_reply = await _try_reorder(groq_router, text, user_id)
        if reorder_reply is not None:
            return reorder_reply, None

    split_result = await split_message(groq_router, text)
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
    for unit in split_result.units:
        unit_intent = await detect_intent(groq_router, unit.text)
        if unit_intent.intent in EDIT_INTENTS_ALL:
            reply_text, _kb = await execute_edit(unit_intent, user_id)
            edit_replies.append(reply_text)
        else:
            create_units.append(unit)

    if not create_units:
        # All units were edits — return combined replies.
        return "\n".join(edit_replies), None

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

    # Critic: review classifications that need it (only survivors).
    reviewed: list[tuple[ClassifierResult, ResolvedTime | None]] = []
    for cr, resolved, unit_text in survivors:
        if should_run_critic(
            cr, critic_mode=critic_mode, confidence_threshold=confidence_threshold
        ):
            try:
                verdict = await critique_classification(
                    groq_router, unit_text, cr, resolved, user_tz
                )
                cr = apply_verdict(cr, verdict)
            except Exception:
                logger.exception("pipeline.critic_failed", user_id=user_id)
        reviewed.append((cr, resolved))

    # Persist surviving units.
    items: list[SummaryItem] = []
    async with session_scope() as session:
        await log_ai_run(
            session,
            user_id=user_id,
            inbox_id=inbox_id,
            stage="splitter",
            model="llama-3.1-8b-instant",
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
                items.append(
                    SummaryItem(
                        kind="task" if isinstance(row, Task) else "note",
                        title=cr.title,
                        category_name=cr.category_name,
                        persisted_id=row.id,
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
                model="llama-3.3-70b-versatile",
                key_index=groq_router.current_key_id,
            )

    text_reply, keyboard = await courier_respond(
        groq_router,
        items,
        mode=courier_mode,
        style=courier_style,
    )

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
