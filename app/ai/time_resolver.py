"""Time resolver — extract and parse Russian time expressions.

Pure Python (no LLM). Uses ``dateparser`` with Russian-specific
preprocessing to handle idioms like "через полчаса", "вечером",
"на этой неделе".
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from app.ai.schemas import ResolvedTime
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Частотные НЕ-временные продолжения после «в N»: «увеличить продажи в
# 3 раза» не должно превращаться в дедлайн 03:00. Список расширяем по
# мере встречаемых ложных срабатываний.
_NON_TIME_UNITS = (
    r"раз|человек|штук|шт|км|кг|грамм|рубл|тыс|млн|миллион|миллиард|"
    r"процент|минут|секунд|дня|дней|недел|месяц|год|лет|этап|шаг|пункт"
)

_WEEKDAYS_RX = r"(?:понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресенье)"

# Приводим родительный падеж «до пятницы» к винительному «в пятницу»,
# который dateparser понимает.
_WEEKDAY_GEN_TO_ACC = {
    "понедельника": "понедельник",
    "вторника": "вторник",
    "среды": "среду",
    "четверга": "четверг",
    "пятницы": "пятницу",
    "субботы": "субботу",
    "воскресенья": "воскресенье",
}

# Препроцесс: замена русских идиом на формы, понятные dateparser
# Bare-hour normalisation: ``в 12`` (without :MM) is the dominant
# Russian phrasing for "at twelve o'clock" but dateparser treats the
# fragment as a date — we expand it to ``в 12:00`` so it parses as a
# time-of-day. Run before the other replacements so subsequent
# substitutions see the canonical form. Lookahead avoids matching
# ranges like ``в 12 30`` (spaced-time) and dotted-date forms like
# ``в 12.05``.
_BARE_HOUR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(в|во)\s+(\d{1,2})\b"
            r"(?!\s*[:.]\s*\d|\s+\d|\s*час|\s*(?:" + _NON_TIME_UNITS + r")\w*)",
            re.I,
        ),
        r"\1 \2:00",
    ),
    # ``в 12 часов`` / ``в 12 ч.`` → ``в 12:00`` so dateparser sees a
    # bare time. Russian users say "в 12 часов" interchangeably with
    # "в 12". The trailing ``часов``/``часа``/``час`` token is
    # otherwise ignored by dateparser, but specifying ``:00`` makes
    # the parse deterministic.
    (
        re.compile(
            r"\b(в|во)\s+(\d{1,2})\s+час(?:ов|а|у|е|ом)?\b",
            re.I,
        ),
        r"\1 \2:00",
    ),
]

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
    # «до конца недели/дня» → конкретный дедлайн. «до конца месяца»
    # обрабатывается кодом в ``resolve_time`` (последний день месяца
    # зависит от текущей даты — статической заменой не выразить).
    (re.compile(r"\bдо\s+конца\s+недели\b", re.I), "в воскресенье 23:59"),
    (re.compile(r"\bдо\s+конца\s+дня\b", re.I), "сегодня в 23:59"),
    # «в следующую пятницу» — dateparser с languages=["ru"] НЕ понимает
    # ни «следующую пятницу», ни англ. «next пятницу» (старые замены
    # «следующ*» → "next" были мёртвым кодом: parse всегда давал None).
    # Убираем слово «следующ*» и парсим как ближайшую будущую пятницу.
    # Семантика «эта vs следующая неделя» в русском неоднозначна;
    # «ближайшая будущая» — честный и предсказуемый выбор.
    (re.compile(r"\bследующ\w+\s+(?=" + _WEEKDAYS_RX + r")", re.I), ""),
]


def _replace_do_weekday(m: re.Match[str]) -> str:
    """«до пятницы» → «в пятницу» (родительный → винительный)."""
    return "в " + _WEEKDAY_GEN_TO_ACC.get(m.group(1).lower(), m.group(1))


# Хвост «… в HH[:MM]» / «… в HH часов», прицепляемый к дате-словам
# («завтра в 19», «в пятницу в 15:00», «через 2 дня в 18:00»). Раньше
# экстрактор брал только ПЕРВЫЙ матч из списка, и «в 15:00» перебивал
# «в пятницу …» — день недели терялся; а «завтра в 19» без двоеточия
# вообще не захватывал время. Голый час нормализуется в HH:00
# препроцессором.
_TIME_TAIL = r"(?:\s+в\s+\d{1,2}(?:[:.]\d{2})?(?:\s+час(?:ов|а|у)?)?)?"

# Паттерны для извлечения временных выражений из текста. Порядок важен:
# более специфичные (составные) — выше, «послезавтра» — раньше «завтра».
_TIME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(через\s+\d+\s*(?:минут[аыу]?|час(?:а|ов)?|дн(?:ей|я)|недел[юиь])" + _TIME_TAIL + r")",
        re.I,
    ),
    re.compile(r"(через\s+полчаса)", re.I),
    re.compile(r"(через\s+полтора\s+часа)", re.I),
    re.compile(r"(через\s+сутки)", re.I),
    re.compile(r"(через\s+час)\b", re.I),
    re.compile(r"(через\s+минуту)\b", re.I),
    re.compile(r"(через\s+неделю" + _TIME_TAIL + r")", re.I),
    re.compile(r"(через\s+месяц" + _TIME_TAIL + r")", re.I),
    re.compile(r"(послезавтра" + _TIME_TAIL + r")", re.I),
    re.compile(r"((?<!после)завтра" + _TIME_TAIL + r")", re.I),
    re.compile(r"(сегодня" + _TIME_TAIL + r")", re.I),
    # Составные «(в следующую) пятницу (в 15:00)» — выше голого времени,
    # иначе «в 15:00» перебьёт день недели.
    re.compile(r"((?:в|во)\s+следующ\w+\s+" + _WEEKDAYS_RX + _TIME_TAIL + r")", re.I),
    re.compile(r"((?:в|во)\s+" + _WEEKDAYS_RX + _TIME_TAIL + r")", re.I),
    re.compile(
        r"(до\s+(?:понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья))", re.I
    ),
    # Match ``в HH:MM`` first (more specific), then bare ``в HH`` /
    # ``в HH часов``. The bare-hour pattern is preprocessed to
    # ``в HH:00`` before dateparser sees it; here we only need the
    # *fragment extractor* to grab the right slice of the user text.
    re.compile(r"(в\s+\d{1,2}[:.]\d{2})", re.I),
    re.compile(r"((?:в|во)\s+\d{1,2}\s+час(?:ов|а|у|е|ом)?)", re.I),
    re.compile(
        r"((?:в|во)\s+(?:[01]?\d|2[0-3]))\b"
        r"(?!\s*[:.]\s*\d|\s+\d|\s*(?:" + _NON_TIME_UNITS + r")\w*)",
        re.I,
    ),
    re.compile(r"((?:утром|вечером|к\s+утру))", re.I),
    re.compile(r"(на\s+этой\s+неделе)", re.I),
    re.compile(r"(в\s+течение\s+дня)", re.I),
    re.compile(r"(до\s+конца\s+(?:недели|месяца|дня))", re.I),
]

# «в 15:00» / «в 15» / «в 15 часов» БЕЗ слов даты — для таких фрагментов
# dateparser с TIMEZONE+naive RELATIVE_BASE сравнивает «прошлое/будущее»
# в сдвинутой на UTC-офсет системе координат (наблюдаемо: Москва, сейчас
# 14:00 — «в 15:00» уезжает на завтра). Пост-коррекция в
# ``_correct_time_only_frame`` возвращает такие результаты на место.
# Предлог опционален: из edit-интентов сырьё приходит и как «на 14:00»,
# и как голое «15:00» — им нужна та же коррекция суток.
_TIME_ONLY_RX = re.compile(
    r"(?:(?:в|во|на|к)\s+)?\d{1,2}(?:[:.]\d{2})?(?:\s+час(?:ов|а|у|е|ом)?)?", re.I
)


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
    for pattern, repl in _BARE_HOUR_PATTERNS:
        result = pattern.sub(repl, result)
    # «до пятницы» → «в пятницу»: dateparser не понимает родительный
    # падеж после «до» (эти фрагменты всегда парсились в None).
    result = re.sub(
        r"\bдо\s+(понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья)\b",
        _replace_do_weekday,
        result,
        flags=re.I,
    )
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


def _parse_with_user_base(preprocessed: str, user_tz: str, now: datetime) -> datetime | None:
    """Run dateparser with the project-standard settings.

    ``RELATIVE_BASE`` намеренно передаётся как ЛОКАЛЬНОЕ naive-время
    пользователя: относительная арифметика («через 30 минут», «завтра»)
    у dateparser считается прямо от базы, и локальная база даёт
    правильный локальный результат. Не переводить базу в UTC —
    проверено вживую: «через 30 минут» от UTC-базы даёт время,
    сдвинутое на офсет.
    """
    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": user_tz,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": now.replace(tzinfo=None),
        "DATE_ORDER": "DMY",
    }
    return dateparser.parse(preprocessed, languages=["ru"], settings=settings)


def _correct_time_only_frame(dt: datetime, fragment: str, now: datetime) -> datetime:
    """Fix dateparser's shifted past/future frame for time-only fragments.

    Для фрагментов вида «в 15:00» dateparser сравнивает кандидата с
    ``RELATIVE_BASE`` так, будто база задана в UTC, — граница
    «прошлое → перенести на завтра» смещается ровно на UTC-офсет
    пользователя. Для Москвы (+3) это значит: в 14:00 «в 15:00»
    прыгало на завтра, а «в 12:00» на сегодня-в-прошлом не попадало
    никогда. Коррекция возвращает результат в правильные сутки в обе
    стороны (положительные и отрицательные офсеты).
    """
    if not _TIME_ONLY_RX.fullmatch(fragment.strip()):
        return dt
    prev = dt - timedelta(days=1)
    if prev > now:
        # Упихнуто на завтра, хотя сегодняшний слот ещё впереди.
        return prev
    if dt <= now:
        # Оставлено в прошлом (кадр отрицательного офсета).
        return dt + timedelta(days=1)
    return dt


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

    # «до конца месяца» — последний день ТЕКУЩЕГО месяца зависит от
    # даты, статической заменой под dateparser не выразить. Считаем сами.
    if re.search(r"\bдо\s+конца\s+месяца\b", fragment, re.I):
        last_day = calendar.monthrange(now.year, now.month)[1]
        dt = now.replace(day=last_day, hour=23, minute=59, second=0, microsecond=0)
    else:
        preprocessed = _preprocess(
            fragment,
            morning_anchor=morning_anchor,
            evening_anchor=evening_anchor,
        )
        parsed = _parse_with_user_base(preprocessed, user_tz, now)
        if parsed is None:
            logger.debug("time_resolver.no_parse", fragment=fragment, preprocessed=preprocessed)
            return None
        dt = _correct_time_only_frame(parsed, fragment, now)

    # «во вторник» (если сегодня вторник) -> следующий вторник.
    # НО — не для явного «сегодня в HH:MM»: пользователь сам сказал,
    # что речь про сегодня, и подкидывать ему +7 дней категорически
    # неверно (раньше «сегодня в 10:00» в 14:00 → задача через
    # неделю). Если время уже прошло, оставляем дату сегодняшней —
    # вызывающая сторона/UI решит, что показать («уже прошло» или
    # ничего). См. ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-2``.
    # Time-only фрагменты сюда не попадают — их сутки уже выправила
    # ``_correct_time_only_frame`` (иначе «в 12:00» получало бы +7 дней).
    text_lower = text.lower()
    explicit_today = bool(re.search(r"\b(сегодня|сейчас|today)\b", text_lower))
    if (
        not _TIME_ONLY_RX.fullmatch(fragment.strip())
        and dt.date() == now.date()
        and dt <= now
        and "через" not in text_lower
        and not explicit_today
    ):
        dt = dt + timedelta(days=7)

    horizon_hint = _horizon_from_delta(now, dt)

    # Detect explicit reminder intent. Matches «напомни», «напомнить»,
    # «напомню», «напоминание», «напоминай», «поставь напоминание»,
    # «поставь напоминалку», «напоминалку». The ``\bнапомн`` prefix
    # covers the verb forms; ``\bнапомина`` covers the noun forms.
    is_reminder = bool(re.search(r"\b(?:напомн|напомина)", text, re.I))

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


def parse_user_datetime(
    raw: str,
    user_tz: str,
    now: datetime | None = None,
) -> datetime | None:
    """Parse a free-form Russian date/time expression in the user's timezone.

    Общий парсер для веток edit-executor'а (set_due / reorder_time /
    set_reminder): раньше они звали ``dateparser.parse`` БЕЗ таймзоны,
    и на UTC-сервере «напомни завтра в 10» для москвича записывалось
    как 10:00 UTC — напоминание приходило в 13:00 МСК. Здесь — те же
    настройки и та же пост-коррекция, что и в :func:`resolve_time`,
    поэтому «завтра в 9», «в 15:00», «через час» ведут себя одинаково
    во всех интентах.

    Returns an AWARE datetime in the user's zone (callers convert with
    ``to_naive_utc``), or ``None`` when nothing parseable was found.
    """
    tz = ZoneInfo(user_tz)
    if now is None:
        now = datetime.now(tz)
    stripped = raw.strip()
    if not stripped:
        return None
    # Из reorder-интентов время приходит как «на 14:00» — dateparser
    # такой предлог не понимает, нормализуем в «в 14:00».
    normalized = re.sub(r"^на\s+", "в ", stripped, flags=re.I)
    parsed = _parse_with_user_base(_preprocess(normalized), user_tz, now)
    if parsed is None:
        return None
    dt = _correct_time_only_frame(parsed, stripped, now)
    # Тот же guard «во вторник, а сегодня вторник → следующий вторник»,
    # что и в resolve_time (для не-time-only выражений).
    if (
        not _TIME_ONLY_RX.fullmatch(stripped)
        and dt.date() == now.date()
        and dt <= now
        and "через" not in stripped.lower()
        and not re.search(r"\b(сегодня|сейчас)\b", stripped, re.I)
    ):
        dt = dt + timedelta(days=7)
    return dt
