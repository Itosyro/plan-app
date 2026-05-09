"""Daily digest builders + cron tick (Phase 4b).

Two flavours:

* ``build_morning_digest`` — list of today's still-open tasks, sent at the
  user's ``morning_digest_at`` (default ``08:00`` local time).
* ``build_evening_digest`` — wrap-up of what's still open today plus a peek
  at tomorrow, sent at ``evening_digest_at`` (default ``21:00`` local).

The cron worker (``app/workers/scheduler.py``) calls :func:`tick_digests`
once a minute. Each user's HH:MM slots are evaluated against their local
timezone (``User.tz``) and the digest is built and sent on an exact match.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.base import session_scope
from app.db.models import Horizon, Task, User, UserSettings
from app.shared.logging import get_logger
from app.shared.time import format_due_local

logger = get_logger(__name__)

PRIORITY_ICONS: dict[str, str] = {"high": "🔴", "medium": "🟡", "low": "🟢"}


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


async def _open_tasks_for_horizon(
    session: AsyncSession,
    user_id: int,
    slug: str,
) -> list[Task]:
    """Return non-done tasks for *user_id* under the given horizon slug."""
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
            )
            .order_by(Task.created_at),  # type: ignore[arg-type]
        )
    ).all()
    return list(rows)


async def build_morning_digest(session: AsyncSession, user: User) -> str:
    """Compose the morning digest for *user*."""
    if user.id is None:
        raise RuntimeError("user.id is required for digest")
    today = await _open_tasks_for_horizon(session, user.id, "today")
    if not today:
        return "🌅 Доброе утро!\n\nНа сегодня задач не запланировано — лёгкого дня."
    lines = ["🌅 Доброе утро!", "", "Сегодня:"]
    lines.extend(_format_task_line(t, user.tz) for t in today)
    return "\n".join(lines)


async def build_evening_digest(session: AsyncSession, user: User) -> str:
    """Compose the evening digest (today's leftovers + tomorrow)."""
    if user.id is None:
        raise RuntimeError("user.id is required for digest")
    today = await _open_tasks_for_horizon(session, user.id, "today")
    tomorrow = await _open_tasks_for_horizon(session, user.id, "tomorrow")
    lines = ["🌙 Подводим итоги дня."]
    if today:
        lines.append("")
        lines.append("Осталось на сегодня:")
        lines.extend(_format_task_line(t, user.tz) for t in today)
    else:
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
                    text = await build_morning_digest(session, user)
                    settings.last_morning_digest_on = local_date
                    # Phase 6.3: pin the digest so we can re-edit it as
                    # tasks complete during the day. ``send_and_pin``
                    # falls back to a plain ``send_message`` if pinning
                    # fails (e.g. group chat where bot isn't admin).
                    from app.bot.pinned_today import send_and_pin_morning_digest

                    await send_and_pin_morning_digest(bot, session, user, settings, text)
                    sent_morning += 1
                if evening:
                    text = await build_evening_digest(session, user)
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
