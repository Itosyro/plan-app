"""Tests for time_resolver — pure Python date parsing, no LLM."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.ai.time_resolver import resolve_time

_TZ = "Europe/Moscow"
_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))


def test_cherez_43_minuty() -> None:
    result = resolve_time("через 43 минуты позвонить", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    diff = (result.resolved_dt - _NOW).total_seconds()
    assert 42 * 60 <= diff <= 44 * 60


def test_zavtra_v_11() -> None:
    result = resolve_time("завтра в 11:00 совещание", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.day == 9
    assert result.resolved_dt.hour == 11


def test_vecherom() -> None:
    result = resolve_time("вечером пробежка", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 19


def test_cherez_polchasa() -> None:
    result = resolve_time("через полчаса встреча", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    diff = (result.resolved_dt - _NOW).total_seconds()
    assert 29 * 60 <= diff <= 31 * 60


def test_no_time_returns_none() -> None:
    result = resolve_time("купить хлеб", _TZ, now=_NOW)
    assert result is None


def test_horizon_today() -> None:
    result = resolve_time("в 15:00 звонок", _TZ, now=_NOW)
    assert result is not None
    assert result.horizon_hint == "today"


def test_is_reminder_flag() -> None:
    result = resolve_time("напомни завтра в 11:00", _TZ, now=_NOW)
    assert result is not None
    assert result.is_reminder is True


def test_no_reminder_flag() -> None:
    result = resolve_time("завтра в 11:00 совещание", _TZ, now=_NOW)
    assert result is not None
    assert result.is_reminder is False


def test_cherez_chas() -> None:
    result = resolve_time("через час позвонить маме", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    diff = (result.resolved_dt - _NOW).total_seconds()
    assert 59 * 60 <= diff <= 61 * 60


def test_cherez_nedelyu() -> None:
    result = resolve_time("через неделю сдать отчёт", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    diff = (result.resolved_dt - _NOW).total_seconds()
    assert 6.9 * 86400 <= diff <= 7.1 * 86400


# ── M-6: per-user morning_anchor / evening_anchor ────────────────────


def test_vecherom_custom_anchor() -> None:
    """User with evening_anchor=21:00 gets 21:00 instead of default 19:00."""
    result = resolve_time(
        "вечером пробежка",
        _TZ,
        now=_NOW,
        evening_anchor="21:00",
    )
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 21


def test_utrom_custom_anchor() -> None:
    """User with morning_anchor=08:00 gets 08:00 instead of default 09:00."""
    result = resolve_time(
        "утром пробежка",
        _TZ,
        now=_NOW,
        morning_anchor="08:00",
    )
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 8
