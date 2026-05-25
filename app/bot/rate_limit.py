"""In-memory per-user token-bucket rate limiter for the LLM pipeline.

A single user (or a leaked bot token) sending hundreds of messages a
minute would fan out into hundreds of Groq calls — real money and a
denial-of-wallet vector (CRIT-2 in the 2026-05 security review). This
module gates the expensive pipeline behind a cheap per-user token
bucket held in process memory.

Why in-memory and not Redis: the bot runs as a single Render web
service (one process), so a module-level dict is sufficient and
avoids a new infra dependency. If we ever scale to multiple workers
this must move to a shared store — the public API here (``allow``)
stays the same, only the backing store changes.

The bucket is intentionally simple and lock-free: asyncio runs our
handlers cooperatively on one thread, so the read-modify-write of a
bucket entry never interleaves with another coroutine mid-statement.
"""

from __future__ import annotations

import time

__all__ = ["RateLimiter", "get_rate_limiter", "reset_rate_limiter"]


class RateLimiter:
    """Token bucket keyed by Telegram user id.

    ``capacity`` tokens, refilling at ``refill_per_sec``. Each
    :meth:`allow` call costs one token and returns whether it was
    available. A ``per_minute`` of 0 disables limiting (every call is
    allowed) so the feature can be turned off via config without
    branching at call sites.
    """

    def __init__(self, *, per_minute: int, burst: int) -> None:
        self._enabled = per_minute > 0
        self._capacity = float(max(burst, 1))
        self._refill_per_sec = per_minute / 60.0
        # user_id -> (tokens, last_refill_monotonic)
        self._buckets: dict[int, tuple[float, float]] = {}

    def allow(self, user_id: int, *, now: float | None = None) -> bool:
        """Consume one token for *user_id*; return ``False`` if empty."""
        if not self._enabled:
            return True
        ts = now if now is not None else time.monotonic()
        tokens, last = self._buckets.get(user_id, (self._capacity, ts))
        # Refill proportional to elapsed time, capped at capacity.
        tokens = min(self._capacity, tokens + (ts - last) * self._refill_per_sec)
        if tokens < 1.0:
            self._buckets[user_id] = (tokens, ts)
            return False
        self._buckets[user_id] = (tokens - 1.0, ts)
        return True

    def prune(self, *, now: float | None = None) -> int:
        """Drop fully-refilled idle buckets to bound memory.

        A bucket back at full capacity carries no state worth keeping —
        the next :meth:`allow` would recreate it identically. Returns
        the number of entries removed. Safe to call periodically; not
        required for correctness.
        """
        ts = now if now is not None else time.monotonic()
        stale = [
            uid
            for uid, (tokens, last) in self._buckets.items()
            if min(self._capacity, tokens + (ts - last) * self._refill_per_sec) >= self._capacity
        ]
        for uid in stale:
            del self._buckets[uid]
        return len(stale)


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide limiter, building it from settings once."""
    global _limiter
    if _limiter is None:
        # Imported lazily to avoid a config import at module load (keeps
        # this module importable in isolation for unit tests).
        from app.shared.config import get_settings

        settings = get_settings()
        _limiter = RateLimiter(
            per_minute=settings.rate_limit_per_minute,
            burst=settings.rate_limit_burst,
        )
    return _limiter


def reset_rate_limiter() -> None:
    """Drop the cached limiter (tests rebuild it with fresh settings)."""
    global _limiter
    _limiter = None
