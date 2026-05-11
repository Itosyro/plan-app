"""Intent detection for voice/text editing of existing tasks (PR-I1).

Recognises phrases like «сделал йогу», «удали пробежку», «верни задачу»
and returns a structured ``EditIntent`` with the detected action and
target task query.

Uses ``llama-3.1-8b-instant`` via Groq with ``instructor`` for
structured detection — same pattern as ``reorder.py``.
"""

from __future__ import annotations

import time
from pathlib import Path

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter, call_with_rotation
from app.ai.schemas import EditIntent
from app.shared.logging import get_logger

logger = get_logger(__name__)

INTENT_MODEL = "llama-3.1-8b-instant"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "intent.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    """Read the intent system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


async def detect_intent(
    router: GroqKeyRouter,
    user_text: str,
) -> EditIntent:
    """Detect whether *user_text* is an edit command or a new-task creation.

    Returns an ``EditIntent`` with ``intent="create"`` (or ``"none"``)
    for messages that should follow the existing split/classify pipeline,
    and a specific edit intent for recognised commands.
    """
    stripped = user_text.strip()
    if len(stripped) < 2:
        return EditIntent(intent="none", confidence=1.0)

    system_prompt = _load_prompt()

    async def _do_call(r: GroqKeyRouter) -> EditIntent:
        client = instructor.from_groq(
            AsyncGroq(api_key=r.current_key),
            mode=instructor.Mode.JSON,
        )
        return await client.chat.completions.create(
            model=INTENT_MODEL,
            response_model=EditIntent,
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
        "intent.detect",
        intent=result.intent,
        task_query=result.task_query,
        confidence=result.confidence,
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return result
