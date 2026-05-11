"""Daily digest builders + cron tick (Phase 4b, extended in PR-G).

Two flavours:

* ``build_morning_digest`` — today's open tasks + anything overdue from
  earlier + week deadlines coming up in the next 7 days. Sent at the
  user's ``morning_digest_at`` (default ``08:00`` local time).
* ``build_evening_digest`` — tasks closed during the day, what's still
  open today, and a peek at tomorrow. Sent at ``evening_digest_at``
  (default ``21:00`` local).

The cron worker (``app/workers/scheduler.py``) calls :func:`tick_digests`
once a minute. Each user's HH:MM slots are evaluated against their local
timezone (``User.tz``) and the digest is built and sent on an exact match
(with catch-up semantics — see :func:`_should_fire_digest`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.base import session_scope
from app.db.models import Horizon, Task, TaskEvent, User, UserSettings
from app.shared.logging import get_logger
from app.shared.time import format_due_local

logger = get_logger(__name__)

PRIORITY_ICONS: dict[str, str] = {"high": "🔴", "medium": "🟡", "low": "🟢"}

# Section caps — the digest is a Telegram message, not a backlog. We
# bias toward signal: the worst 5 overdue items and the 5 nearest week
# deadlines are enough to be actionable; "closed today" is allowed a
# bit more (10) because seeing a long completion list is motivating.
OVERDUE_LIMIT = 5
URGENT_WEEK_LIMIT = 5
COMPLETED_TODAY_LIMIT = 10


def _user_local_now(user_tz: str, now_utc: datetime | None = None) -> datetime:
    """Return *now_utc* converted to the user's timezone (defaults to UTC)."""
    if now_utc is None:
        now_utc = datetime.now(UTC)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    zi: ZoneInfo | timezone
    try:
        zi = ZoneInfo(user_tz or "UTC")
    except ZoneInfoNotFoundError:
        zi = UTC
    return now_utc.astimezone(zi)


def _matches_hhmm(local_dt: datetime, hhmm: str | None) -> bool:
    """Strict ``HH:MM`` match against *local_dt* (no minute slack).

    Kept for backwards compatibility with existing callers and tests;
    new code should prefer :func:`_should_fire_digest`, which adds
    catch-up semantics for delayed scheduler ticks.
    """
    if not hhmm or len(hhmm) != 5 or hhmm[2] != ":":
        return False
    try:
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
    except ValueError:
        return False
    return local_dt.hour == hh and local_dt.minute == mm


def _parse_hhmm(hhmm: str | None) -> tuple[int, int] | None:
    """Parse a strict zero-padded ``HH:MM`` into ``(hh, mm)`` or ``None``.

    Centralises validation so the catch-up predicate, the strict-match
    helper, and any future caller agree on what a malformed slot looks
    like.
    """
    if not hhmm or len(hhmm) != 5 or hhmm[2] != ":":
        return None
    try:
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
    except ValueError:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def _should_fire_digest(
    local_dt: datetime,
    hhmm: str | None,
    last_sent_on: date | None,
    onboarded_local: datetime | None = None,
) -> bool:
    """Return ``True`` if a digest scheduled at ``hhmm`` should fire now.

    Catch-up logic: fires when the user's local time has reached or
    passed the scheduled HH:MM **and** we have not yet fired this
    digest today (per the ``last_sent_on`` gate). This survives
    scheduler tick drift > 60 s — the strict HH:MM match would
    otherwise silently skip the digest if the worker happened to tick
    at 08:00:00 and then 08:01:30. See
    ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-4``.

    The optional ``onboarded_local`` argument suppresses the catch-up
    on the user's first day if they finished onboarding *after* the
    scheduled slot. Without this guard, a user who signs up at
    21:00 local with morning_digest_at=08:00 would immediately
    receive a "good morning" message; their first morning digest
    should land the following day instead.

    Returns ``False`` for malformed ``hhmm`` (None / wrong shape /
    non-numeric); the caller treats that as "no digest configured".
    """
    parsed = _parse_hhmm(hhmm)
    if parsed is None:
        return False
    hh, mm = parsed
    if last_sent_on == local_dt.date():
        # Already fired today — idempotency gate.
        return False
    if (local_dt.hour, local_dt.minute) < (hh, mm):
        return False
    if onboarded_local is not None:
        scheduled_today = local_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if onboarded_local > scheduled_today:
            # User onboarded after today's scheduled slot — first
            # digest of this kind should land tomorrow.
            return False
    return True


def _format_task_line(task: Task, user_tz: str) -> str:
    """Format a single task as ``<icon> <title>[ — в HH:MM]``.

    ``task.due_at`` is naive UTC; rendered in *user_tz* so the user sees
    their own clock. See ``docs/REVIEW-2026-05-09.md::C-2``.
    """
    icon = PRIORITY_ICONS.get(task.priority, "⚪")
    line = f"{icon} {task.title}"
    if task.due_at is not None:
        local = format_due_local(task.due_at, user_tz)
        if local is not None:
            line += f" — в {local}"
    return line


def _format_task_line_with_date(task: Task, user_tz: str) -> str:
    """Format a task with full ``ДД.ММ[ HH:MM]`` suffix.

    Used by the overdue and weekly-deadline sections where "в 09:00"
    on its own is ambiguous — the user needs to see *which day* the
    deadline refers to. Falls back to the icon + title if ``due_at``
    is null (defensive; the callers filter for non-null ``due_at``).
    """
    icon = PRIORITY_ICONS.get(task.priority, "⚪")
    line = f"{icon} {task.title}"
    if task.due_at is None:
        return line
    aware_utc = task.due_at.replace(tzinfo=UTC) if task.due_at.tzinfo is None else task.due_at
    zi: ZoneInfo | timezone
    try:
        zi = ZoneInfo(user_tz or "UTC")
    except ZoneInfoNotFoundError:
        zi = UTC
    local = aware_utc.astimezone(zi)
    date_str = f"{local:%d.%m}"
    # ``00:00`` is the project's "date-only deadline" sentinel — don't
    # render a misleading midnight time on those.
    if local.hour == 0 and local.minute == 0:
        return f"{line} — {date_str}"
    return f"{line} — {date_str} {local:%H:%M}"


def _local_day_bounds_utc(
    user_tz: str, now_utc: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return ``(today_start_utc, today_end_utc)`` as **naive** UTC.

    ``today`` is defined in the user's local timezone (so a Moscow
    user's "today" is 21:00 UTC → 21:00 UTC next day, not 00:00–24:00
    UTC). The result is naive UTC to match ``Task.due_at`` (which the
    rest of the codebase treats as naive UTC — see
    ``app/shared/time.py``).
    """
    local_now = _user_local_now(user_tz, now_utc=now_utc)
    local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_today_end = local_today_start + timedelta(days=1)
    return (
        local_today_start.astimezone(UTC).replace(tzinfo=None),
        local_today_end.astimezone(UTC).replace(tzinfo=None),
    )


async def _open_tasks_for_horizon(
    session: AsyncSession,
    user_id: int,
    slug: str,
) -> list[Task]:
    """Return non-done, non-deleted tasks for *user_id* under the given horizon slug."""
    horizon = (
        await session.exec(
            select(Horizon).where(Horizon.user_id == user_id, Horizon.slug == slug),
        )
    ).first()
    if horizon is None:
        return []
    rows = (
        await session.exec(
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.horizon_id == horizon.id,
                Task.status != "done",
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(Task.created_at),  # type: ignore[arg-type]
        )
    ).all()
    return list(rows)


async def _tasks_overdue(
    session: AsyncSession,
    user_id: int,
    user_tz: str,
    now_utc: datetime | None = None,
    *,
    limit: int = OVERDUE_LIMIT,
) -> list[Task]:
    """Open tasks whose ``due_at`` is **before** the user's local today.

    Returns up to ``limit`` rows, oldest deadline first (the most
    overdue is the most urgent). ``due_at`` is interpreted as naive
    UTC and compared to the user-local day boundary converted back to
    UTC — so a Moscow user with a Friday 18:00 deadline only sees it
    as overdue starting Saturday 00:00 *Moscow time*, not Friday 18:00
    UTC.
    """
    today_start_utc, _ = _local_day_bounds_utc(user_tz, now_utc=now_utc)
    rows = (
        await session.exec(
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status != "done",
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
                Task.due_at.is_not(None),  # type: ignore[union-attr]
                Task.due_at < today_start_utc,  # type: ignore[operator]
            )
            .order_by(Task.due_at)  # type: ignore[arg-type]
            .limit(limit),
        )
    ).all()
    return list(rows)


async def _tasks_urgent_week(
    session: AsyncSession,
    user_id: int,
    user_tz: str,
    now_utc: datetime | None = None,
    *,
    limit: int = URGENT_WEEK_LIMIT,
) -> list[Task]:
    """Open tasks with a deadline in the next 7 user-local days (exclusive of today).

    We skip "today" entries because they appear in the main
    "Сегодня" section already; surfacing them twice in the same
    digest would be noise. Returns up to ``limit`` rows ordered by
    nearest deadline first.
    """
    _, today_end_utc = _local_day_bounds_utc(user_tz, now_utc=now_utc)
    week_end_utc = today_end_utc + timedelta(days=7)
    rows = (
        await session.exec(
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status != "done",
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
                Task.due_at.is_not(None),  # type: ignore[union-attr]
                Task.due_at >= today_end_utc,  # type: ignore[operator]
                Task.due_at < week_end_utc,  # type: ignore[operator]
            )
            .order_by(Task.due_at)  # type: ignore[arg-type]
            .limit(limit),
        )
    ).all()
    return list(rows)


async def _tasks_completed_today(
    session: AsyncSession,
    user_id: int,
    user_tz: str,
    now_utc: datetime | None = None,
    *,
    limit: int = COMPLETED_TODAY_LIMIT,
) -> list[Task]:
    """Tasks the user marked done at any point during today's local day.

    Joins ``Task`` with ``TaskEvent`` filtered on ``kind == "completed"``
    and ``created_at`` inside today's local-day window. Distinct on
    task id because a task could be completed, reopened, and completed
    again on the same day — we want it once.

    Returns up to ``limit`` rows ordered by completion time (newest
    first — the digest is sent in the evening, the most recent
    completion is the freshest).
    """
    today_start_utc, today_end_utc = _local_day_bounds_utc(user_tz, now_utc=now_utc)
    # We over-fetch (limit * 4) and then dedupe by task id in Python.
    # A task could be completed → reopened → completed again on the
    # same day and we want to surface it once at the position of its
    # newest event. Ordering by ``created_at DESC`` puts that newest
    # event first so the Python dedupe sees it before any older one.
    # ``Task.id`` and ``TaskEvent.task_id`` are typed as plain ``int``
    # by SQLModel; use the SQLAlchemy ``__table__`` columns directly
    # so the join / comparisons go through SQLA's expression API
    # rather than producing literal ``bool`` (which mypy then rejects).
    task_id_col = Task.__table__.c.id  # type: ignore[attr-defined]
    event_task_id_col = TaskEvent.__table__.c.task_id  # type: ignore[attr-defined]
    event_kind_col = TaskEvent.__table__.c.kind  # type: ignore[attr-defined]
    event_created_at_col = TaskEvent.__table__.c.created_at  # type: ignore[attr-defined]
    rows = (
        await session.exec(
            select(Task)
            .join(TaskEvent, event_task_id_col == task_id_col)
            .where(
                Task.user_id == user_id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
                event_kind_col == "completed",
                event_created_at_col >= today_start_utc,
                event_created_at_col < today_end_utc,
            )
            .order_by(event_created_at_col.desc())
            .limit(limit * 4),
        )
    ).all()
    # Deduplicate by id while preserving order (a task can match the
    # join multiple times if it was completed twice today; we want it
    # once, at the position of its most recent event).
    seen: set[int] = set()
    deduped: list[Task] = []
    for task in rows:
        if task.id is None or task.id in seen:
            continue
        seen.add(task.id)
        deduped.append(task)
        if len(deduped) >= limit:
            break
    return deduped


async def build_morning_digest(
    session: AsyncSession,
    user: User,
    *,
    now_utc: datetime | None = None,
) -> str:
    """Compose the morning digest: today + overdue + this-week deadlines.

    The ``now_utc`` knob exists for tests (so they can pin the
    "today" window deterministically); production callers omit it
    and the helpers fall back to ``datetime.now(UTC)``.
    """
    if user.id is None:
        raise RuntimeError("user.id is required for digest")
    today = await _open_tasks_for_horizon(session, user.id, "today")
    overdue = await _tasks_overdue(session, user.id, user.tz, now_utc=now_utc)
    urgent_week = await _tasks_urgent_week(session, user.id, user.tz, now_utc=now_utc)

    if not today and not overdue and not urgent_week:
        return "🌅 Доброе утро!\n\nНа сегодня задач не запланировано — лёгкого дня."

    lines: list[str] = ["🌅 Доброе утро!"]
    if today:
        lines.append("")
        lines.append("Сегодня:")
        lines.extend(_format_task_line(t, user.tz) for t in today)
    if overdue:
        lines.append("")
        lines.append("Просрочено:")
        lines.extend(_format_task_line_with_date(t, user.tz) for t in overdue)
    if urgent_week:
        lines.append("")
        lines.append("Горячие дедлайны на неделе:")
        lines.extend(_format_task_line_with_date(t, user.tz) for t in urgent_week)
    return "\n".join(lines)


async def build_evening_digest(
    session: AsyncSession,
    user: User,
    *,
    now_utc: datetime | None = None,
) -> str:
    """Compose the evening digest: closed today + leftovers + tomorrow."""
    if user.id is None:
        raise RuntimeError("user.id is required for digest")
    completed = await _tasks_completed_today(session, user.id, user.tz, now_utc=now_utc)
    today = await _open_tasks_for_horizon(session, user.id, "today")
    tomorrow = await _open_tasks_for_horizon(session, user.id, "tomorrow")
    lines: list[str] = ["🌙 Подводим итоги дня."]
    if completed:
        lines.append("")
        # Subtle but motivating: lead with the win count. The list
        # below it makes the wins concrete.
        lines.append(f"Закрыто сегодня — {len(completed)} ✅")
        lines.extend(f"— {t.title}" for t in completed)
    if today:
        lines.append("")
        lines.append("Осталось на сегодня:")
        lines.extend(_format_task_line(t, user.tz) for t in today)
    elif not completed:
        # Only celebrate "all clear" when there was no activity at
        # all today — if the user closed five tasks and has nothing
        # left, the "Закрыто — 5 ✅" line is already the win.
        lines.append("")
        lines.append("Сегодня всё закрыто 🎉.")
    if tomorrow:
        lines.append("")
        lines.append("Завтра:")
        lines.extend(_format_task_line(t, user.tz) for t in tomorrow)
    return "\n".join(lines)


async def tick_digests(bot: Bot, *, now: datetime | None = None) -> dict[str, int]:
    """Send morning/evening digests to users whose local HH:MM matches now.

    Idempotent against sub-minute scheduler ticks: each digest is gated
    on ``UserSettings.last_morning_digest_on`` /
    ``last_evening_digest_on`` (user-local date). If the gate is already
    set to today's local date, we skip — so two ticks within the same
    minute (or even the same wall-clock second) can never double-send.
    See ``docs/REVIEW-2026-05-09.md::C-3``.

    Returns a counter dict (``morning``, ``evening``, ``errors``).
    """
    sent_morning = sent_evening = errors = 0
    async with session_scope() as session:
        users = list((await session.exec(select(User))).all())
        for user in users:
            if user.id is None or user.onboarded_at is None:
                continue
            settings = (
                await session.exec(
                    select(UserSettings).where(UserSettings.user_id == user.id),
                )
            ).first()
            if settings is None:
                continue
            local = _user_local_now(user.tz, now_utc=now)
            local_date = local.date()
            # Convert onboarded_at (naive UTC) to user-local so
            # _should_fire_digest can suppress the catch-up on day 1
            # for users who joined after today's scheduled slot.
            onboarded_local = _user_local_now(user.tz, now_utc=user.onboarded_at)
            # Catch-up semantics: fire whenever user-local time has
            # reached the scheduled HH:MM and we haven't fired yet today.
            # The idempotency gate (last_*_digest_on) prevents double-sends
            # within the same user-local day. See R-NEW-I-4.
            morning = _should_fire_digest(
                local,
                settings.morning_digest_at,
                settings.last_morning_digest_on,
                onboarded_local=onboarded_local,
            )
            evening = _should_fire_digest(
                local,
                settings.evening_digest_at,
                settings.last_evening_digest_on,
                onboarded_local=onboarded_local,
            )
            if not morning and not evening:
                continue
            try:
                if morning:
                    text = await build_morning_digest(session, user, now_utc=now)
                    settings.last_morning_digest_on = local_date
                    # Phase 6.3: pin the digest so we can re-edit it as
                    # tasks complete during the day. ``send_and_pin``
                    # falls back to a plain ``send_message`` if pinning
                    # fails (e.g. group chat where bot isn't admin).
                    from app.bot.pinned_today import send_and_pin_morning_digest

                    await send_and_pin_morning_digest(bot, session, user, settings, text)
                    sent_morning += 1
                if evening:
                    text = await build_evening_digest(session, user, now_utc=now)
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    settings.last_evening_digest_on = local_date
                    sent_evening += 1
                # Persist the gate flips so a follow-up tick in the same
                # session_scope (or a crash before commit) doesn't lose
                # them. session_scope commits on exit; this flush makes
                # the gate visible to subsequent loop iterations too.
                session.add(settings)
                await session.flush()
            except Exception as exc:
                errors += 1
                logger.warning(
                    "digest.send_failed",
                    user_id=user.id,
                    error=str(exc)[:200],
                )
    if sent_morning or sent_evening or errors:
        logger.info(
            "digests.tick",
            morning=sent_morning,
            evening=sent_evening,
            errors=errors,
        )
    return {"morning": sent_morning, "evening": sent_evening, "errors": errors}
