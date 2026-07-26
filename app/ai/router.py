"""Round-robin Groq API key router with retry-on-failure helper.

The bot ships with a pool of Groq API keys to spread the free-tier
rate limits across multiple accounts. ``GroqKeyRouter`` cycles
through them; the ``call_with_rotation`` helper wraps an async
callable and, if it raises a recoverable Groq error (429 rate-limit
or 5xx server error), advances to the next key and retries.

See ``docs/REVIEW-2026-05-09.md::I-1`` — historically every Groq
call site invoked the LLM directly with ``router.current_key``,
nobody ever called ``router.advance()``, so the rotation was dead
code. ``call_with_rotation`` is the only sanctioned way to make a
Groq call from the AI modules; the helper guarantees ``advance()``
is called on the right errors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from groq import APIStatusError, AsyncGroq, InternalServerError, RateLimitError

from app.shared.logging import get_logger

logger = get_logger(__name__)


class GroqKeysExhaustedError(RuntimeError):
    """All Groq API keys have been tried and none succeeded."""


@dataclass
class GroqKeyRouter:
    """Simple round-robin key pool for Groq API calls."""

    keys: list[str]
    _index: int = field(default=0, init=False, repr=False)
    _clients: dict[int, AsyncGroq] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("GroqKeyRouter requires at least one API key.")

    @property
    def current_key(self) -> str:
        return self.keys[self._index % len(self.keys)]

    @property
    def current_key_id(self) -> int:
        return self._index % len(self.keys)

    def advance(self) -> None:
        self._index += 1

    def async_client(self) -> AsyncGroq:
        """Return a cached ``AsyncGroq`` client for the current key.

        Creating ``AsyncGroq`` per call meant a fresh httpx pool and TLS
        handshake on every LLM request; clients are lazy-cached per key
        instead. ``instructor.from_groq`` stays per-call at the call
        sites — it is a thin stateless wrapper over this client.
        """
        # Лениво кэшируем клиент на ключ — event loop у бота один,
        # поэтому блокировка не нужна.
        key_id = self.current_key_id
        client = self._clients.get(key_id)
        if client is None:
            client = AsyncGroq(api_key=self.current_key)
            self._clients[key_id] = client
        return client


def _is_recoverable_groq_error(exc: BaseException) -> bool:
    """Return True if ``exc`` indicates we should rotate to the next key.

    Triggered by 429 (rate limit) and 5xx (server error). 4xx other
    than 429 means the request itself is bad (e.g. malformed prompt,
    invalid model) — rotating keys won't help, so propagate.
    """
    if isinstance(exc, RateLimitError | InternalServerError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


async def call_with_rotation[T](
    router: GroqKeyRouter,
    fn: Callable[[GroqKeyRouter], Awaitable[T]],
) -> T:
    """Invoke ``fn(router)`` with key-rotation on recoverable errors.

    Tries each key in the pool exactly once (starting from the current
    one). On ``RateLimitError`` / ``InternalServerError`` / 5xx
    ``APIStatusError`` the helper calls ``router.advance()`` and
    retries. Any other exception is re-raised immediately. If every
    key in the pool failed, raises ``GroqKeysExhaustedError`` with the
    last error chained via ``__cause__``.

    Used by every AI module — ``splitter``, ``time_resolver``,
    ``classifier``, ``critic``, ``courier``, ``reorder``, ``whisper``
    — to pick up rate-limit failover for free.
    """
    attempts = len(router.keys)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await fn(router)
        except Exception as exc:
            if not _is_recoverable_groq_error(exc):
                raise
            last_exc = exc
            logger.warning(
                "groq.key_rotation",
                attempt=attempt + 1,
                max_attempts=attempts,
                key_id=router.current_key_id,
                error_type=type(exc).__name__,
            )
            router.advance()
    raise GroqKeysExhaustedError(
        f"All {attempts} Groq keys failed with recoverable errors."
    ) from last_exc
