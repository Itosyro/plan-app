"""Tests for ``app.shared.time`` helpers (format_due_local, to_naive_utc).

C-2 regression coverage. The schema stores ``Task.due_at`` as a tz-naive
``DateTime`` column with the convention "naive == UTC". These helpers
are the only correct way to (a) coerce a tz-aware value into that
contract before INSERT, and (b) render the stored value back to a
human-readable HH:MM in the user's local timezone.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.shared.time import format_due_local, to_naive_utc, utcnow_naive

# ── to_naive_utc ─────────────────────────────────────────────────────


def test_to_naive_utc_strips_tzinfo_from_aware_msk() -> None:
    """Aware MSK 12:00 → naive UTC 09:00."""
    msk = ZoneInfo("Europe/Moscow")
    aware = datetime(2026, 5, 9, 12, 0, tzinfo=msk)
    result = to_naive_utc(aware)
    assert result == datetime(2026, 5, 9, 9, 0)
    assert result.tzinfo is None


def test_to_naive_utc_passes_naive_through() -> None:
    """A naive datetime is returned as-is (assumed already UTC)."""
    naive = datetime(2026, 5, 9, 9, 0)
    assert to_naive_utc(naive) == naive
    assert to_naive_utc(naive).tzinfo is None


def test_to_naive_utc_handles_aware_utc() -> None:
    """An aware-UTC datetime drops tzinfo without changing wall-clock."""
    from datetime import UTC

    aware_utc = datetime(2026, 5, 9, 9, 0, tzinfo=UTC)
    result = to_naive_utc(aware_utc)
    assert result == datetime(2026, 5, 9, 9, 0)
    assert result.tzinfo is None


# ── format_due_local ─────────────────────────────────────────────────


def test_format_due_local_converts_utc_to_user_tz() -> None:
    """C-2: 12:00 UTC for an MSK user shows as 15:00."""
    naive_utc = datetime(2026, 5, 9, 12, 0)
    assert format_due_local(naive_utc, "Europe/Moscow") == "15:00"


def test_format_due_local_utc_user_returns_utc_clock() -> None:
    """A UTC user sees UTC clock-time unchanged."""
    naive_utc = datetime(2026, 5, 9, 12, 0)
    assert format_due_local(naive_utc, "UTC") == "12:00"


def test_format_due_local_returns_none_for_local_midnight() -> None:
    """Midnight in the user's tz is treated as the date-only sentinel.

    21:00 UTC = 00:00 MSK → return None so the caller can omit "— в HH:MM".
    """
    naive_utc = datetime(2026, 5, 8, 21, 0)
    assert format_due_local(naive_utc, "Europe/Moscow") is None


def test_format_due_local_unknown_tz_falls_back_to_utc() -> None:
    """A bogus tz string must not crash; we silently fall back to UTC."""
    naive_utc = datetime(2026, 5, 9, 12, 0)
    assert format_due_local(naive_utc, "Mars/Olympus_Mons") == "12:00"


def test_format_due_local_empty_tz_falls_back_to_utc() -> None:
    """Empty-string tz is also handled gracefully."""
    naive_utc = datetime(2026, 5, 9, 12, 0)
    assert format_due_local(naive_utc, "") == "12:00"


def test_format_due_local_aware_input_works_too() -> None:
    """An aware-UTC ``due_at`` is handled symmetrically with naive."""
    from datetime import UTC

    aware_utc = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    assert format_due_local(aware_utc, "Europe/Moscow") == "15:00"


# ── utcnow_naive (smoke) ─────────────────────────────────────────────


def test_utcnow_naive_returns_naive() -> None:
    now = utcnow_naive()
    assert now.tzinfo is None
