"""Tests for reminder_extractor — pure Python, no LLM."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.ai.reminder_extractor import extract_reminder

_TZ = "Europe/Moscow"
_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))


def test_napomni_cherez_chas() -> None:
    result = extract_reminder("напомни через час купить молоко", _TZ, now=_NOW)
    assert result is not None
    diff = (result.fire_at - _NOW).total_seconds()
    assert 59 * 60 <= diff <= 61 * 60


def test_no_napomni_returns_none() -> None:
    result = extract_reminder("записаться к врачу", _TZ, now=_NOW)
    assert result is None


def test_napomni_zavtra() -> None:
    result = extract_reminder("напомнить завтра в 9:00 позвонить", _TZ, now=_NOW)
    assert result is not None
    assert result.fire_at.day == 9
    assert result.fire_at.hour == 9


def test_napomni_cherez_polchasa() -> None:
    result = extract_reminder("напомни через полчаса", _TZ, now=_NOW)
    assert result is not None
    diff = (result.fire_at - _NOW).total_seconds()
    assert 29 * 60 <= diff <= 31 * 60
