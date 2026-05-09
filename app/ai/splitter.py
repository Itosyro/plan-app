"""Splitter — split a user message into atomic intent units.

Uses ``llama-3.1-8b-instant`` via Groq with ``instructor`` for structured
output. The prompt lives in ``app/ai/prompts/splitter.md``.

Phase 2.1: called from the text router, results are logged but **not**
persisted yet (no Task/Note models until Phase 2.2).
"""

from __future__ import annotations

import time
from pathlib import Path

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter, call_with_rotation
from app.ai.schemas import SplitterResult
from app.shared.logging import get_logger

logger = get_logger(__name__)

SPLITTER_MODEL = "llama-3.1-8b-instant"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "splitter.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    """Read the splitter system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


async def split_message(
    router: GroqKeyRouter,
    user_text: str,
) -> SplitterResult:
    """Split *user_text* into atomic intent units via LLM.

    Returns a ``SplitterResult`` with zero or more ``IntentUnit`` items.
    Empty or very short messages (< 2 chars) are short-circuited without
    an LLM call.
    """
    stripped = user_text.strip()
    if len(stripped) < 2:
        logger.info("splitter.skip_short", text_len=len(stripped))
        return SplitterResult(units=[])

    system_prompt = _load_prompt()

    async def _do_call(r: GroqKeyRouter) -> SplitterResult:
        client = instructor.from_groq(
            AsyncGroq(api_key=r.current_key),
            mode=instructor.Mode.JSON,
        )
        return await client.chat.completions.create(
            model=SPLITTER_MODEL,
            response_model=SplitterResult,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": stripped},
            ],
            temperature=0.0,
            max_retries=2,
        )

    t0 = time.monotonic()
    result = await call_with_rotation(router, _do_call)
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "splitter.done",
        text_len=len(stripped),
        units_count=len(result.units),
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return result
