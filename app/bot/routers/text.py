"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 added the Splitter.
Phase 2.2 adds the full pipeline: split → time → classify → persist → reply.
Phase 2.3 adds the Critic (conditional review of classifier output).
Phase 2.3c replaces the deterministic reply with Courier.
Phase 2.3d adds reorder detection (move task to a different horizon).
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import Message

from app.ai.classifier import classify_intent
from app.ai.courier import courier_respond
from app.ai.critic import apply_verdict, critique_classification, should_run_critic
from app.ai.reorder import detect_reorder
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult
from app.ai.splitter import split_message
from app.ai.time_resolver import resolve_time
from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.services import (
    find_task_by_query,
    get_or_create_user,
    get_user_settings,
    log_ai_run,
    persist_classification,
    store_inbox_text,
    update_task_horizon,
)
from app.db.base import session_scope
from app.shared.config import get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

_groq_router: GroqKeyRouter | None = None


def _log_task_exception(task: asyncio.Task[object]) -> None:
    """Log any exception raised inside a background task instead of swallowing it."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "background_task.unhandled",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def _get_router() -> GroqKeyRouter | None:
    """Return singleton GroqKeyRouter (lazy init)."""
    global _groq_router
    if _groq_router is not None:
        return _groq_router
    keys = get_settings().groq_keys_list
    if not keys:
        return None
    _groq_router = GroqKeyRouter(keys=keys)
    return _groq_router


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


async def _run_pipeline(
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
) -> str:
    """Detect reorder or run split → time → classify → critic → persist."""
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
    resolved_list = [resolve_time(unit.text, user_tz) for unit in split_result.units]

    # Classify all units in parallel. ``return_exceptions=True`` keeps a single
    # transient Groq failure (429, 5xx) from killing the whole batch — we drop
    # the failed unit and continue with the rest.
    classify_tasks = [
        classify_intent(groq_router, unit.text, resolved, [], user_tz)
        for unit, resolved in zip(split_result.units, resolved_list, strict=True)
    ]
    raw_results = await asyncio.gather(*classify_tasks, return_exceptions=True)

    survivors: list[tuple[ClassifierResult, object, str]] = []
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
    reviewed: list[tuple[ClassifierResult, object]] = []
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


def create_router() -> Router:
    """Build a fresh ``text`` router (catch-all)."""
    router = Router(name="text")

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Persist incoming text, run full pipeline in background, reply."""
        if message.from_user is None or message.text is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            assert user.id is not None
            entry = await store_inbox_text(
                session,
                user_id=user.id,
                raw_text=message.text,
                telegram_message_id=message.message_id,
            )
            user_id = user.id
            user_tz = user.tz
            inbox_id = entry.id
            settings = await get_user_settings(session, user.id)
            critic_mode = settings.critic_mode if settings else "confidence"
            critic_threshold = settings.critic_confidence_threshold if settings else 0.7
            courier_mode = settings.response_style_source if settings else "mix"
            courier_style = "neutral"

        logger.info(
            "inbox.text_stored",
            user_id=message.from_user.id,
            text_len=len(message.text),
        )

        groq_router = _get_router()
        if groq_router is None:
            await message.answer("AI-разбор временно недоступен — сохраняю во входящие.")
            return

        msg_text = message.text
        from_user_id = message.from_user.id

        await message.answer("⏳ Разбираю…")

        async def _background() -> None:
            try:
                reply = await _run_pipeline(
                    groq_router,
                    msg_text,
                    from_user_id,
                    user_id,
                    user_tz,
                    inbox_id,
                    critic_mode=critic_mode,
                    confidence_threshold=critic_threshold,
                    courier_mode=courier_mode,
                    courier_style=courier_style,
                )
                await message.answer(reply)
            except Exception:
                logger.exception(
                    "pipeline.error",
                    tg_user_id=from_user_id,
                    text_len=len(msg_text),
                )
                await message.answer("Ошибка при разборе — сохранил во входящие, разберу позже.")

        task = asyncio.create_task(_background())
        task.add_done_callback(_log_task_exception)

    return router
