"""Split an existing task into 2–5 atomic subtasks via LLM (PR-Split).

Used by the «Входящие» review card in the Mini-App: a user can ask the
backend to take a single high-level task and propose a list of atomic
subtasks to break it down. Mirrors :mod:`app.ai.intent` in structure
(instructor tools mode, key rotation, wrap_untrusted, logging).
"""

from __future__ import annotations

import time
from pathlib import Path

import instructor
from pydantic import BaseModel, Field

from app.ai._safety import wrap_untrusted
from app.ai.models import get_models
from app.ai.router import GroqKeyRouter, call_with_rotation
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Hard cap on suggested subtasks — mirrors ``_persist_subtasks`` in
# ``app.bot.services.tasks``. The prompt and schema both enforce this,
# but defensive truncation here keeps the contract one-sided.
_MAX_SUBTASKS = 5

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "task_splitter.md"
_prompt_cache: str | None = None


class TaskSplitResult(BaseModel):
    """Structured response: 2–5 atomic subtask titles in execution order."""

    subtasks: list[str] = Field(
        default_factory=list,
        max_length=_MAX_SUBTASKS,
        description="2–5 atomic subtask titles in execution order",
    )


def _load_prompt() -> str:
    """Read the task-splitter system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


async def split_task_to_subtasks(
    router: GroqKeyRouter,
    title: str,
) -> list[str]:
    """Ask the LLM to break *title* into 2–5 atomic subtasks.

    Returns a list of cleaned, deduplicated, non-empty titles in
    execution order. Empty list when the task is already atomic or the
    LLM refused. Capped at :data:`_MAX_SUBTASKS` defensively even though
    both the prompt and the Pydantic schema enforce the same bound.
    """
    stripped = title.strip()
    if not stripped:
        return []

    system_prompt = _load_prompt()

    async def _do_call(r: GroqKeyRouter) -> TaskSplitResult:
        client = instructor.from_groq(
            r.async_client(),
            mode=instructor.Mode.TOOLS,
        )
        return await client.chat.completions.create(
            model=get_models().task_splitter,
            response_model=TaskSplitResult,
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

    # Defensive cleanup: strip blanks, trim, dedupe (case-insensitive),
    # and cap. The schema already caps at 5 but a sloppy model output
    # could still return whitespace-only or duplicate strings.
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in result.subtasks:
        candidate = raw.strip()
        if not candidate:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
        if len(cleaned) >= _MAX_SUBTASKS:
            break

    logger.info(
        "task_splitter.done",
        subtasks_count=len(cleaned),
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return cleaned
