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

The live defaults are ``openai/gpt-oss-20b`` for the tight loop stages
(splitter/intent/reorder/courier/task_splitter) and
``openai/gpt-oss-120b`` for the heavy stages (classifier/critic) where
one wrong call cascades. Groq deprecated the previous Llama defaults
(shutdown August 2026) — see the History note above the defaults below
before swapping models again.
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


# History — прочитай перед любой сменой моделей:
#
# • Май 2026 (откат в PR #171): первая попытка перейти на
#   ``openai/gpt-oss-*`` сломала ВСЕ вызовы. Причина была не в самих
#   моделях, а в связке с ``instructor.Mode.JSON``: gpt-oss — reasoning-
#   модели и эмитят reasoning-токены вокруг ответа в ``message.content``,
#   поэтому Pydantic-парс контента падал на каждом сообщении.
#   Откатились тогда на Llama.
#
# • 17 июня 2026: Groq объявил deprecation ``llama-3.1-8b-instant`` и
#   ``llama-3.3-70b-versatile`` с отключением к августу 2026. Откат на
#   llama-модели после августа НЕВОЗМОЖЕН — этой опции больше нет.
#
# • Сейчас: снова gpt-oss, но все instructor-колсайты переведены на
#   ``instructor.Mode.TOOLS`` — схема передаётся как tool, ответ
#   парсится из ``tool_calls[0].function.arguments`` (gpt-oss
#   поддерживает tool use на Groq), reasoning-токены в ``content``
#   парсингу больше не мешают. Это и есть отличие от майской попытки.
#
# Env-override ``GROQ_MODEL_<STAGE>`` остаётся аварийным рычагом: любую
# стадию можно перевести на другой model id без редеплоя (но только на
# модель, которая умеет tool use).
_WHISPER_DEFAULT = "whisper-large-v3"
_LIGHT_DEFAULT = "openai/gpt-oss-20b"
_HEAVY_DEFAULT = "openai/gpt-oss-120b"


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
