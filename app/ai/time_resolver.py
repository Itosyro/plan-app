"""Time resolver — extract and parse Russian time expressions.

Pure Python (no LLM). Uses ``dateparser`` with Russian-specific
preprocessing to handle idioms like "через полчаса", "вечером",
"на этой неделе".
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from app.ai.schemas import ResolvedTime
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Препроцесс: замена русских идиом на формы, понятные dateparser
_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bчерез\s+полчаса\b", re.I), "через 30 минут"),
    (re.compile(r"\bчерез\s+полтора\s+часа\b", re.I), "через 1 час 30 минут"),
    (re.compile(r"\bчерез\s+сутки\b", re.I), "через 24 часа"),
    (re.compile(r"\bчерез\s+час\b", re.I), "через 60 минут"),
    (re.compile(r"\bчерез\s+минуту\b", re.I), "через 1 минуту"),
    (re.compile(r"\bчерез\s+неделю\b", re.I), "через 7 дней"),
    (re.compile(r"\bчерез\s+месяц\b", re.I), "через 30 дней"),
    # Anchors for "вечером" / "утром" are inserted dynamically by
    # ``_preprocess`` based on per-user settings (M-6). The static
    # entries below are kept only as fallback sentinels — they are
    # overridden when ``morning_anchor`` / ``evening_anchor`` kwargs
    # are passed to ``resolve_time``.
    (re.compile(r"\bвечером\b", re.I), "в 19:00"),
    (re.compile(r"\bутром\b", re.I), "в 09:00"),
    (re.compile(r"\bк\s+утру\b", re.I), "в 09:00"),
    (re.compile(r"\bна\s+этой\s+неделе\b", re.I), "в воскресенье 23:59"),
    (re.compile(r"\bв\s+течение\s+дня\b", re.I), "сегодня в 23:59"),
    (re.compile(r"\bследующий\b", re.I), "next"),
    (re.compile(r"\bследующую\b", re.I), "next"),
    (re.compile(r"\bследующее\b", re.I), "next"),
    (re.compile(r"\bследующего\b", re.I), "next"),
]

# Паттерны для извлечения временных выражений из текста
_TIME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(через\s+\d+\s*(?:минут[аыу]?|час(?:а|ов)?|дн(?:ей|я)|недел[юиь]))",
        re.I,
    ),
    re.compile(r"(через\s+полчаса)", re.I),
    re.compile(r"(через\s+полтора\s+часа)", re.I),
    re.compile(r"(через\s+сутки)", re.I),
    re.compile(r"(через\s+час)\b", re.I),
    re.compile(r"(через\s+минуту)\b", re.I),
    re.compile(r"(через\s+неделю)\b", re.I),
    re.compile(r"(через\s+месяц)\b", re.I),
    re.compile(r"(завтра(?:\s+в\s+\d{1,2}[:.]\d{2})?)", re.I),
    re.compile(r"(послезавтра(?:\s+в\s+\d{1,2}[:.]\d{2})?)", re.I),
    re.compile(r"(сегодня(?:\s+в\s+\d{1,2}[:.]\d{2})?)", re.I),
    re.compile(r"(в\s+\d{1,2}[:.]\d{2})", re.I),
    re.compile(
        r"(до\s+(?:понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья))", re.I
    ),
    re.compile(
        r"((?:в|во)\s+(?:понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресенье))",
        re.I,
    ),
    re.compile(r"((?:утром|вечером|к\s+утру))", re.I),
    re.compile(r"(на\s+этой\s+неделе)", re.I),
    re.compile(r"(в\s+течение\s+дня)", re.I),
    re.compile(
        r"(next\s+(?:понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресенье))", re.I
    ),
    re.compile(r"(до\s+конца\s+(?:недели|месяца|дня))", re.I),
]


def _preprocess(
    text: str,
    *,
    morning_anchor: str = "09:00",
    evening_anchor: str = "19:00",
) -> str:
    """Apply Russian-specific replacements before dateparser.

    ``morning_anchor`` / ``evening_anchor`` override the hard-coded
    ``09:00`` / ``19:00`` so each user can customise what "утром" and
    "вечером" mean. See ``docs/REVIEW-2026-05-09.md::M-6``.
    """
    result = text
    for pattern, replacement in _REPLACEMENTS:
        # Override anchor replacements with per-user values.
        if pattern.pattern == r"\bвечером\b":
            replacement = f"в {evening_anchor}"
        elif pattern.pattern in (r"\bутром\b", r"\bк\s+утру\b"):
            replacement = f"в {morning_anchor}"
        result = pattern.sub(replacement, result)
    return result


def _extract_time_fragment(text: str) -> str | None:
    """Try to find a time expression in the text."""
    for pattern in _TIME_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def _horizon_from_delta(now: datetime, dt: datetime) -> str:
    """Determine horizon slug from the time difference."""
    delta = dt.date() - now.date()
    days = delta.days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days <= 7:
        return "week"
    if days <= 30:
        return "month"
    if days <= 365:
        return "year"
    return "someday"


def resolve_time(
    text: str,
    user_tz: str,
    now: datetime | None = None,
    *,
    morning_anchor: str = "09:00",
    evening_anchor: str = "19:00",
) -> ResolvedTime | None:
    """Parse Russian time expressions from *text*.

    ``morning_anchor`` / ``evening_anchor`` control the HH:MM values
    substituted for "утром" / "вечером". Defaults match the old
    hard-coded behaviour.

    Returns ``None`` if no time expression was found.
    """
    tz = ZoneInfo(user_tz)
    if now is None:
        now = datetime.now(tz)

    fragment = _extract_time_fragment(text)
    if fragment is None:
        return None

    preprocessed = _preprocess(
        fragment,
        morning_anchor=morning_anchor,
        evening_anchor=evening_anchor,
    )

    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": user_tz,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": now.replace(tzinfo=None),
        "DATE_ORDER": "DMY",
    }

    dt = dateparser.parse(preprocessed, languages=["ru"], settings=settings)
    if dt is None:
        logger.debug("time_resolver.no_parse", fragment=fragment, preprocessed=preprocessed)
        return None

    # «во вторник» (если сегодня вторник) -> следующий вторник.
    # НО — не для явного «сегодня в HH:MM»: пользователь сам сказал,
    # что речь про сегодня, и подкидывать ему +7 дней категорически
    # неверно (раньше «сегодня в 10:00» в 14:00 → задача через
    # неделю). Если время уже прошло, оставляем дату сегодняшней —
    # вызывающая сторона/UI решит, что показать («уже прошло» или
    # ничего). См. ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-2``.
    text_lower = text.lower()
    explicit_today = bool(re.search(r"\b(сегодня|сейчас|today)\b", text_lower))
    if dt.date() == now.date() and dt <= now and "через" not in text_lower and not explicit_today:
        dt = dt + timedelta(days=7)

    horizon_hint = _horizon_from_delta(now, dt)

    # Проверяем, есть ли в тексте «напомни» / «напомнить»
    is_reminder = bool(re.search(r"\bнапомн", text, re.I))

    logger.info(
        "time_resolver.done",
        fragment=fragment,
        resolved_dt=dt.isoformat(),
        horizon_hint=horizon_hint,
        is_reminder=is_reminder,
    )

    return ResolvedTime(
        original_text=fragment,
        resolved_dt=dt,
        is_reminder=is_reminder,
        horizon_hint=horizon_hint,
    )
