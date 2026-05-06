"""SmartKeyRouter — ConfigLoader.

Loads keyrouter.yaml, resolves {env: "VAR_NAME"} from os.environ,
validates config, and provides a typed object for the rest of the system.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    id: str
    context_limit: int
    priority: int


@dataclass
class KeyConfig:
    env: str  # e.g. "OPENROUTER_KEY_1"


@dataclass
class ProviderConfig:
    name: str
    provider_type: str
    priority: int
    enabled: bool
    keys: list[KeyConfig]
    key_strategy: str  # round_robin / random / sequential
    models: list[ModelConfig]
    base_url: str | None = None  # only for generic_openai / custom
    resolved_keys: list[str] = field(default_factory=list)  # filled by loader


@dataclass
class GlobalSettings:
    log_file: str
    log_level: str
    max_retries_per_key: int
    backoff_strategy: str
    backoff_base_seconds: int
    respect_retry_after_header: bool
    context_overflow_strategy: str


@dataclass
class SmartKeyRouterConfig:
    global_settings: GlobalSettings
    providers: list[ProviderConfig]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when config loading or validation fails."""


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------


class ConfigLoader:
    """
    Loads keyrouter.yaml, resolves env var references, validates, returns
    SmartKeyRouterConfig.

    Usage::

        loader = ConfigLoader("keyrouter.yaml")
        config = loader.load()
        print(config.providers[0].name)

        # Re-read without recreating the object:
        config = loader.reload()
    """

    _logger = logging.getLogger("SmartKeyRouter.ConfigLoader")

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).parent.parent / "keyrouter.yaml"
        self._config_path = Path(config_path)
        self._config: SmartKeyRouterConfig | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> SmartKeyRouterConfig:
        """Load (or return cached) config."""
        if self._config is None:
            self._config = self._do_load()
        return self._config

    def reload(self) -> SmartKeyRouterConfig:
        """Force re-read from disk."""
        self._config = self._do_load()
        return self._config

    @property
    def config_path(self) -> Path:
        return self._config_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_load(self) -> SmartKeyRouterConfig:
        if not self._config_path.exists():
            raise ConfigError(f"Config file not found: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh)

        if not raw or "keyrouter" not in raw:
            raise ConfigError("Invalid YAML: missing top-level 'keyrouter' key")

        kr = raw["keyrouter"]
        global_settings = self._parse_global(kr.get("global", {}))
        providers = self._parse_providers(kr.get("providers", []))
        self._validate(providers)
        return SmartKeyRouterConfig(
            global_settings=global_settings,
            providers=providers,
        )

    def _parse_global(self, raw: dict[str, Any]) -> GlobalSettings:
        return GlobalSettings(
            log_file=raw.get("log_file", "keyrouter.log"),
            log_level=raw.get("log_level", "INFO"),
            max_retries_per_key=raw.get("max_retries_per_key", 1),
            backoff_strategy=raw.get("backoff_strategy", "exponential"),
            backoff_base_seconds=raw.get("backoff_base_seconds", 1),
            respect_retry_after_header=raw.get("respect_retry_after_header", True),
            context_overflow_strategy=raw.get(
                "context_overflow_strategy", "truncate_middle"
            ),
        )

    def _parse_providers(
        self, raw_providers: list[dict[str, Any]]
    ) -> list[ProviderConfig]:
        providers: list[ProviderConfig] = []
        for raw in raw_providers:
            name = raw.get("name", "")
            keys_raw: list[dict[str, str]] = raw.get("keys", [])
            resolved: list[str] = []
            skipped_keys: list[str] = []

            for key_entry in keys_raw:
                env_var = key_entry.get("env", "")
                if not env_var:
                    continue
                value = os.environ.get(env_var)
                if value:
                    resolved.append(value)
                else:
                    skipped_keys.append(env_var)
                    self._logger.warning(
                        f"Env var '{env_var}' not set — skipping key for provider '{name}'"
                    )

            # Mark provider disabled if no keys resolved
            enabled = bool(resolved) and raw.get("enabled", True)

            if not resolved and raw.get("enabled", True):
                self._logger.warning(
                    f"Provider '{name}' has no valid keys — marking as disabled"
                )
                enabled = False

            models = [
                ModelConfig(
                    id=m.get("id", ""),
                    context_limit=m.get("context_limit", 0),
                    priority=m.get("priority", 99),
                )
                for m in raw.get("models", [])
            ]

            provider = ProviderConfig(
                name=name,
                provider_type=raw.get("provider_type", "generic_openai"),
                priority=raw.get("priority", 99),
                enabled=enabled,
                keys=[KeyConfig(env=k.get("env", "")) for k in keys_raw],
                key_strategy=raw.get("key_strategy", "round_robin"),
                models=models,
                base_url=raw.get("base_url"),
                resolved_keys=resolved,
            )
            providers.append(provider)

        return providers

    def _validate(self, providers: list[ProviderConfig]) -> None:
        # Unique names
        names = [p.name for p in providers]
        if len(names) != len(set(names)):
            raise ConfigError("Duplicate provider names found in config")

        # Unique priorities
        priorities = [p.priority for p in providers]
        if len(priorities) != len(set(priorities)):
            raise ConfigError("Duplicate priority values found in config")

        # context_limit > 0
        for p in providers:
            for m in p.models:
                if m.context_limit <= 0:
                    raise ConfigError(
                        f"Provider '{p.name}', model '{m.id}': "
                        f"context_limit must be > 0, got {m.context_limit}"
                    )

        # key_strategy valid
        valid_strategies = {"round_robin", "random", "sequential"}
        for p in providers:
            if p.key_strategy not in valid_strategies:
                raise ConfigError(
                    f"Provider '{p.name}': unknown key_strategy "
                    f"'{p.key_strategy}' — use one of {valid_strategies}"
                )

        # global context_overflow_strategy valid
        # (will be checked against GlobalSettings — skip here)

    # ------------------------------------------------------------------
    # CLI helpers (used by cli.py)
    # ------------------------------------------------------------------

    @staticmethod
    def mask_key(key: str) -> str:
        """Show only first 8 chars + '...'"""
        if not key:
            return "..."
        if len(key) <= 8:
            return key
        return key[:8] + "..."

    @staticmethod
    def create_example_env(path: Path | str | None = None) -> None:
        """Write .env.example to disk."""
        content = """\
# SmartKeyRouter — Environment Variables Template
# Copy this file to .env and fill in your actual API keys.
# NEVER commit .env to version control.

# --- OpenRouter Keys ---
# Get keys from https://openrouter.ai/keys
OPENROUTER_KEY_1=
OPENROUTER_KEY_2=
OPENROUTER_KEY_3=

# --- Qwen (Alibaba Cloud DashScope) Keys ---
# Get keys from https://dashscope.console.aliyun.com/apiKey
QWEN_API_KEY_1=
QWEN_API_KEY_2=

# --- Allama Cloud Keys ---
# Get keys from https://allama.cloud
ALLAMA_CLOUD_KEY_1=
"""
        out_path = Path(path) if path else Path(__file__).parent.parent / ".env.example"
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
