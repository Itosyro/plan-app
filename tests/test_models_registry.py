"""Regression tests for the central model registry (``app.ai.models``).

These lock in the production-safe defaults so a future "let's try the
shiny new model" change can't silently re-break prod the way the
``openai/gpt-oss-*`` switch did (reasoning models broke instructor's
JSON parsing → every classify call failed → bot errored on every
message). If you intentionally change a default, update the assertion
AND verify the new model works with ``instructor`` JSON mode first.
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


def test_defaults_are_production_llama_models() -> None:
    """The shipped defaults must be the battle-tested Llama line that
    works with instructor JSON mode — NOT reasoning models."""
    get_settings.cache_clear()
    get_models.cache_clear()
    models = get_models()
    # Heavy stages: 70B versatile (native JSON mode + tool use).
    assert models.classifier == "llama-3.3-70b-versatile"
    assert models.critic == "llama-3.3-70b-versatile"
    # Light stages: 8b-instant (fast, production).
    assert models.splitter == "llama-3.1-8b-instant"
    assert models.intent == "llama-3.1-8b-instant"
    assert models.reorder == "llama-3.1-8b-instant"
    assert models.courier == "llama-3.1-8b-instant"
    assert models.task_splitter == "llama-3.1-8b-instant"
    # STT unchanged.
    assert models.whisper == "whisper-large-v3"


def test_no_reasoning_models_in_defaults() -> None:
    """Guard rail: no ``gpt-oss`` / ``qwen-qwq`` reasoning model may be a
    default. They emit reasoning tokens that break structured output."""
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
    assert "gpt-oss" not in blob
    assert "qwen-qwq" not in blob


def test_env_override_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``GROQ_MODEL_<STAGE>`` env var must override the default so
    models can be A/B'd in prod without a redeploy."""
    monkeypatch.setenv("GROQ_MODEL_CLASSIFIER", "openai/gpt-oss-120b")
    get_settings.cache_clear()
    get_models.cache_clear()
    # Re-read settings from the patched environment.
    s = Settings()
    assert s.groq_model_classifier == "openai/gpt-oss-120b"
