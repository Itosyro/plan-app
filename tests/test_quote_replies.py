"""Tests for ``app.bot.quote_replies`` helpers."""

from __future__ import annotations

from aiogram.types import ReplyParameters

from app.bot.quote_replies import reply_to, safe_quote


def test_reply_to_anchors_to_message() -> None:
    params = reply_to(chat_id=10, message_id=20)
    assert isinstance(params, ReplyParameters)
    assert params.chat_id == 10
    assert params.message_id == 20
    assert params.allow_sending_without_reply is True
    assert params.quote is None


def test_reply_to_with_quote() -> None:
    params = reply_to(chat_id=1, message_id=2, quote="hello")
    assert params.quote == "hello"


def test_reply_to_empty_quote_omits_field() -> None:
    params = reply_to(chat_id=1, message_id=2, quote="")
    # Empty string is treated like None — never sent to Telegram.
    assert params.quote is None


def test_safe_quote_returns_substring_when_match() -> None:
    haystack = "Завтра в 11 совещание про отчёт"
    needle = "совещание"
    assert safe_quote(haystack, needle) == "совещание"


def test_safe_quote_returns_none_when_not_substring() -> None:
    assert safe_quote("foo bar", "baz") is None


def test_safe_quote_returns_none_for_empty_inputs() -> None:
    assert safe_quote("", "anything") is None
    assert safe_quote("anything", "") is None
    assert safe_quote("anything", "   ") is None


def test_safe_quote_truncates_long_needle() -> None:
    haystack = "x" * 100
    needle = "x" * 80
    quoted = safe_quote(haystack, needle, max_len=10)
    assert quoted == "xxxxxxxxxx"
    # Fallback also requires the (now-truncated) snippet to be a substring,
    # which "xxxxxxxxxx" is. With max_len=200 the original 80x would pass
    # through unchanged.
    quoted2 = safe_quote(haystack, needle, max_len=200)
    assert quoted2 == needle
