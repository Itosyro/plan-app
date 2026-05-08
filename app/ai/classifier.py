"""Classifier — categorise a single intent unit as task or note.

Uses ``llama-3.3-70b-versatile`` via Groq with ``instructor`` for
structured output.  The prompt lives in ``app/ai/prompts/classifier.md``.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult, ResolvedTime
from app.shared.logging import get_logger

logger = get_logger(__name__)

CLASSIFIER_MODEL = "llama-3.3-70b-versatile"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "classifier.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    """Read the classifier system prompt from disk (cached after first call)."""
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


def _build_user_message(
    intent_text: str,
    resolved_time: ResolvedTime | None,
    user_categories: list[str],
    user_tz: str,
) -> str:
    """Build the user message with context for the classifier."""
    now = datetime.now(ZoneInfo(user_tz))
    parts = [
        f"intent: {intent_text}",
        f"resolved_time: {resolved_time.resolved_dt.isoformat() if resolved_time and resolved_time.resolved_dt else 'null'}",
        f"existing_categories: {user_categories}",
        f"user_tz: {user_tz}",
        f"current_time: {now.isoformat()}",
    ]
    return "\n".join(parts)


async def classify_intent(
    router: GroqKeyRouter,
    intent_text: str,
    resolved_time: ResolvedTime | None,
    user_categories: list[str],
    user_tz: str,
) -> ClassifierResult:
    """Classify *intent_text* into a task or note via LLM.

    Returns a ``ClassifierResult`` with category, horizon, priority, etc.
    """
    system_prompt = _load_prompt()
    user_message = _build_user_message(
        intent_text,
        resolved_time,
        user_categories,
        user_tz,
    )

    client = instructor.from_groq(
        AsyncGroq(api_key=router.current_key),
        mode=instructor.Mode.JSON,
    )

    t0 = time.monotonic()
    result = await client.chat.completions.create(
        model=CLASSIFIER_MODEL,
        response_model=ClassifierResult,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
        max_retries=2,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "classifier.done",
        unit_text_len=len(intent_text),
        is_task=result.is_task,
        category=result.category_name,
        horizon=result.horizon,
        priority=result.priority,
        confidence=result.confidence,
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return result
