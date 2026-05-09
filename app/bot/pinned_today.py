"""Pinned-morning-digest tracker (Phase 6.3, Bot API 10.0 polish).

When the morning digest fires, the bot pins it at the top of the user's
chat. As tasks are marked done / moved / deleted during the day, we
re-render the digest and ``editMessageText`` the same pinned message so
the pin always reflects today's state — turning a static morning ping
into a living "today board".

We track the message identity ``(chat_id, message_id, date)`` on
``UserSettings``. Three reasons the pin can become unusable:
1. Message older than 48h — Telegram refuses ``editMessageText``.
2. User manually unpinned / deleted the message.
3. The bot was kicked / blocked.
All of these surface as ``TelegramBadRequest`` or ``TelegramForbiddenError``;
in every case we just clear the stored pin so we don't keep retrying.

The pin itself is best-effort: if ``pinChatMessage`` fails because the bot
doesn't have permission (private chat is fine; group chats might restrict
us), we still send the digest and just skip the pin.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import User, UserSettings
from app.shared.logging import get_logger

logger = get_logger(__name__)


async def send_and_pin_morning_digest(
    bot: Bot,
    session: AsyncSession,
    user: User,
    settings: UserSettings,
    text: str,
) -> int | None:
    """Send the digest, pin it, persist the (chat_id, message_id) on
    ``settings``. Returns the new ``message_id`` or ``None`` on send failure.

    Pin failures are non-fatal — the digest still goes out, we just don't
    track it for live updates.
    """
    try:
        sent = await bot.send_message(chat_id=user.telegram_id, text=text)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning(
            "pinned_morning.send_failed",
            user_id=user.id,
            error=str(exc)[:200],
        )
        return None

    try:
        await bot.pin_chat_message(
            chat_id=user.telegram_id,
            message_id=sent.message_id,
            disable_notification=True,
        )
    except Exception as exc:
        # Pin is cosmetic. Most common cause: bot is not admin in a
        # group chat. Private chats with the bot don't need this perm.
        # Catch broadly: any failure must not break the digest send.
        logger.info(
            "pinned_morning.pin_failed",
            user_id=user.id,
            error=str(exc)[:200],
        )
        return sent.message_id

    settings.pinned_morning_chat_id = user.telegram_id
    settings.pinned_morning_message_id = sent.message_id
    if user.id is not None:
        # Local date for which this pin represents the morning state. We
        # use ``last_morning_digest_on`` as a proxy — it was just set to
        # today's local date in the caller.
        settings.pinned_morning_date = settings.last_morning_digest_on
    session.add(settings)
    return sent.message_id


async def refresh_pinned_morning(bot: Bot, session: AsyncSession, user_id: int) -> bool:
    """Rebuild the morning digest and ``editMessageText`` the pinned message.

    No-op if there's no current pin or its date is stale (the next morning
    digest will replace it). Returns True if the edit succeeded, False if
    we cleared the pin because Telegram rejected the edit (e.g. user
    unpinned / deleted the message).
    """
    user = await session.get(User, user_id)
    if user is None:
        return False
    settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user_id))
    ).first()
    if settings is None:
        return False
    if settings.pinned_morning_message_id is None or settings.pinned_morning_chat_id is None:
        return False
    # Stale pin from yesterday — let the next morning digest replace it
    # rather than leaking edits to a no-longer-relevant message.
    if settings.pinned_morning_date != settings.last_morning_digest_on:
        return False

    # Imported lazily to break the digest ↔ pinned_today cycle.
    from app.bot.digest import build_morning_digest

    text = await build_morning_digest(session, user)
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=settings.pinned_morning_chat_id,
            message_id=settings.pinned_morning_message_id,
        )
    except TelegramBadRequest as exc:
        msg = str(exc).lower()
        if "message is not modified" in msg:
            # Same content (e.g. concurrent callback). Not an error.
            return True
        # Anything else (message deleted, too old, parse failure, …) →
        # forget the pin so we don't keep retrying.
        logger.info(
            "pinned_morning.edit_rejected",
            user_id=user_id,
            error=str(exc)[:200],
        )
        settings.pinned_morning_chat_id = None
        settings.pinned_morning_message_id = None
        settings.pinned_morning_date = None
        session.add(settings)
        return False
    except TelegramForbiddenError as exc:
        logger.info(
            "pinned_morning.edit_forbidden",
            user_id=user_id,
            error=str(exc)[:200],
        )
        settings.pinned_morning_chat_id = None
        settings.pinned_morning_message_id = None
        settings.pinned_morning_date = None
        session.add(settings)
        return False
    return True
