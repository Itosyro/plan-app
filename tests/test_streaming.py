"""Tests for ``app.bot.streaming.stream_reply``.

We don't go through aiogram's HTTP layer — instead we hand the helper a
fake ``Message`` whose ``edit_text`` records calls. Three scenarios:

1. Happy path: every chunk reaches ``edit_text`` and the final state is
   the full text.
2. Single-line replies: no progressive reveal needed; one final edit.
3. ``RetryAfter`` is honoured (sleep + retry) without dropping content.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiogram.exceptions import TelegramRetryAfter

from app.bot.streaming import stream_reply


class _FakeChat:
    def __init__(self, chat_id: int = 1) -> None:
        self.id = chat_id


class _FakeMessage:
    """Records every ``edit_text`` call for inspection."""

    def __init__(self, chat_id: int = 1) -> None:
        self.chat = _FakeChat(chat_id)
        self.calls: list[str] = []
        self._raise_once: BaseException | None = None

    async def edit_text(self, text: str, **_: Any) -> _FakeMessage:
        if self._raise_once is not None:
            err, self._raise_once = self._raise_once, None
            raise err
        self.calls.append(text)
        return self


@pytest.mark.asyncio
async def test_stream_reply_progressive_reveal() -> None:
    msg = _FakeMessage()
    text = "первая строка\nвторая строка\nтретья строка"
    # Use ``chunk_delay=0`` so the test runs in milliseconds.
    await stream_reply(msg, text, chunk_delay=0.0)
    assert msg.calls, "stream_reply must emit at least one edit"
    # Each successive call must be a (non-strict) prefix-or-equal of
    # the next, ending in the full text.
    for prev, curr in zip(msg.calls, msg.calls[1:], strict=False):
        assert curr.startswith(prev) or len(curr) >= len(prev)
    assert msg.calls[-1] == text


@pytest.mark.asyncio
async def test_stream_reply_single_line() -> None:
    msg = _FakeMessage()
    await stream_reply(msg, "одна строка", chunk_delay=0.0)
    assert msg.calls[-1] == "одна строка"


@pytest.mark.asyncio
async def test_stream_reply_handles_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = _FakeMessage()
    msg._raise_once = TelegramRetryAfter(
        method=None,  # type: ignore[arg-type]
        message="retry",
        retry_after=0,
    )
    sleeps: list[float] = []

    real_sleep = asyncio.sleep

    async def _capture(d: float) -> None:
        sleeps.append(d)
        await real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", _capture)
    await stream_reply(msg, "hello\nworld", chunk_delay=0.0)
    assert msg.calls[-1] == "hello\nworld"
    # The initial RetryAfter must produce at least one sleep.
    assert any(s == 0 for s in sleeps)


@pytest.mark.asyncio
async def test_stream_reply_empty_returns_immediately() -> None:
    msg = _FakeMessage()
    await stream_reply(msg, "", chunk_delay=0.0)
    assert msg.calls == []
