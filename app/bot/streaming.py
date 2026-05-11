"""Progressive ("streaming") message rendering for chat replies.

Telegram doesn't expose a server-sent-events channel for bot messages,
but we can fake the appearance of a typed-out reply by:

1. Sending a placeholder message immediately ("⏳ …").
2. Editing it line-by-line via ``editMessageText`` as the courier
   output is revealed, with a small inter-edit delay to look natural.
3. Periodically sending a ``typing`` chat action to keep the "is
   typing…" indicator visible if the user is watching.

The helper is *fail-soft*: any TelegramAPIError is logged and the loop
continues with the next chunk. The final edit is always attempted in a
``try/except`` so a temporary 429/RetryAfter doesn't drop the answer.

We deliberately don't use ``parse_mode`` — courier output may contain
user-controlled task titles, and unescaped Markdown there is the
Phase-2 incident we already fixed.
"""

from __future__ import annotations

import asyncio
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, Message

from app.shared.logging import get_logger

logger = get_logger(__name__)

# Telegram tolerates ~1 edit/sec sustained on a single message before
# returning ``RetryAfter``. 350 ms is a comfortable middle ground that
# still feels "typed".
_DEFAULT_CHUNK_DELAY: Final[float] = 0.35

# Some clients re-render the whole bubble on every edit. Coalescing
# very short lines avoids visible "jumpy" edits.
_MIN_GROW_BYTES: Final[int] = 8


async def stream_reply(
    placeholder: Message,
    full_text: str,
    *,
    chunk_delay: float = _DEFAULT_CHUNK_DELAY,
    bot: Bot | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Edit ``placeholder`` progressively until it shows ``full_text``.

    Returns the (final) message reference. ``bot`` is optional: when
    provided we'll periodically send a typing action so the user sees
    "печатает…" between edits.
    """
    full_text = (full_text or "").rstrip()
    if not full_text:
        return placeholder

    lines = full_text.split("\n")
    # First chunk: anything up to the first non-empty line, then keep
    # growing one line at a time. This avoids a long pause where only
    # the placeholder is visible.
    accumulated_chars = 0
    last_displayed = ""
    last_edit_at = 0.0

    chat_id = placeholder.chat.id

    async def _edit(text: str) -> None:
        nonlocal last_displayed, last_edit_at
        if text == last_displayed:
            return
        try:
            await placeholder.edit_text(text)
            last_displayed = text
            last_edit_at = asyncio.get_event_loop().time()
        except TelegramRetryAfter as exc:
            await asyncio.sleep(min(exc.retry_after, 5))
            try:
                await placeholder.edit_text(text)
                last_displayed = text
            except TelegramBadRequest:
                logger.debug("stream.edit.no_change")
            except Exception:
                logger.exception("stream.edit.failed_after_retry")
        except TelegramBadRequest:
            # ``message is not modified`` — Telegram refuses no-op edits.
            logger.debug("stream.edit.no_change")
        except Exception:
            logger.exception("stream.edit.failed")

    async def _typing() -> None:
        if bot is None:
            return
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            logger.debug("stream.typing.failed", exc_info=True)

    revealed: list[str] = []
    for i, line in enumerate(lines):
        revealed.append(line)
        accumulated_chars += len(line)
        is_last = i == len(lines) - 1
        # Coalesce: don't edit if we only added a handful of characters
        # since the previous edit, unless this is the final chunk.
        if not is_last and accumulated_chars < _MIN_GROW_BYTES:
            continue
        accumulated_chars = 0
        await _edit("\n".join(revealed))
        if not is_last:
            await _typing()
            await asyncio.sleep(chunk_delay)

    # Always make sure the final state is the full text.
    if reply_markup is not None:
        try:
            await placeholder.edit_text(full_text, reply_markup=reply_markup)
        except TelegramBadRequest:
            logger.debug("stream.edit.no_change")
        except Exception:
            logger.exception("stream.edit.failed_final")
    else:
        await _edit(full_text)
    return placeholder
