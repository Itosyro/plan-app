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

from app.ai._safety import wrap_untrusted
from app.ai.models import get_models
from app.ai.router import GroqKeyRouter, call_with_rotation
from app.ai.schemas import ReorderRequest
from app.shared.logging import get_logger

logger = get_logger(__name__)

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

    async def _do_call(r: GroqKeyRouter) -> ReorderRequest:
        client = instructor.from_groq(
            AsyncGroq(api_key=r.current_key),
            mode=instructor.Mode.JSON,
        )
        return await client.chat.completions.create(
            model=get_models().reorder,
            response_model=ReorderRequest,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": wrap_untrusted(stripped)},
            ],
            temperature=0.0,
            max_retries=2,
        )

    t0 = time.monotonic()
    result = await call_with_rotation(router, _do_call)
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
