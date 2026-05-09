"""Tests for ``app.bot.reactions`` (Bot API 10.0 setMessageReaction wrapper).

We don't go through aiogram's HTTP layer — we hand the helpers a fake bot
whose ``set_message_reaction`` records its arguments and can be made to
raise on demand. Six scenarios:

1. Happy path: emoji from the allow-list is forwarded with the right
   ``chat_id`` / ``message_id`` and wrapped in ``ReactionTypeEmoji``.
2. Unknown emoji is rejected client-side (no network call) and returns
   ``False``.
3. ``TelegramBadRequest`` (e.g. message too old) is swallowed → ``False``.
4. Any other ``Exception`` is swallowed → ``False``.
5. ``clear_reaction`` sends an empty list → ``True``.
6. ``clear_reaction`` swallows errors → ``False``.
"""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ReactionTypeEmoji

from app.bot import reactions


class _FakeBot:
    """Records every ``set_message_reaction`` call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raise: BaseException | None = None

    async def set_message_reaction(
        self,
        chat_id: int,
        message_id: int,
        reaction: list[Any] | None = None,
        **_: Any,
    ) -> bool:
        if self._raise is not None:
            err, self._raise = self._raise, None
            raise err
        self.calls.append({"chat_id": chat_id, "message_id": message_id, "reaction": reaction})
        return True


@pytest.mark.asyncio
async def test_set_reaction_happy_path() -> None:
    bot = _FakeBot()
    ok = await reactions.set_reaction(bot, 100, 200, reactions.RECEIVE)  # type: ignore[arg-type]
    assert ok is True
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call["chat_id"] == 100
    assert call["message_id"] == 200
    assert call["reaction"] == [ReactionTypeEmoji(emoji=reactions.RECEIVE)]


@pytest.mark.asyncio
async def test_set_reaction_rejects_unknown_emoji() -> None:
    bot = _FakeBot()
    ok = await reactions.set_reaction(bot, 1, 2, "🦄")  # type: ignore[arg-type]
    assert ok is False
    assert bot.calls == []  # never hit Telegram


@pytest.mark.asyncio
async def test_set_reaction_swallows_telegram_bad_request() -> None:
    bot = _FakeBot()
    bot._raise = TelegramBadRequest(method=None, message="message can't be edited")  # type: ignore[arg-type]
    ok = await reactions.set_reaction(bot, 1, 2, reactions.SUCCESS)  # type: ignore[arg-type]
    assert ok is False


@pytest.mark.asyncio
async def test_set_reaction_swallows_other_errors() -> None:
    bot = _FakeBot()
    bot._raise = RuntimeError("network down")
    ok = await reactions.set_reaction(bot, 1, 2, reactions.ERROR)  # type: ignore[arg-type]
    assert ok is False


@pytest.mark.asyncio
async def test_clear_reaction_sends_empty_list() -> None:
    bot = _FakeBot()
    ok = await reactions.clear_reaction(bot, 1, 2)  # type: ignore[arg-type]
    assert ok is True
    assert bot.calls[0]["reaction"] == []


@pytest.mark.asyncio
async def test_clear_reaction_swallows_errors() -> None:
    bot = _FakeBot()
    bot._raise = RuntimeError("boom")
    ok = await reactions.clear_reaction(bot, 1, 2)  # type: ignore[arg-type]
    assert ok is False


def test_allowed_set_is_frozen_and_documented() -> None:
    """Defensive: emoji constants stay in lock-step with the allow-list."""
    assert reactions.RECEIVE in reactions._ALLOWED
    assert reactions.SUCCESS in reactions._ALLOWED
    assert reactions.ERROR in reactions._ALLOWED
    assert isinstance(reactions._ALLOWED, frozenset)
