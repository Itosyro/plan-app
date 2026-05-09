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

from datetime import UTC, datetime
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
    try:
        zi = ZoneInfo(user_tz or "UTC")
    except ZoneInfoNotFoundError:
        zi = UTC
    return now_utc.astimezone(zi)


def _matches_hhmm(local_dt: datetime, hhmm: str | None) -> bool:
    """Strict ``HH:MM`` match against *local_dt* (no minute slack)."""
    if not hhmm or len(hhmm) != 5 or hhmm[2] != ":":
        return False
    try:
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
    except ValueError:
        return False
    return local_dt.hour == hh and local_dt.minute == mm


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
            .order_by(Task.created_at),  # type: ignore[union-attr]
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
            morning = _matches_hhmm(local, settings.morning_digest_at)
            evening = _matches_hhmm(local, settings.evening_digest_at)
            if not morning and not evening:
                continue
            try:
                if morning:
                    text = await build_morning_digest(session, user)
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    sent_morning += 1
                if evening:
                    text = await build_evening_digest(session, user)
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    sent_evening += 1
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
