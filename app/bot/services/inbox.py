"""Inbox entries + Telegram update idempotency."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import InboxEntry, TelegramUpdate


async def is_update_processed(session: AsyncSession, update_id: int) -> bool:
    """Idempotency guard — return True if we've already seen this update_id."""
    result = await session.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == update_id))
    return result.first() is not None


async def record_update(
    session: AsyncSession,
    *,
    update_id: int,
    user_id: int | None,
    kind: str | None,
) -> None:
    """Mark a Telegram update as processed."""
    session.add(TelegramUpdate(update_id=update_id, user_id=user_id, kind=kind))
    await session.flush()


async def store_inbox_text(
    session: AsyncSession,
    *,
    user_id: int,
    raw_text: str,
    telegram_message_id: int | None,
) -> InboxEntry:
    """Persist an incoming text message into the inbox."""
    entry = InboxEntry(
        user_id=user_id,
        kind="text",
        raw_text=raw_text,
        telegram_message_id=telegram_message_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def store_inbox_voice(
    session: AsyncSession,
    *,
    user_id: int,
    transcript: str,
    telegram_message_id: int | None,
) -> InboxEntry:
    """Persist an incoming voice message (with transcript) into the inbox."""
    entry = InboxEntry(
        user_id=user_id,
        kind="voice",
        transcript=transcript,
        telegram_message_id=telegram_message_id,
    )
    session.add(entry)
    await session.flush()
    return entry
