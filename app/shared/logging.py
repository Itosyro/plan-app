"""Structured logging via structlog.

PII rule: never log raw user text (`message.text`, voice transcripts, voice
file bytes). Log only identifiers (`user_id`, `update_id`,
`telegram_message_id`) and metadata (lengths, types, latencies).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.shared.config import get_settings

_configured = False

# Allow-list of stdlib log levels — see ``defensive-programming/SKILL.md``
# for the "no ``getattr``" rule. ``logging`` levels are stable and tiny,
# so an explicit mapping is no more code than ``getattr`` would be and
# matches the rest of the codebase.
_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging() -> None:
    """Configure structlog + stdlib logging once at startup.

    Idempotent — safe to call multiple times (only the first call has effect).
    """
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = _LOG_LEVELS.get(settings.log_level.upper(), logging.INFO)

    # NB: ``structlog.processors.format_exc_info`` is intentionally kept in
    # the chain even though structlog 25 emits a ``UserWarning`` recommending
    # it be removed when ``ConsoleRenderer`` / ``JSONRenderer`` are used. In
    # this codebase, removing it causes ``tests/test_e2e_pipeline.py::
    # test_e2e_partial_classify_failure_does_not_kill_batch`` to hang under
    # certain Groq-retry / chained-exception paths. See
    # ``REVIEW-2026-05-09.md::M-4`` (deferred to future work).
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.env == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")
    _configured = True


def get_logger(name: str | None = None, **initial: Any) -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound to the given name and initial context."""
    return structlog.get_logger(name).bind(**initial) if initial else structlog.get_logger(name)
