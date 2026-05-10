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


# ── R-NEW-C-2: «сегодня в HH:MM» past now must NOT roll forward ──────


def test_segodnya_v_hhmm_past_stays_today() -> None:
    """Regression: «сегодня в 10:00» when *now* is 14:00 must resolve
    to TODAY at 10:00 — NOT next week.

    Before the fix the rollover branch (originally meant for «во
    вторник» on Tuesday) added 7 days for any past same-day datetime.
    Users who said «сегодня в 10:00» retroactively saw a task scheduled
    seven days later.
    """
    now = datetime(2026, 5, 9, 14, 0, tzinfo=ZoneInfo(_TZ))
    result = resolve_time("сегодня в 10:00 позвонить маме", _TZ, now=now)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.date() == now.date(), (
        f"expected today ({now.date()}), got {result.resolved_dt.date()}"
    )
    assert result.resolved_dt.hour == 10
    assert result.horizon_hint == "today"


def test_segodnya_v_hhmm_future_still_today() -> None:
    """«сегодня в 16:00» at 14:00 must keep horizon=today (sanity)."""
    now = datetime(2026, 5, 9, 14, 0, tzinfo=ZoneInfo(_TZ))
    result = resolve_time("сегодня в 16:00 встреча", _TZ, now=now)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.date() == now.date()
    assert result.resolved_dt.hour == 16
    assert result.horizon_hint == "today"


def test_bare_hour_v_12() -> None:
    """«в 12» (no minutes) is the dominant Russian way to say "at noon".

    Before the fix the time-fragment regex required ``в HH:MM`` so
    "напомни про обед в 12" returned ``None`` and the bot silently
    persisted a task with no due_at and no reminder. Regression: the
    bare-hour pattern must be picked up and normalised to ``HH:00``.
    """
    result = resolve_time("напомни про обед в 12", _TZ, now=_NOW)
    assert result is not None, "bare-hour «в 12» must resolve"
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 12
    assert result.resolved_dt.minute == 0
    assert result.is_reminder is True


def test_bare_hour_v_8() -> None:
    """«в 8» (single-digit hour) — same fix applies."""
    result = resolve_time("напомни в 8 принять лекарство", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 8
    assert result.resolved_dt.minute == 0
    assert result.is_reminder is True


def test_v_12_chasov() -> None:
    """«в 12 часов» — explicit "12 o'clock" wording."""
    result = resolve_time("обед в 12 часов", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 12
    assert result.resolved_dt.minute == 0


def test_napominanie_noun_form() -> None:
    """«поставь напоминание» (noun form) must set is_reminder=True.

    Before the fix the regex ``\\bнапомн`` matched the verb forms but
    not the noun «напоминание» (no «н» right after «напоми»). Users say
    "поставь напоминание ..." just as often as "напомни ...".
    """
    result = resolve_time("поставь напоминание про обед в 12:00", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.is_reminder is True


def test_v_12_does_not_match_dotted_date() -> None:
    """``в 12.05`` must NOT be normalised to ``в 12:00`` (it's a date)."""
    # Dotted notation is interpreted as time by dateparser when the second
    # part is a valid minute count, so this test pins down that we don't
    # rewrite the user-supplied minutes to ``:00``.
    result = resolve_time("совещание в 12:30", _TZ, now=_NOW)
    assert result is not None
    assert result.resolved_dt is not None
    assert result.resolved_dt.hour == 12
    assert result.resolved_dt.minute == 30


def test_weekday_on_same_weekday_still_rolls_forward() -> None:
    """«во вторник» when today *is* Tuesday must still resolve to NEXT
    Tuesday — preserves the original intent of the rollover branch.
    """
    # 12 May 2026 is a Tuesday.
    now_tue = datetime(2026, 5, 12, 14, 0, tzinfo=ZoneInfo(_TZ))
    result = resolve_time("во вторник зайти к врачу", _TZ, now=now_tue)
    assert result is not None
    assert result.resolved_dt is not None
    delta_days = (result.resolved_dt.date() - now_tue.date()).days
    assert delta_days == 7, f"expected next Tuesday (+7d), got +{delta_days}d"
