"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 added the Splitter.
Phase 2.2 adds the full pipeline: split → time → classify → persist → reply.
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import Message

from app.ai.classifier import classify_intent
from app.ai.router import GroqKeyRouter
from app.ai.splitter import split_message
from app.ai.time_resolver import resolve_time
from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.services import (
    get_or_create_user,
    log_ai_run,
    persist_classification,
    store_inbox_text,
)
from app.db.base import session_scope
from app.shared.config import get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

_groq_router: GroqKeyRouter | None = None


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


def _pluralize_elements(n: int) -> str:
    """Russian plural for 'элемент'."""
    if 11 <= n % 100 <= 19:
        return f"{n} элементов"
    mod = n % 10
    if mod == 1:
        return f"{n} элемент"
    if 2 <= mod <= 4:
        return f"{n} элемента"
    return f"{n} элементов"


async def _run_pipeline(
    groq_router: GroqKeyRouter,
    text: str,
    tg_user_id: int,
    user_id: int,
    user_tz: str,
    inbox_id: int | None,
) -> str:
    """Run split → time → classify → persist and return a reply summary."""
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

    # Classify all units in parallel
    classify_tasks = [
        classify_intent(groq_router, unit.text, resolved, [], user_tz)
        for unit, resolved in zip(split_result.units, resolved_list, strict=True)
    ]
    classifier_results = await asyncio.gather(*classify_tasks)

    # Persist results
    summaries: list[str] = []
    async with session_scope() as session:
        await log_ai_run(
            session,
            user_id=user_id,
            inbox_id=inbox_id,
            stage="splitter",
            model="llama-3.1-8b-instant",
            key_index=groq_router.current_key_id,
        )

        for cr, resolved in zip(classifier_results, resolved_list, strict=True):
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

            kind = "📌 задача" if cr.is_task else "📝 заметка"
            summaries.append(f"{kind}: {cr.title} [{cr.category_name}]")

    header = f"Разобрал на {_pluralize_elements(len(summaries))}:\n"
    return header + "\n".join(summaries)


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
        task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)

    return router
