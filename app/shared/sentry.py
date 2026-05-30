"""Optional Sentry crash reporter.

The SDK is dormant unless ``SENTRY_DSN`` is set in the environment —
``init_sentry`` is a no-op for tests and local dev. With a DSN it
hooks into FastAPI and asyncio's default exception handler, which is
what catches the background pipeline tasks (text/voice routers fire
``asyncio.create_task(_background())``; unhandled exceptions inside
those tasks currently surface only via ``logger.exception`` and the
``log_task_exception`` done-callback — useful for grep, useless for
on-call).

Why an explicit helper instead of inlining ``sentry_sdk.init`` in
``create_app``: keeping it here lets bot-only entry points (workers,
one-off scripts) opt in with one call and lets tests stub out the
SDK by monkeypatching this module.
"""

from __future__ import annotations

from app.shared.config import Settings
from app.shared.logging import get_logger

logger = get_logger(__name__)

_initialised = False


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry from ``Settings``. Returns True if it actually ran.

    Idempotent — repeated calls are no-ops so a re-imported ``create_app``
    in tests doesn't double-init. Returns False when ``sentry_dsn`` is
    unset (the dominant case in local dev / CI / tests).
    """
    global _initialised
    if _initialised:
        return True
    if not settings.sentry_dsn:
        return False

    # Import lazily so the dependency is allowed to be slow / heavy
    # without paying for it on every cold start.
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # The ``AsyncioIntegration`` is the missing link for our
        # background pipeline tasks — without it, exceptions raised
        # inside ``asyncio.create_task(_background())`` would never
        # reach Sentry because nobody awaits the task.
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            AsyncioIntegration(),
        ],
        # Trim sensitive payloads before they leave the box. Telegram
        # user messages (text + transcripts) can contain personal info;
        # request bodies for ``POST /tg/{secret}`` carry the bot's
        # webhook secret. Strip both.
        send_default_pii=False,
        max_request_body_size="never",
    )
    _initialised = True
    logger.info(
        "sentry.initialised",
        environment=settings.sentry_environment or settings.env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    return True


def reset_for_tests() -> None:
    """Drop the init guard so the next ``init_sentry`` runs again."""
    global _initialised
    _initialised = False
