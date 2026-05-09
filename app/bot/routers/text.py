"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 added the Splitter.
Phase 2.2 adds the full pipeline: split → time → classify → persist → reply.
Phase 2.3 adds the Critic (conditional review of classifier output).
Phase 2.3c replaces the deterministic reply with Courier.
Phase 2.3d adds reorder detection (move task to a different horizon).

The pipeline body itself lives in ``app/bot/routers/_pipeline.py`` — this
file is just the aiogram glue. See ``docs/REVIEW-2026-05-09.md::I-4``.
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import Message

from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.routers._pipeline import (
    get_groq_router,
    log_task_exception,
    run_pipeline,
)
from app.bot.services import (
    get_or_create_user,
    get_user_settings,
    store_inbox_text,
)
from app.bot.streaming import stream_reply
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)


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
            courier_style = settings.courier_template_style if settings else "neutral"
            default_offsets: dict[str, list[int]] | None = (
                {k: list(v) for k, v in settings.default_reminder_offsets.items()}
                if settings
                else None
            )
            morning_anchor = settings.morning_anchor if settings else "09:00"
            evening_anchor = settings.evening_anchor if settings else "19:00"

        logger.info(
            "inbox.text_stored",
            user_id=message.from_user.id,
            text_len=len(message.text),
        )

        groq_router = get_groq_router()
        if groq_router is None:
            await message.answer("AI-разбор временно недоступен — сохраняю во входящие.")
            return

        msg_text = message.text
        from_user_id = message.from_user.id

        # Send a placeholder and edit it progressively once the
        # pipeline finishes. The user sees "⏳ Разбираю…" instantly,
        # then the real reply types itself line-by-line.
        placeholder = await message.answer("⏳ Разбираю…")

        async def _background() -> None:
            try:
                reply = await run_pipeline(
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
                    default_reminder_offsets=default_offsets,
                    morning_anchor=morning_anchor,
                    evening_anchor=evening_anchor,
                )
                await stream_reply(placeholder, reply, bot=message.bot)
            except Exception:
                logger.exception(
                    "pipeline.error",
                    tg_user_id=from_user_id,
                    text_len=len(msg_text),
                )
                try:
                    await placeholder.edit_text(
                        "Ошибка при разборе — сохранил во входящие, разберу позже."
                    )
                except Exception:
                    await message.answer(
                        "Ошибка при разборе — сохранил во входящие, разберу позже."
                    )

        task = asyncio.create_task(_background())
        task.add_done_callback(log_task_exception)

    return router
