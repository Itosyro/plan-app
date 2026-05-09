"""Tests for ``app/api/auth.py`` — initData HMAC validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.api.auth import extract_user, parse_init_data


def _make_init_data(
    bot_token: str,
    *,
    user_id: int = 100,
    auth_date: int | None = None,
    first_name: str = "Юсуф",
    extra: dict[str, str] | None = None,
) -> str:
    """Build a Telegram-spec-compliant ``initData`` string for tests."""
    auth_date = auth_date if auth_date is not None else int(time.time())
    user_payload = {
        "id": user_id,
        "first_name": first_name,
        "username": "tester",
        "language_code": "ru",
    }
    fields: dict[str, str] = {
        "auth_date": str(auth_date),
        "query_id": "AAEAAQ",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    if extra:
        fields.update(extra)
    pairs = sorted(fields.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


@pytest.fixture
def bot_token() -> str:
    return "1234567890:AAFakeTokenForTestingFakeTokenForTesting"


def test_parse_init_data_happy(bot_token: str) -> None:
    raw = _make_init_data(bot_token, user_id=42, first_name="Anna")
    parsed = parse_init_data(raw, bot_token)
    assert parsed is not None
    user = extract_user(parsed)
    assert user is not None
    assert user["id"] == 42
    assert user["first_name"] == "Anna"


def test_parse_init_data_bad_signature(bot_token: str) -> None:
    raw = _make_init_data(bot_token, user_id=42)
    # Tamper with the user field — signature must no longer match.
    tampered = raw.replace("Anna", "Mallory") if "Anna" in raw else raw + "&extra=evil"
    parsed = parse_init_data(tampered, bot_token)
    assert parsed is None


def test_parse_init_data_wrong_token(bot_token: str) -> None:
    raw = _make_init_data(bot_token, user_id=42)
    parsed = parse_init_data(raw, "9999999999:Wrong" + "X" * 30)
    assert parsed is None


def test_parse_init_data_expired(bot_token: str) -> None:
    long_ago = int(time.time()) - 30 * 24 * 60 * 60  # 30 days ago
    raw = _make_init_data(bot_token, user_id=42, auth_date=long_ago)
    parsed = parse_init_data(raw, bot_token)
    assert parsed is None


def test_parse_init_data_future_skew_rejected(bot_token: str) -> None:
    too_far_ahead = int(time.time()) + 600  # 10 min ahead — outside grace
    raw = _make_init_data(bot_token, user_id=42, auth_date=too_far_ahead)
    parsed = parse_init_data(raw, bot_token)
    assert parsed is None


def test_parse_init_data_empty_returns_none(bot_token: str) -> None:
    assert parse_init_data("", bot_token) is None
    assert parse_init_data("foo=bar", bot_token) is None


def test_extract_user_handles_missing_user(bot_token: str) -> None:
    raw = _make_init_data(bot_token)
    parsed = parse_init_data(raw, bot_token)
    assert parsed is not None
    # Wipe user field to simulate corrupted payload.
    parsed_no_user = {k: v for k, v in parsed.items() if k != "user"}
    assert extract_user(parsed_no_user) is None
