"""Tests for the per-user token-bucket rate limiter (CRIT-2)."""

from __future__ import annotations

from app.bot.rate_limit import RateLimiter, get_rate_limiter, reset_rate_limiter


def test_disabled_when_per_minute_zero() -> None:
    limiter = RateLimiter(per_minute=0, burst=5)
    # Every call allowed regardless of volume.
    assert all(limiter.allow(1, now=0.0) for _ in range(1000))


def test_burst_then_throttle() -> None:
    # 60/min = 1 token/sec, burst 3. Three immediate calls pass, the
    # fourth (same instant) is throttled.
    limiter = RateLimiter(per_minute=60, burst=3)
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is False


def test_refill_over_time() -> None:
    limiter = RateLimiter(per_minute=60, burst=2)  # 1 token/sec
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is False
    # One second later exactly one token has refilled.
    assert limiter.allow(1, now=1.0) is True
    assert limiter.allow(1, now=1.0) is False


def test_per_user_isolation() -> None:
    limiter = RateLimiter(per_minute=60, burst=1)
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=0.0) is False
    # A different user has their own full bucket.
    assert limiter.allow(2, now=0.0) is True


def test_refill_capped_at_capacity() -> None:
    limiter = RateLimiter(per_minute=60, burst=2)
    # Long idle period must not over-fill beyond burst capacity.
    assert limiter.allow(1, now=0.0) is True
    assert limiter.allow(1, now=10_000.0) is True
    assert limiter.allow(1, now=10_000.0) is True
    assert limiter.allow(1, now=10_000.0) is False


def test_prune_removes_full_buckets() -> None:
    limiter = RateLimiter(per_minute=60, burst=2)
    limiter.allow(1, now=0.0)  # bucket for user 1 now below capacity
    # Far in the future the bucket has refilled to full → prunable.
    removed = limiter.prune(now=10_000.0)
    assert removed == 1


def test_get_rate_limiter_is_singleton() -> None:
    reset_rate_limiter()
    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
    reset_rate_limiter()
