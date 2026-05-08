"""Reminder extractor — find explicit "напомни через X" in text.

Pure Python + dateparser. Returns ``None`` if no explicit reminder
request is found.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import dateparser

from app.ai.schemas import ReminderInfo
from app.ai.time_resolver import _preprocess
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Проверка наличия «напомни» / «напомнить» / «напоминание»
_HAS_REMINDER = re.compile(r"\bнапомн\w*", re.I)

# Паттерны для извлечения временной фразы из текста с «напомни»
_TIME_AFTER_REMINDER: list[re.Pattern[str]] = [
    re.compile(r"\bнапомн\w*\s+(через\s+\d+\s*(?:минут\w*|час\w*|дн\w*|недел\w*))", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+полчаса)", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+полтора\s+часа)", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+сутки)", re.I),
    re.compile(r"\bнапомн\w*\s+(завтра(?:\s+в\s+\d{1,2}[:.]\d{2})?)", re.I),
    re.compile(r"\bнапомн\w*\s+(послезавтра(?:\s+в\s+\d{1,2}[:.]\d{2})?)", re.I),
    re.compile(r"\bнапомн\w*\s+(в\s+\d{1,2}[:.]\d{2})", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+час)\b", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+минуту)\b", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+неделю)\b", re.I),
    re.compile(r"\bнапомн\w*\s+(через\s+месяц)\b", re.I),
]


def _extract_time_after_napomni(text: str) -> str | None:
    """Extract the time expression that follows 'напомни'."""
    for pattern in _TIME_AFTER_REMINDER:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def extract_reminder(
    text: str,
    user_tz: str,
    now: datetime | None = None,
) -> ReminderInfo | None:
    """Extract an explicit reminder request from *text*.

    Returns ``None`` if no "напомни" / "напомнить" pattern is found.
    """
    if not _HAS_REMINDER.search(text):
        return None

    time_part = _extract_time_after_napomni(text)
    if not time_part:
        return None

    tz = ZoneInfo(user_tz)
    if now is None:
        now = datetime.now(tz)

    preprocessed = _preprocess(time_part)

    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": user_tz,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": now.replace(tzinfo=None),
        "DATE_ORDER": "DMY",
    }

    dt = dateparser.parse(preprocessed, languages=["ru"], settings=settings)  # type: ignore[arg-type]
    if dt is None:
        logger.debug("reminder_extractor.no_parse", time_part=time_part)
        return None

    logger.info(
        "reminder_extractor.done",
        fire_at=dt.isoformat(),
    )

    return ReminderInfo(fire_at=dt, original_text=text)
