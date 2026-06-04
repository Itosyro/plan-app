"""Central registry of LLM / STT model IDs used across the AI pipeline.

Historically each AI module hard-coded its model identifier as a
module-level constant (``CLASSIFIER_MODEL = "..."``). That meant a
model swap touched eight files and there was no way to override per
deployment. It also let drift happen silently — the critic was wired
to ``qwen-qwq-32b`` long after Groq removed that model from service.

This module is the single source of truth. Each stage reads its model
from ``get_models()`` which builds a frozen ``ModelRegistry`` from
``Settings``. Defaults match the May 2026 Groq production catalog
(see ``console.groq.com/docs/models``); every default is overridable
via a ``GROQ_MODEL_<STAGE>`` environment variable so production can
roll a new model without a code change. When OpenRouter keys land,
the same env hooks point individual stages at OpenRouter IDs.

The picks below trade pure speed for accuracy on long, multi-unit
Russian messages — the user's pain point. ``openai/gpt-oss-20b``
runs at ~1000 tok/s on Groq LPUs (fast enough for tight loop stages
like splitter/intent/courier) while still reasoning. The heavier
``openai/gpt-oss-120b`` handles classifier and critic where one
wrong call cascades.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.shared.config import get_settings


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    """Frozen snapshot of model IDs for every AI stage.

    Frozen + ``slots`` so callers can't mutate it at runtime; pass the
    registry around rather than reaching into globals when a stage
    needs to know which model it ran on (e.g. for the ``log_ai_run``
    audit trail).
    """

    whisper: str
    splitter: str
    intent: str
    reorder: str
    courier: str
    task_splitter: str
    classifier: str
    critic: str


# Defaults — battle-tested Groq production models that play cleanly
# with ``instructor`` JSON/structured-output mode.
#
# History: WS1 briefly switched the heavy stages to ``openai/gpt-oss-*``
# (reasoning models). In production those broke EVERY classify call —
# gpt-oss models emit ``<reasoning>`` tokens around their output and
# don't honour instructor's JSON mode cleanly, so the Pydantic parse
# failed on every voice/text message and the bot replied with a
# generic error. Reverted to the proven Llama line:
#   • ``llama-3.3-70b-versatile`` — 128K ctx, native JSON mode + tool
#     use, current Groq production (NOT deprecated as of 2026-06).
#   • ``llama-3.1-8b-instant`` — fast light-stage model, current
#     production (the sanctioned replacement for llama3-8b-8192).
# ``qwen-qwq-32b`` (the old critic) stays gone — Groq withdrew it.
# The critic now shares the 70B model.
#
# Every default is still env-overridable (``GROQ_MODEL_<STAGE>``), so
# gpt-oss / kimi / a future OpenRouter id can be A/B'd in one place
# WITHOUT a redeploy once verified to work with structured output.
_WHISPER_DEFAULT = "whisper-large-v3"
_LIGHT_DEFAULT = "llama-3.1-8b-instant"
_HEAVY_DEFAULT = "llama-3.3-70b-versatile"


@lru_cache(maxsize=1)
def get_models() -> ModelRegistry:
    """Build the registry from settings, caching the result for the process.

    ``lru_cache`` ties the lifetime to ``get_settings()`` (also cached) —
    in tests that mutate settings, call ``get_models.cache_clear()``.
    """
    s = get_settings()
    return ModelRegistry(
        whisper=s.groq_model_whisper or _WHISPER_DEFAULT,
        splitter=s.groq_model_splitter or _LIGHT_DEFAULT,
        intent=s.groq_model_intent or _LIGHT_DEFAULT,
        reorder=s.groq_model_reorder or _LIGHT_DEFAULT,
        courier=s.groq_model_courier or _LIGHT_DEFAULT,
        task_splitter=s.groq_model_task_splitter or _LIGHT_DEFAULT,
        classifier=s.groq_model_classifier or _HEAVY_DEFAULT,
        critic=s.groq_model_critic or _HEAVY_DEFAULT,
    )
