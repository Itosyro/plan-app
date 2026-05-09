"""Best-effort wrapper around Telegram's ``setMessageReaction`` (Bot API 7.0).

Phase 6.1 — show a quick reaction on the user's message instead of a text
reply: ``👀`` while the pipeline thinks, ``🎉`` when the Courier reply is
out, ``😢`` if anything blew up. Cheap, non-intrusive feedback that maps to
the same allowed-emoji set Telegram already exposes to clients.

All public helpers swallow exceptions and log warnings — reactions are
purely cosmetic and must never fail an otherwise-successful pipeline run.
The set of allowed emojis is enforced as an allow-list to prevent typos
or future Telegram restrictions from raising at call sites.
"""

from __future__ import annotations

from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ReactionTypeEmoji

from app.shared.logging import get_logger

logger = get_logger(__name__)

#: Allow-list of emojis we use in plan-app. These are all officially in
#: Telegram's documented "available emoji" set (Bot API 10.0). Anything
#: outside this list is rejected client-side to avoid the dynamic-allow-
#: list anti-pattern flagged in the defensive-programming skill.
RECEIVE: Final[str] = "👀"
SUCCESS: Final[str] = "🎉"
ERROR: Final[str] = "😢"

_ALLOWED: Final[frozenset[str]] = frozenset({RECEIVE, SUCCESS, ERROR})


async def set_reaction(
    bot: Bot,
    chat_id: int,
    message_id: int,
    emoji: str,
) -> bool:
    """Set a single emoji reaction on a message. Best-effort, non-raising.

    Returns ``True`` on success and ``False`` on any error (network,
    Telegram BadRequest, non-allowed emoji, …). Never raises.
    """
    if emoji not in _ALLOWED:
        logger.warning(
            "reaction.rejected_unknown_emoji",
            emoji=emoji,
            chat_id=chat_id,
            message_id=message_id,
        )
        return False
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
    except TelegramBadRequest as exc:
        # E.g. message too old (>48h), bot doesn't have permission, message
        # deleted between receive and reaction. Not actionable, just log.
        logger.info(
            "reaction.bad_request",
            emoji=emoji,
            chat_id=chat_id,
            message_id=message_id,
            description=str(exc),
        )
        return False
    except Exception:
        logger.warning(
            "reaction.failed",
            emoji=emoji,
            chat_id=chat_id,
            message_id=message_id,
            exc_info=True,
        )
        return False
    return True


async def clear_reaction(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Remove all reactions from a message. Best-effort, non-raising."""
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[],
        )
    except Exception:
        logger.info(
            "reaction.clear_failed",
            chat_id=chat_id,
            message_id=message_id,
            exc_info=True,
        )
        return False
    return True
