"""Tests for time_resolver — pure Python date parsing, no LLM."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.ai.time_resolver import parse_user_datetime, resolve_time

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


# ── Аудит 2026-07-26: таймзонный кадр, «послезавтра», составные фразы ──
#
# _NOW = 12:00 МСК (09:00 UTC). Старый баг: для time-only «в HH:MM»
# dateparser сравнивал «прошлое/будущее» в кадре, сдвинутом на UTC-офсет,
# и «в 14:00» (будущее!) уезжало на завтра.


@pytest.mark.parametrize(
    "tz",
    ["Europe/Moscow", "Asia/Novosibirsk", "America/New_York"],
)
def test_time_only_future_stays_today(tz: str) -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(tz))
    result = resolve_time("в 14:00 звонок", tz, now=now)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.date() == now.date()
    assert result.resolved_dt.hour == 14


@pytest.mark.parametrize(
    "tz",
    ["Europe/Moscow", "Asia/Novosibirsk", "America/New_York"],
)
def test_time_only_past_moves_to_tomorrow(tz: str) -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(tz))
    result = resolve_time("в 10:00 звонок", tz, now=now)
    assert result is not None and result.resolved_dt is not None
    assert (result.resolved_dt.date() - now.date()).days == 1
    assert result.resolved_dt.hour == 10


def test_poslezavtra_is_two_days_ahead() -> None:
    # Раньше «послезавтра» матчился паттерном «завтра» → на день раньше.
    result = resolve_time("послезавтра сдать отчёт", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert (result.resolved_dt.date() - _NOW.date()).days == 2


def test_poslezavtra_with_time() -> None:
    result = resolve_time("послезавтра в 10:00 сдать отчёт", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert (result.resolved_dt.date() - _NOW.date()).days == 2
    assert result.resolved_dt.hour == 10


def test_weekday_with_time_keeps_weekday() -> None:
    # Раньше «в 15:00» перебивал «в пятницу» — задача падала на завтра.
    # 2026-05-08 — пятница; «в пятницу в 15:00» при 12:00 МСК → сегодня 15:00
    # (время ещё впереди) ЛИБО следующая пятница — главное, что ПЯТНИЦА.
    result = resolve_time("в пятницу в 15:00 отчёт", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.weekday() == 4  # пятница
    assert result.resolved_dt.hour == 15


def test_zavtra_bare_hour() -> None:
    # «завтра в 19» (без :00) раньше терял время суток.
    result = resolve_time("завтра в 19 тренировка", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert (result.resolved_dt.date() - _NOW.date()).days == 1
    assert result.resolved_dt.hour == 19


def test_cherez_dva_dnya_s_vremenem() -> None:
    # «через 2 дня в 18:00» раньше терял «в 18:00».
    result = resolve_time("через 2 дня в 18:00 встреча", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert (result.resolved_dt.date() - _NOW.date()).days == 2
    assert result.resolved_dt.hour == 18


def test_sleduyushchaya_pyatnitsa_resolves() -> None:
    # Раньше «следующ*» → "next" — dateparser отдавал None.
    result = resolve_time("в следующую пятницу созвон", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.weekday() == 4


def test_do_pyatnitsy_resolves() -> None:
    # «до пятницы» раньше извлекался, но парсился в None.
    result = resolve_time("сделать до пятницы", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.weekday() == 4


def test_do_kontsa_nedeli() -> None:
    result = resolve_time("закрыть до конца недели", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.weekday() == 6  # воскресенье
    assert result.resolved_dt.hour == 23


def test_do_kontsa_mesyatsa() -> None:
    result = resolve_time("оплатить до конца месяца", _TZ, now=_NOW)
    assert result is not None and result.resolved_dt is not None
    assert result.resolved_dt.month == _NOW.month
    assert result.resolved_dt.day == 31  # май
    assert result.resolved_dt.hour == 23


def test_v_tri_raza_not_a_deadline() -> None:
    # «увеличить продажи в 3 раза» раньше получало дедлайн 03:00.
    result = resolve_time("увеличить продажи в 3 раза", _TZ, now=_NOW)
    assert result is None


def test_parse_user_datetime_uses_user_tz() -> None:
    # Хелпер для edit-веток: «завтра в 10» = 10:00 в зоне ЮЗЕРА.
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
    parsed = parse_user_datetime("завтра в 10", _TZ, now=now)
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.hour == 10
    assert (parsed.date() - now.date()).days == 1
    # В naive-UTC это 07:00 (МСК = UTC+3) — раньше сохранялось 10:00 UTC.
    from app.shared.time import to_naive_utc

    assert to_naive_utc(parsed).hour == 7


@pytest.mark.parametrize("raw", ["на 15:00", "в 15:00", "15:00"])
def test_parse_user_datetime_time_only_today(raw: str) -> None:
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
    parsed = parse_user_datetime(raw, _TZ, now=now)
    assert parsed is not None
    assert parsed.date() == now.date()
    assert parsed.hour == 15


def test_parse_user_datetime_honours_evening_anchor() -> None:
    """M-6 anchors must reach the edit-executor surface too.

    Раньше ``parse_user_datetime`` звал ``_preprocess`` без якорей, и
    «напомни вечером» через голосовую правку давало дефолтные 19:00
    вместо настроенных пользователем.
    """
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
    parsed = parse_user_datetime("вечером", _TZ, now=now, evening_anchor="21:00")
    assert parsed is not None
    assert parsed.hour == 21
    assert parsed.date() == now.date()


def test_parse_user_datetime_honours_morning_anchor() -> None:
    """Same for «утром» → morning_anchor."""
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
    parsed = parse_user_datetime("утром", _TZ, now=now, morning_anchor="08:00")
    assert parsed is not None
    assert parsed.hour == 8
    # 08:00 сегодня уже прошло в 12:00 — переносится на завтра.
    assert (parsed.date() - now.date()).days == 1


def test_parse_user_datetime_anchor_defaults_unchanged() -> None:
    """Without kwargs the old hard-coded 19:00 / 09:00 still apply."""
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
    evening = parse_user_datetime("вечером", _TZ, now=now)
    morning = parse_user_datetime("утром", _TZ, now=now)
    assert evening is not None and evening.hour == 19
    assert morning is not None and morning.hour == 9
