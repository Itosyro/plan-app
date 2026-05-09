"""Critic — review and optionally correct classifier output.

Uses ``qwen-qwq-32b`` (reasoning model) via Groq with ``instructor``
for structured output.  Runs conditionally based on user settings:
- ``confidence`` mode: only when classifier confidence < threshold
- ``always`` mode: every classification gets reviewed
"""

from __future__ import annotations

import time
from pathlib import Path

import instructor
from groq import AsyncGroq

from app.ai.router import GroqKeyRouter, call_with_rotation
from app.ai.schemas import ClassifierResult, CriticVerdict, ResolvedTime
from app.shared.logging import get_logger

logger = get_logger(__name__)

CRITIC_MODEL = "qwen-qwq-32b"

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "critic.md"
_prompt_cache: str | None = None


def _load_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


def _build_user_message(
    intent_text: str,
    classifier_result: ClassifierResult,
    resolved_time: ResolvedTime | None,
    user_tz: str,
) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(user_tz))
    resolved_dt = (
        resolved_time.resolved_dt.isoformat()
        if resolved_time and resolved_time.resolved_dt
        else "null"
    )
    return "\n".join(
        [
            f"intent: {intent_text}",
            f"classifier_result: {classifier_result.model_dump_json()}",
            f"resolved_time: {resolved_dt}",
            f"user_tz: {user_tz}",
            f"current_time: {now.isoformat()}",
        ]
    )


def should_run_critic(
    classifier_result: ClassifierResult,
    *,
    critic_mode: str,
    confidence_threshold: float,
) -> bool:
    """Decide whether the critic should run for this classification."""
    if critic_mode == "always":
        return True
    if critic_mode == "confidence":
        return classifier_result.confidence < confidence_threshold
    return False


async def critique_classification(
    router: GroqKeyRouter,
    intent_text: str,
    classifier_result: ClassifierResult,
    resolved_time: ResolvedTime | None,
    user_tz: str,
) -> CriticVerdict:
    """Run the Critic on a classifier result.

    Returns a ``CriticVerdict`` with approval status and optional correction.
    """
    system_prompt = _load_prompt()
    user_message = _build_user_message(
        intent_text,
        classifier_result,
        resolved_time,
        user_tz,
    )

    async def _do_call(r: GroqKeyRouter) -> CriticVerdict:
        client = instructor.from_groq(
            AsyncGroq(api_key=r.current_key),
            mode=instructor.Mode.JSON,
        )
        return await client.chat.completions.create(
            model=CRITIC_MODEL,
            response_model=CriticVerdict,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_retries=2,
        )

    t0 = time.monotonic()
    verdict = await call_with_rotation(router, _do_call)
    latency_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "critic.done",
        approved=verdict.approved,
        reason_len=len(verdict.reason),
        latency_ms=latency_ms,
        key_id=router.current_key_id,
    )
    return verdict


def apply_verdict(
    classifier_result: ClassifierResult,
    verdict: CriticVerdict,
) -> ClassifierResult:
    """Return the final ClassifierResult after applying the critic verdict."""
    if verdict.approved or verdict.corrected is None:
        return classifier_result
    return verdict.corrected
