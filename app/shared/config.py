"""Application configuration.

Reads from environment variables (and `.env` for local dev) via Pydantic
Settings. Phase 1 wires up Telegram + database fields. Groq fields land in
Phase 2.
"""

from __future__ import annotations

from functools import lru_cache
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

    # Phase 1 — Telegram + DB
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    webhook_base_url: str | None = None
    database_url: str | None = None

    # Phase 2 — Groq
    groq_api_keys: str | None = Field(
        default=None,
        description="Comma-separated list of Groq API keys.",
    )
    critic_default_mode: Literal["confidence", "paranoid"] = "confidence"

    # Phase 4 — in-process scheduler (used on Render free tier instead of a
    # standalone cron service).
    scheduler_inproc_enabled: bool = True
    scheduler_tick_interval_seconds: float = 60.0

    # Phase 5 — Mini-App URL override. By default we derive it from
    # ``webhook_base_url`` (same host, ``/app/`` path). Set explicitly
    # when the Mini-App is hosted on a separate domain (e.g. Cloudflare
    # Pages) — Telegram requires HTTPS for ``MenuButtonWebApp``.
    miniapp_url_override: str | None = None

    @property
    def groq_keys_list(self) -> list[str]:
        """Parse `GROQ_API_KEYS` into a clean list of keys."""
        if not self.groq_api_keys:
            return []
        return [key.strip() for key in self.groq_api_keys.split(",") if key.strip()]

    @property
    def webhook_url(self) -> str | None:
        """Full public webhook URL (`{base}/tg/{secret}`) or None if unset."""
        if not self.webhook_base_url or not self.telegram_webhook_secret:
            return None
        return f"{self.webhook_base_url.rstrip('/')}/tg/{self.telegram_webhook_secret}"

    @property
    def miniapp_url(self) -> str | None:
        """Public URL of the Mini-App (used by ``setChatMenuButton``).

        Returns ``miniapp_url_override`` if set, otherwise
        ``{webhook_base_url}/app/`` if the base URL is available.
        ``None`` when neither is configured (no menu button is set).
        """
        if self.miniapp_url_override:
            return self.miniapp_url_override.rstrip("/") + "/"
        if self.webhook_base_url:
            return self.webhook_base_url.rstrip("/") + "/app/"
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
