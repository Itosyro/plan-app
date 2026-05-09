"""Project-wide datetime helpers.

The DB schema stores timestamps in tz-naive ``DateTime`` columns and we
treat all of those as **UTC**. This module gives the rest of the codebase
a single, easy-to-grep way to spell "now in UTC, naive": the alternatives
either tug in tz info that gets silently stripped on insert
(``datetime.now(UTC)`` then a write to a naive column) or use the
deprecated naive-UTC ``datetime.utcnow``.

For display, :func:`format_due_local` converts a stored naive-UTC
datetime back to the user's local timezone before formatting it as
``HH:MM`` — use it everywhere we render ``Task.due_at`` to a Telegram
message. See ``docs/REVIEW-2026-05-09.md::C-2``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utcnow_naive() -> datetime:
    """Return the current time in UTC as a tz-naive ``datetime``.

    Equivalent to ``datetime.now(UTC).replace(tzinfo=None)`` — avoids the
    deprecated ``datetime.utcnow()`` while still matching the tz-naive
    columns we use throughout the schema.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Return *dt* as a naive UTC datetime (drop tz, converting if needed).

    * tz-naive input — returned unchanged (assumed already UTC).
    * tz-aware input — converted to UTC, then ``replace(tzinfo=None)``.

    This is the only correct way to coerce a value that came from
    ``dateparser`` (tz-aware in the user's tz) before persisting it into
    a tz-naive column.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def format_due_local(due_at: datetime, user_tz: str) -> str | None:
    """Return the ``HH:MM`` rendering of *due_at* in *user_tz*.

    *due_at* is interpreted as **naive UTC** (the schema contract).
    *user_tz* is an IANA name (``"Europe/Moscow"``); unknown values
    fall back to UTC.

    Returns ``None`` if the time component is exactly midnight, since
    we use that as a sentinel for "date-only deadline". Callers can
    decide whether to render "— в HH:MM" or omit the suffix.
    """
    aware_utc = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at
    zi: ZoneInfo | timezone
    try:
        zi = ZoneInfo(user_tz or "UTC")
    except ZoneInfoNotFoundError:
        zi = UTC
    local = aware_utc.astimezone(zi)
    if local.hour == 0 and local.minute == 0:
        return None
    return f"{local:%H:%M}"
