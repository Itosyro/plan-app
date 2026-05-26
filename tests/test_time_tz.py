"""Regression tests for the non-UTC timezone epoch bug (ROADMAP P0.1).

A naive-UTC datetime's ``.timestamp()`` is interpreted by Python in the
*system local* timezone, so on a non-UTC host it yields an epoch offset by
the local UTC offset. These tests force a non-UTC process timezone via
``time.tzset()`` and assert the time helpers and the auth TTL check stay
correct regardless of ``TZ``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest

from app.api.auth import INIT_DATA_MAX_AGE_SECONDS, parse_init_data
from app.shared.time import to_epoch, utcnow_epoch, utcnow_naive

# A timezone with a large, fixed offset makes the bug glaringly obvious if
# it regresses (UTC-5/-4 -> epoch off by ~4-5h).
_NON_UTC_TZ = "America/New_York"


@pytest.fixture
def non_utc_tz() -> Iterator[None]:
    """Run the body with the process timezone set to a non-UTC zone."""
    prev = os.environ.get("TZ")
    os.environ["TZ"] = _NON_UTC_TZ
    time.tzset()
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = prev
        time.tzset()


def test_utcnow_epoch_matches_aware_utc(non_utc_tz: None) -> None:
    """``utcnow_epoch`` must equal the true aware-UTC epoch, not local."""
    expected = int(datetime.now(UTC).timestamp())
    assert abs(utcnow_epoch() - expected) <= 1


def test_utcnow_epoch_ignores_naive_timestamp_trap(non_utc_tz: None) -> None:
    """The naive ``.timestamp()`` path is wrong; the helper avoids it."""
    naive_epoch = int(utcnow_naive().timestamp())  # the buggy computation
    correct_epoch = utcnow_epoch()
    # On a non-UTC host the two diverge by the local offset (hours).
    assert abs(naive_epoch - correct_epoch) > 3600


def test_to_epoch_treats_naive_as_utc(non_utc_tz: None) -> None:
    """A stored naive-UTC datetime converts to its true UTC epoch."""
    dt = datetime(2026, 5, 26, 12, 0, 0)  # naive UTC
    expected = int(dt.replace(tzinfo=UTC).timestamp())
    assert to_epoch(dt) == expected


def _make_init_data(bot_token: str, *, auth_date: int) -> str:
    user_payload = {"id": 100, "first_name": "Анна", "username": "t"}
    fields: dict[str, str] = {
        "auth_date": str(auth_date),
        "query_id": "AAEAAQ",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    pairs = sorted(fields.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


def test_auth_ttl_accepts_fresh_initdata_under_non_utc_tz(non_utc_tz: None) -> None:
    """A just-issued initData must validate even on a non-UTC host."""
    bot_token = "1234567890:AAFakeTokenForTestingFakeTokenForTesting"
    fresh = int(datetime.now(UTC).timestamp())
    raw = _make_init_data(bot_token, auth_date=fresh)
    # No ``now_ts`` override: exercises the real ``utcnow_epoch()`` default.
    assert parse_init_data(raw, bot_token) is not None


def test_auth_ttl_rejects_expired_initdata_under_non_utc_tz(non_utc_tz: None) -> None:
    """Genuinely stale initData is still rejected on a non-UTC host."""
    bot_token = "1234567890:AAFakeTokenForTestingFakeTokenForTesting"
    stale = int(datetime.now(UTC).timestamp()) - INIT_DATA_MAX_AGE_SECONDS - 120
    raw = _make_init_data(bot_token, auth_date=stale)
    assert parse_init_data(raw, bot_token) is None
