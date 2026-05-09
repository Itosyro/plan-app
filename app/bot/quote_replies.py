"""Helpers for Bot API 7.0+ ``reply_parameters`` (incl. the ``quote`` field).

Phase 6.2 — anchor the bot's reply to the user's original message and,
when we have a meaningful fragment to highlight (e.g. the task name a
reorder request couldn't resolve), pin a quote span on top so the user
sees the bot literally "pointing at" the right phrase.

Quoting is best-effort: if the substring isn't a verbatim slice of the
original message, Telegram rejects the call. We validate locally and
fall back to plain anchoring.
"""

from __future__ import annotations

from aiogram.types import ReplyParameters


def reply_to(
    *,
    chat_id: int,
    message_id: int,
    quote: str | None = None,
    allow_sending_without_reply: bool = True,
) -> ReplyParameters:
    """Build ``ReplyParameters`` anchoring to ``(chat_id, message_id)``.

    If ``quote`` is provided, it is forwarded as-is (Telegram requires it
    to be a verbatim substring of the target message — caller must ensure
    that). Defaults to ``allow_sending_without_reply=True`` so we don't
    explode if the user deletes their message between send and reply.
    """
    params: dict[str, object] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "allow_sending_without_reply": allow_sending_without_reply,
    }
    if quote:
        params["quote"] = quote
    return ReplyParameters(**params)  # type: ignore[arg-type]


def safe_quote(haystack: str, needle: str, *, max_len: int = 64) -> str | None:
    """Return ``needle`` if it occurs verbatim in ``haystack``, else ``None``.

    Telegram requires ``ReplyParameters.quote`` to be a contiguous
    substring of the target message; otherwise the API returns
    ``QUOTE_TEXT_INVALID``. We also cap the length so we never try to
    "quote" a multi-paragraph fragment.
    """
    if not needle or not haystack:
        return None
    snippet = needle.strip()
    if not snippet:
        return None
    if len(snippet) > max_len:
        snippet = snippet[:max_len].rstrip()
    return snippet if snippet in haystack else None
