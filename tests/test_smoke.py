"""Smoke tests for the Phase 0 skeleton.

These should pass without any environment variables set. They verify that
imports work, the FastAPI app boots, and the health probe returns 200.

The settings tests scrub the relevant env vars first, so the suite is stable
on dev machines that already have secrets exported.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.config import Settings

_SETTINGS_ENV_VARS = (
    "ENV",
    "LOG_LEVEL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "WEBHOOK_BASE_URL",
    "DATABASE_URL",
    "GROQ_API_KEYS",
    "CRITIC_DEFAULT_MODE",
)


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every Settings-relevant env var so defaults stay default."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_app_importable() -> None:
    """The FastAPI app object exists and is named correctly."""
    assert app.title == "plan-app"


def test_healthz_ok() -> None:
    """`/healthz` is a 200 OK liveness probe."""
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_default_env(_clean_env: None) -> None:
    """Default settings load without secrets present."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env in {"development", "production", "test"}
    assert settings.critic_default_mode == "confidence"
    assert settings.groq_keys_list == []


def test_settings_groq_keys_parsing(_clean_env: None) -> None:
    """`GROQ_API_KEYS` splits on commas and trims whitespace."""
    settings = Settings(_env_file=None, groq_api_keys=" k1 , k2,k3 ")  # type: ignore[call-arg]
    assert settings.groq_keys_list == ["k1", "k2", "k3"]
