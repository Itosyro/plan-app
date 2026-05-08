"""Reorder — detect and execute task rescheduling requests.

Recognises phrases like «перенеси задачу X на завтра» and updates
the task's horizon (and optionally due_at) in the database.

Uses ``llama-3.1-8b-instant`` via Groq with ``instructor`` for
structured detection of reorder intent.
"""

from __future__ import annotations

import time
from pathlib import Path

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter
from app.ai.schemas import ReorderRequest
from app.shared.logging import get_logger

logger = get_logger(__name__)

REORDER_MODEL = "llama-3.1-8b-instant"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reorder.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    """Read the reorder system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


async def detect_reorder(
    router: GroqKeyRouter,
    user_text: str,
) -> ReorderRequest:
    """Detect whether user_text is a task reorder request.

    Returns a ``ReorderRequest`` with ``is_reorder=True`` if the user
    wants to move/reschedule an existing task, or ``is_reorder=False``
    if this is a normal message.
    """
    stripped = user_text.strip()
    if len(stripped) < 3:
        return ReorderRequest(
            is_reorder=False,
            task_query=None,
            target_horizon=None,
            target_raw=None,
        )

    system_prompt = _load_prompt()

    client = instructor.from_groq(
        AsyncGroq(api_key=router.current_key),
        mode=instructor.Mode.JSON,
    )

    t0 = time.monotonic()
    result = await client.chat.completions.create(
        model=REORDER_MODEL,
        response_model=ReorderRequest,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": stripped},
        ],
        temperature=0.0,
        max_retries=2,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "reorder.detect",
        is_reorder=result.is_reorder,
        task_query=result.task_query,
        target_horizon=result.target_horizon,
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return result
