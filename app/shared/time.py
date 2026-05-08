"""Project-wide datetime helpers.

The DB schema stores timestamps in tz-naive ``DateTime`` columns and we
treat all of those as **UTC**. This module gives the rest of the codebase
a single, easy-to-grep way to spell "now in UTC, naive": the alternatives
either tug in tz info that gets silently stripped on insert
(``datetime.now(UTC)`` then a write to a naive column) or use the
deprecated naive-UTC ``datetime.utcnow``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """Return the current time in UTC as a tz-naive ``datetime``.

    Equivalent to ``datetime.now(UTC).replace(tzinfo=None)`` — avoids the
    deprecated ``datetime.utcnow()`` while still matching the tz-naive
    columns we use throughout the schema.
    """
    return datetime.now(UTC).replace(tzinfo=None)
