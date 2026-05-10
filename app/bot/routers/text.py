"""Catch-all router for plain-text messages (after onboarding).

Phase 1 stored the message in ``inbox_entries`` and replied with a stub.
Phase 2.1 added the Splitter.
Phase 2.2 adds the full pipeline: split → time → classify → persist → reply.
Phase 2.3 adds the Critic (conditional review of classifier output).
Phase 2.3c replaces the deterministic reply with Courier.
Phase 2.3d adds reorder detection (move task to a different horizon).
Phase 8b extracts the inbox + pipeline glue into ``_pipeline.enqueue_text_pipeline``
so the ``/add`` slash command can share it.

The pipeline body itself lives in ``app/bot/routers/_pipeline.py`` — this
file is just the aiogram glue. See ``docs/REVIEW-2026-05-09.md::I-4``.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bot.routers._pipeline import enqueue_text_pipeline


def create_router() -> Router:
    """Build a fresh ``text`` router (catch-all)."""
    router = Router(name="text")

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Persist incoming text, run full pipeline in background, reply."""
        if message.text is None:
            return
        await enqueue_text_pipeline(message, message.text)

    return router
