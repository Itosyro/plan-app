"""Inbox entries + Telegram update idempotency."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import InboxEntry, TelegramUpdate


async def is_update_processed(session: AsyncSession, update_id: int) -> bool:
    """Idempotency guard — return True if we've already seen this update_id.

    NOTE: this function is a *non-atomic* check (SELECT only) and is kept
    for direct-DB assertions in tests. The webhook handler uses
    :func:`claim_update` instead, which is atomic against concurrent
    deliveries. See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-5``.
    """
    result = await session.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == update_id))
    return result.first() is not None


async def record_update(
    session: AsyncSession,
    *,
    update_id: int,
    user_id: int | None,
    kind: str | None,
) -> None:
    """Mark a Telegram update as processed.

    NOTE: not race-safe — two concurrent callers will both pass any prior
    ``is_update_processed`` check and the second will hit a primary-key
    ``IntegrityError`` here. Use :func:`claim_update` from request paths
    that may race; this helper stays for tests that pre-seed rows.
    """
    session.add(TelegramUpdate(update_id=update_id, user_id=user_id, kind=kind))
    await session.flush()


async def claim_update(
    session: AsyncSession,
    *,
    update_id: int,
    user_id: int | None,
    kind: str | None,
) -> bool:
    """Atomically register *update_id* as processed.

    Returns ``True`` if this call inserted the row (caller should proceed
    to dispatch the update); ``False`` if another concurrent caller
    already inserted the same ``update_id`` (caller should treat the
    delivery as a duplicate and reply 200 without dispatching).

    Implementation: INSERT then catch ``IntegrityError`` on PK conflict.
    Replaces the old SELECT-then-INSERT pattern, which had a TOCTOU race
    where two webhook requests for the same ``update_id`` could both
    pass the SELECT and the second's INSERT would fail with a 500 — the
    bug that made Telegram retry the same update forever. See
    ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-5``.
    """
    session.add(TelegramUpdate(update_id=update_id, user_id=user_id, kind=kind))
    try:
        await session.flush()
    except IntegrityError:
        # Конфликт PK значит, что конкурент уже застолбил этот update_id.
        # Откатываем текущий sub-state и сообщаем вызывающему, что это
        # дубликат — ``session_scope`` спокойно завершится без записи.
        await session.rollback()
        return False
    return True


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
