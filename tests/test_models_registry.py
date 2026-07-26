"""Regression tests for the central model registry (``app.ai.models``).

These lock in the production defaults so a model swap is always a
deliberate, reviewed change. History: the May 2026 ``openai/gpt-oss-*``
switch broke prod because instructor ran in ``Mode.JSON`` and reasoning
tokens polluted ``message.content``; since then every call site uses
``Mode.TOOLS`` (parses ``tool_calls``), which gpt-oss supports on Groq.
The old Llama defaults were deprecated by Groq (shutdown August 2026)
and must not come back. If you intentionally change a default, update
the assertions AND verify the new model works with instructor
``Mode.TOOLS`` first.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.ai.models import get_models
from app.shared.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_caches() -> Generator[None, None, None]:
    """Both ``get_settings`` and ``get_models`` are ``lru_cache``d."""
    get_settings.cache_clear()
    get_models.cache_clear()
    yield
    get_settings.cache_clear()
    get_models.cache_clear()


def test_defaults_are_gpt_oss_models() -> None:
    """The shipped defaults are the gpt-oss line (tool-use capable on
    Groq, parsed via instructor ``Mode.TOOLS``)."""
    models = get_models()
    # Тяжёлые стадии: 120b — одна ошибка классификации каскадится.
    assert models.classifier == "openai/gpt-oss-120b"
    assert models.critic == "openai/gpt-oss-120b"
    # Лёгкие стадии: 20b — быстрый tight-loop.
    assert models.splitter == "openai/gpt-oss-20b"
    assert models.intent == "openai/gpt-oss-20b"
    assert models.reorder == "openai/gpt-oss-20b"
    assert models.courier == "openai/gpt-oss-20b"
    assert models.task_splitter == "openai/gpt-oss-20b"
    # STT без изменений.
    assert models.whisper == "whisper-large-v3"


def test_no_deprecated_models_in_defaults() -> None:
    """Guard rail: models Groq has withdrawn or deprecated (shutdown
    August 2026) may not reappear as defaults — they will 404 in prod."""
    models = get_models()
    blob = " ".join(
        [
            models.whisper,
            models.splitter,
            models.intent,
            models.reorder,
            models.courier,
            models.task_splitter,
            models.classifier,
            models.critic,
        ]
    )
    assert "llama-3.1-8b-instant" not in blob
    assert "llama-3.3-70b-versatile" not in blob
    assert "qwen-qwq" not in blob


def test_env_override_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``GROQ_MODEL_<STAGE>`` env var must override the default so
    models can be A/B'd in prod without a redeploy."""
    monkeypatch.setenv("GROQ_MODEL_CLASSIFIER", "moonshotai/kimi-k2-instruct")
    get_settings.cache_clear()
    get_models.cache_clear()
    # Re-read settings from the patched environment.
    s = Settings()
    assert s.groq_model_classifier == "moonshotai/kimi-k2-instruct"
