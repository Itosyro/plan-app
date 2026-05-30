"""Tests for the optional Sentry crash-reporter wiring.

The SDK is dormant unless ``SENTRY_DSN`` is set. These tests pin the
contract from both directions so a future refactor can't accidentally
(a) ship Sentry traffic from CI / local dev, or
(b) silently break the prod-only init path.
"""

from __future__ import annotations

from unittest.mock import patch

from app.shared.config import Settings
from app.shared.sentry import init_sentry, reset_for_tests


def test_init_sentry_noop_without_dsn() -> None:
    """No DSN → no SDK call. Local dev / CI never reach out to Sentry."""
    reset_for_tests()
    settings = Settings(sentry_dsn=None)
    with patch("sentry_sdk.init") as sentry_init:
        result = init_sentry(settings)
    assert result is False
    sentry_init.assert_not_called()


def test_init_sentry_runs_with_dsn() -> None:
    """DSN set → ``sentry_sdk.init`` is invoked exactly once."""
    reset_for_tests()
    settings = Settings(
        sentry_dsn="https://public@sentry.example.invalid/1",
        sentry_environment="staging",
        sentry_traces_sample_rate=0.1,
    )
    with patch("sentry_sdk.init") as sentry_init:
        result = init_sentry(settings)
    assert result is True
    sentry_init.assert_called_once()
    kwargs = sentry_init.call_args.kwargs
    assert kwargs["dsn"] == "https://public@sentry.example.invalid/1"
    assert kwargs["environment"] == "staging"
    assert kwargs["traces_sample_rate"] == 0.1
    # Don't ship PII or request bodies by default.
    assert kwargs["send_default_pii"] is False
    assert kwargs["max_request_body_size"] == "never"
    reset_for_tests()


def test_init_sentry_is_idempotent() -> None:
    """Repeated calls don't double-init the SDK (which would re-attach
    every integration twice and double-fire on the next exception)."""
    reset_for_tests()
    settings = Settings(sentry_dsn="https://public@sentry.example.invalid/1")
    with patch("sentry_sdk.init") as sentry_init:
        init_sentry(settings)
        init_sentry(settings)
    assert sentry_init.call_count == 1
    reset_for_tests()


def test_init_sentry_defaults_environment_to_settings_env() -> None:
    reset_for_tests()
    settings = Settings(
        sentry_dsn="https://public@sentry.example.invalid/1",
        env="production",
        # sentry_environment left at default (None) so it should fall
        # back to ``settings.env``.
    )
    with patch("sentry_sdk.init") as sentry_init:
        init_sentry(settings)
    assert sentry_init.call_args.kwargs["environment"] == "production"
    reset_for_tests()
