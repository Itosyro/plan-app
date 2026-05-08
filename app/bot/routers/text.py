"""Catch-all router for plain-text messages (after onboarding).

Phase 1 just stores the message in ``inbox_entries`` and replies with a
short acknowledgement. Phase 2 will hand the entry off to the AI pipeline
(Splitter → Classifier → Critic).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bot.courier_templates import NOT_ONBOARDED, TEXT_ACK_PHASE1
from app.bot.services import get_or_create_user, store_inbox_text
from app.db.base import session_scope
from app.shared.logging import get_logger

logger = get_logger(__name__)


def create_router() -> Router:
    """Build a fresh ``text`` router (catch-all)."""
    router = Router(name="text")

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Persist incoming text and acknowledge."""
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
        await message.answer(TEXT_ACK_PHASE1)

    return router
