"""Telegram Mini-App authentication.

Validates the ``WebApp.initData`` query string that Telegram embeds in
every Mini App load (and refreshes on every reopen). The signature is an
HMAC-SHA256 over the sorted ``key=value`` pairs (excluding ``hash``) using
``HMAC-SHA256("WebAppData", bot_token)`` as the key — see
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app.

The Mini-App frontend forwards ``initData`` to the API in the
``X-Telegram-Init-Data`` HTTP header (or ``?init_data=...`` query
parameter as a fallback for tooling that strips custom headers). The
``current_user`` dependency below validates the signature, ensures the
``auth_date`` is fresh, looks up our internal ``User`` row by Telegram
``id``, and returns it. Unauthorised callers see 401 (no/invalid
init-data) or 404 (no matching user — i.e. they have never run
``/start``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Final
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, Query, status
from sqlmodel import select

from app.db.base import session_scope
from app.db.models import User
from app.shared.config import Settings, get_settings
from app.shared.logging import get_logger
from app.shared.time import utcnow_naive

logger = get_logger(__name__)

# Telegram says ``auth_date`` must be checked to prevent replay. 24 h is
# the recommended ceiling — anything older we treat as invalid even if
# the signature still matches.
INIT_DATA_MAX_AGE_SECONDS: Final[int] = 24 * 60 * 60


def _hex_digest(secret: bytes, msg: bytes) -> bytes:
    """HMAC-SHA256 raw digest helper."""
    return hmac.new(secret, msg, hashlib.sha256).digest()


def _check_signature(parsed: Mapping[str, str], bot_token: str) -> bool:
    """Return ``True`` iff ``parsed['hash']`` matches the expected digest.

    The data-check string is built per Telegram spec: take every key
    except ``hash``, sort by key, format as ``key=value`` and join with
    ``\\n``. The HMAC key is itself an HMAC of the bot token with the
    constant string ``"WebAppData"``.
    """
    received_hash = parsed.get("hash")
    if not received_hash:
        return False
    pairs = sorted((k, v) for k, v in parsed.items() if k != "hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret_key = _hex_digest(b"WebAppData", bot_token.encode("utf-8"))
    expected = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_hash)


def parse_init_data(
    raw: str,
    bot_token: str,
    *,
    now_ts: int | None = None,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
) -> dict[str, str] | None:
    """Validate and parse a Telegram ``initData`` query string.

    Returns the parsed key→value dict on success or ``None`` on any
    validation failure (bad signature, expired ``auth_date``, missing
    fields). The dict still contains ``hash`` and the JSON-encoded
    ``user`` field (call :func:`extract_user` to decode the latter).
    """
    if not raw or not bot_token:
        return None
    parsed = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))
    if not _check_signature(parsed, bot_token):
        return None
    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw is None:
        return None
    try:
        auth_date = int(auth_date_raw)
    except ValueError:
        return None
    now = now_ts if now_ts is not None else int(utcnow_naive().timestamp())
    if auth_date > now + 60:  # 60 s grace for clock skew
        return None
    if now - auth_date > max_age_seconds:
        return None
    return parsed


def extract_user(parsed: Mapping[str, str]) -> dict[str, object] | None:
    """Decode the ``user`` JSON field from a parsed init-data dict."""
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        decoded = json.loads(user_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


async def current_user(
    x_telegram_init_data: str | None = Header(default=None),
    init_data: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency that resolves the request's authenticated user.

    Order of precedence: ``X-Telegram-Init-Data`` header > ``init_data``
    query parameter. Returns the matching ``User`` row, or raises
    ``HTTPException`` (401 for missing/invalid init-data, 404 if the
    Telegram user has not yet run ``/start`` and onboarded).
    """
    raw = x_telegram_init_data or init_data
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing init-data",
        )
    if not settings.telegram_bot_token:
        # Defence-in-depth: an unconfigured deploy must not silently
        # accept everything. Treat as 503 so callers know it's a server
        # config error, not their fault.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bot token not configured",
        )
    parsed = parse_init_data(raw, settings.telegram_bot_token)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad init-data",
        )
    user_payload = extract_user(parsed)
    if user_payload is None or "id" not in user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad init-data: no user",
        )
    raw_id = user_payload["id"]
    if not isinstance(raw_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad init-data: bad user.id",
        )
    async with session_scope() as session:
        result = await session.exec(select(User).where(User.telegram_id == raw_id))
        user = result.first()
    if user is None or user.id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not onboarded",
        )
    return user


__all__ = [
    "INIT_DATA_MAX_AGE_SECONDS",
    "current_user",
    "extract_user",
    "parse_init_data",
]
