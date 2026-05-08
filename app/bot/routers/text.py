"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 adds the Splitter: after storing the message, we run the AI
splitter in the background and reply with a short acknowledgement.
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import Message

from app.ai.router import GroqKeyRouter
from app.ai.splitter import split_message
from app.bot.courier_templates import NOT_ONBOARDED, TEXT_ACK_PHASE1
from app.bot.services import get_or_create_user, store_inbox_text
from app.db.base import session_scope
from app.shared.config import get_settings
from app.shared.logging import get_logger

logger = get_logger(__name__)


def _get_router() -> GroqKeyRouter | None:
    """Build a GroqKeyRouter from settings, or None if no keys configured."""
    keys = get_settings().groq_keys_list
    if not keys:
        return None
    return GroqKeyRouter(keys=keys)


async def _run_splitter(groq_router: GroqKeyRouter, text: str, tg_user_id: int) -> None:
    """Run the splitter and log the result.

    Exceptions are caught so a splitter failure never crashes the webhook.
    """
    try:
        result = await split_message(groq_router, text)
        logger.info(
            "splitter.result",
            tg_user_id=tg_user_id,
            units_count=len(result.units),
            text_len=len(text),
        )
    except Exception:
        logger.exception(
            "splitter.error",
            tg_user_id=tg_user_id,
            text_len=len(text),
        )


def create_router() -> Router:
    """Build a fresh ``text`` router (catch-all)."""
    router = Router(name="text")

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Persist incoming text, run Splitter in background, acknowledge."""
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
            await store_inbox_text(
                session,
                user_id=user.id,
                raw_text=message.text,
                telegram_message_id=message.message_id,
            )

        # PII: text-length only, never the message text itself.
        logger.info(
            "inbox.text_stored",
            user_id=message.from_user.id,
            text_len=len(message.text),
        )

        # Phase 2.1: fire splitter in background so webhook responds fast.
        groq_router = _get_router()
        if groq_router is not None:
            task = asyncio.create_task(
                _run_splitter(groq_router, message.text, message.from_user.id),
            )
            # Prevent the task from being garbage-collected before completion.
            task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)

        await message.answer(TEXT_ACK_PHASE1)

    return router
