"""Tests for GroqKeyRouter — round-robin key rotation and error handling."""

from __future__ import annotations

import pytest

from app.ai.router import GroqKeyRouter, GroqKeysExhaustedError


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
