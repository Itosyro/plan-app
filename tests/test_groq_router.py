"""Tests for GroqKeyRouter — round-robin key rotation and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from groq import APIStatusError, InternalServerError, RateLimitError

from app.ai.router import (
    GroqKeyRouter,
    GroqKeysExhaustedError,
    call_with_rotation,
)


def test_single_key_round_robin() -> None:
    """With one key the router always returns it."""
    router = GroqKeyRouter(keys=["k1"])
    assert router.current_key == "k1"
    assert router.current_key_id == 0
    router.advance()
    assert router.current_key == "k1"
    assert router.current_key_id == 0


def test_multi_key_round_robin() -> None:
    """Keys cycle in order."""
    router = GroqKeyRouter(keys=["k1", "k2", "k3"])
    assert router.current_key == "k1"
    router.advance()
    assert router.current_key == "k2"
    router.advance()
    assert router.current_key == "k3"
    router.advance()
    assert router.current_key == "k1"  # wraps around


def test_empty_keys_raises() -> None:
    """Creating a router with no keys is an error."""
    with pytest.raises(ValueError, match="at least one"):
        GroqKeyRouter(keys=[])


def test_async_client_uses_current_key() -> None:
    """The async client should be constructed with the current key."""
    router = GroqKeyRouter(keys=["gsk_aaa", "gsk_bbb"])
    client = router.async_client()
    assert client.api_key == "gsk_aaa"
    router.advance()
    client2 = router.async_client()
    assert client2.api_key == "gsk_bbb"


def test_keys_exhausted_error_message() -> None:
    """GroqKeysExhaustedError is a RuntimeError with a clear message."""
    err = GroqKeysExhaustedError("test")
    assert isinstance(err, RuntimeError)
    assert "test" in str(err)


# ── call_with_rotation tests (I-1) ───────────────────────────────────


def _rate_limit_error() -> RateLimitError:
    """Construct a RateLimitError as if Groq returned a 429."""
    body = MagicMock()
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=429, request=request)
    return RateLimitError("rate limit", response=response, body=body)


def _server_error() -> InternalServerError:
    """Construct an InternalServerError as if Groq returned a 500."""
    body = MagicMock()
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=500, request=request)
    return InternalServerError("server error", response=response, body=body)


def _bad_request_error() -> APIStatusError:
    """Construct a 400 (bad-request) APIStatusError — NOT recoverable."""
    body = MagicMock()
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=400, request=request)
    return APIStatusError("bad request", response=response, body=body)


@pytest.mark.asyncio
async def test_call_with_rotation_success_no_advance() -> None:
    """If fn succeeds on first try, advance() is never called."""
    router = GroqKeyRouter(keys=["k1", "k2"])

    call_count = 0

    async def _fn(r: GroqKeyRouter) -> str:
        nonlocal call_count
        call_count += 1
        return f"ok-{r.current_key}"

    result = await call_with_rotation(router, _fn)
    assert result == "ok-k1"
    assert call_count == 1
    assert router.current_key == "k1"  # did not advance


@pytest.mark.asyncio
async def test_call_with_rotation_advances_on_rate_limit() -> None:
    """RateLimitError triggers key rotation; second key succeeds."""
    router = GroqKeyRouter(keys=["k1", "k2", "k3"])

    attempts: list[str] = []

    async def _fn(r: GroqKeyRouter) -> str:
        attempts.append(r.current_key)
        if r.current_key == "k1":
            raise _rate_limit_error()
        return f"ok-{r.current_key}"

    result = await call_with_rotation(router, _fn)
    assert result == "ok-k2"
    assert attempts == ["k1", "k2"]
    assert router.current_key == "k2"


@pytest.mark.asyncio
async def test_call_with_rotation_advances_on_5xx() -> None:
    """5xx server error also triggers rotation."""
    router = GroqKeyRouter(keys=["k1", "k2"])

    async def _fn(r: GroqKeyRouter) -> str:
        if r.current_key == "k1":
            raise _server_error()
        return "ok"

    result = await call_with_rotation(router, _fn)
    assert result == "ok"


@pytest.mark.asyncio
async def test_call_with_rotation_propagates_4xx() -> None:
    """A 400 (bad request) is NOT recoverable — propagate immediately."""
    router = GroqKeyRouter(keys=["k1", "k2"])

    attempts = 0

    async def _fn(r: GroqKeyRouter) -> str:
        nonlocal attempts
        attempts += 1
        raise _bad_request_error()

    with pytest.raises(APIStatusError):
        await call_with_rotation(router, _fn)
    assert attempts == 1  # no retry, no rotation


@pytest.mark.asyncio
async def test_call_with_rotation_exhausts_pool() -> None:
    """If every key fails with a recoverable error, raise GroqKeysExhaustedError."""
    router = GroqKeyRouter(keys=["k1", "k2"])

    async def _fn(r: GroqKeyRouter) -> str:
        raise _rate_limit_error()

    with pytest.raises(GroqKeysExhaustedError) as exc_info:
        await call_with_rotation(router, _fn)
    # The original RateLimitError is chained as __cause__ for debugging.
    assert isinstance(exc_info.value.__cause__, RateLimitError)


@pytest.mark.asyncio
async def test_call_with_rotation_propagates_unexpected() -> None:
    """Unexpected exceptions (e.g. ValueError) propagate without rotation."""
    router = GroqKeyRouter(keys=["k1", "k2"])

    attempts = 0

    async def _fn(r: GroqKeyRouter) -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        await call_with_rotation(router, _fn)
    assert attempts == 1  # no rotation
