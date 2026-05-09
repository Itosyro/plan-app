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

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.env == "development":
        # ``plain_traceback`` avoids Rich's ``show_locals=True`` which
        # hangs on complex Groq/instructor exception chains. See M-4.
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=False,
                exception_formatter=structlog.dev.plain_traceback,
            )
        )
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
