"""Shared pipeline helpers for the text and voice routers.

``app/bot/routers/text.py`` and ``app/bot/routers/voice.py`` were
sharing the same Groq pipeline (split → time → classify → critic →
persist → courier reply) plus a couple of small utilities (lazy
``GroqKeyRouter`` singleton, background-task exception logger).
Voice imported these from text.py via leading-underscore (private)
names, which is a layering violation.

This module hosts those helpers under public names. Both routers
import from here. See ``docs/REVIEW-2026-05-09.md::I-4``.
"""

from __future__ import annotations

import asyncio

from app.ai.classifier import classify_intent
from app.ai.courier import courier_respond
from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.reorder import detect_reorder
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ResolvedTime
from app.ai.splitter import split_message
from app.ai.time_resolver import resolve_time
from app.bot.services import (
    find_task_by_query,
    get_user_categories,
    log_ai_run,
    persist_classification,
    update_task_horizon,
)
from app.db.base import session_scope
from app.shared.config import get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

_groq_router: GroqKeyRouter | None = None


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
        return f"✅ Перенёс «{task.title}» → {label}."


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
) -> str:
    """Detect reorder or run split → time → classify → critic → persist → reply.

    The full Groq pipeline. Used by both the text router and the voice
    router (post-Whisper). Returns a user-facing reply string.
    """
    reorder_reply = await _try_reorder(groq_router, text, user_id)
    if reorder_reply is not None:
        return reorder_reply
    split_result = await split_message(groq_router, text)
    logger.info(
        "pipeline.split",
        tg_user_id=tg_user_id,
        units_count=len(split_result.units),
    )

    if not split_result.units:
        return "Принял, но не нашёл конкретных задач или заметок."

    # Resolve time for each unit (pure Python, fast)
    resolved_list: list[ResolvedTime | None] = [
        resolve_time(
            unit.text,
            user_tz,
            morning_anchor=morning_anchor,
            evening_anchor=evening_anchor,
        )
        for unit in split_result.units
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
        for unit, resolved in zip(split_result.units, resolved_list, strict=True)
    ]
    raw_results = await asyncio.gather(*classify_tasks, return_exceptions=True)

    survivors: list[tuple[ClassifierResult, ResolvedTime | None, str]] = []
    for unit, resolved, item in zip(split_result.units, resolved_list, raw_results, strict=True):
        if isinstance(item, BaseException):
            logger.exception(
                "pipeline.classify_failed",
                user_id=user_id,
                exc_info=(type(item), item, item.__traceback__),
            )
            continue
        survivors.append((item, resolved, unit.text))

    if not survivors:
        return "Не удалось разобрать ни одну часть сообщения — сохранил во входящие."

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

            await persist_classification(
                session,
                user_id=user_id,
                cr=cr,
                due_at=due_at,
                inbox_id=inbox_id,
                default_reminder_offsets=default_reminder_offsets,
            )

            await log_ai_run(
                session,
                user_id=user_id,
                inbox_id=inbox_id,
                stage="classifier",
                model="llama-3.3-70b-versatile",
                key_index=groq_router.current_key_id,
            )

    return await courier_respond(
        groq_router,
        [cr for cr, _ in reviewed],
        mode=courier_mode,
        style=courier_style,
    )
