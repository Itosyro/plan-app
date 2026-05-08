"""Round-robin Groq API key router.

Cycles through a pool of Groq API keys. On 429 or 5xx the caller
should call ``advance()`` to switch to the next key.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from groq import AsyncGroq


class GroqKeysExhaustedError(RuntimeError):
    """All Groq API keys have been tried and none succeeded."""


@dataclass
class GroqKeyRouter:
    """Simple round-robin key pool for Groq API calls."""

    keys: list[str]
    _index: int = field(default=0, init=False, repr=False)

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
        return AsyncGroq(api_key=self.current_key)
