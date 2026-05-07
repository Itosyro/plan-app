"""Application configuration.

Reads from environment variables (and `.env` for local dev) via Pydantic
Settings. Phase 0 ships a minimal skeleton — real fields land alongside the
features that need them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # Phase 1 will populate these.
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    webhook_base_url: str | None = None
    database_url: str | None = None

    # Phase 2 will populate these.
    groq_api_keys: str | None = Field(
        default=None,
        description="Comma-separated list of Groq API keys.",
    )
    critic_default_mode: Literal["confidence", "paranoid"] = "confidence"

    @property
    def groq_keys_list(self) -> list[str]:
        """Parse `GROQ_API_KEYS` into a clean list of keys."""
        if not self.groq_api_keys:
            return []
        return [key.strip() for key in self.groq_api_keys.split(",") if key.strip()]


def get_settings() -> Settings:
    """Return a settings instance.

    Currently re-creates each time. Phase 1 will switch this to `lru_cache`
    once we know the wiring is right.
    """
    return Settings()
