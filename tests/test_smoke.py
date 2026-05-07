"""Smoke tests for Phase 0 skeleton.

These should pass without any environment variables set. They verify that
imports work, the FastAPI app boots, and the health probe returns 200.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.shared.config import Settings


def test_app_importable() -> None:
    """The FastAPI app object exists and is named correctly."""
    assert app.title == "plan-app"


def test_healthz_ok() -> None:
    """`/healthz` is a 200 OK liveness probe."""
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_default_env() -> None:
    """Default settings load without secrets present."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env in {"development", "production", "test"}
    assert settings.critic_default_mode == "confidence"
    assert settings.groq_keys_list == []


def test_settings_groq_keys_parsing() -> None:
    """`GROQ_API_KEYS` splits on commas and trims whitespace."""
    settings = Settings(_env_file=None, groq_api_keys=" k1 , k2,k3 ")  # type: ignore[call-arg]
    assert settings.groq_keys_list == ["k1", "k2", "k3"]
