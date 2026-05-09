"""Cron tick: deliver due reminders, send daily digests (Phase 4b).

Render's worker service invokes ``python -m app.workers.scheduler`` once per
minute; each invocation processes a single batch and exits. Reminders flip
from ``pending`` → ``sent``/``failed`` immediately so the next tick won't
double-send. Digests are dispatched only when the user's *local* HH:MM
exactly matches their ``UserSettings`` slots.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from sqlmodel import select

from app.bot.digest import tick_digests
from app.db.base import dispose_engine, init_engine, session_scope
from app.db.models import Reminder, Task, User
from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger
from app.shared.time import format_due_local, utcnow_naive

logger = get_logger(__name__)

MAX_REMINDER_ATTEMPTS = 3
REMINDER_BATCH_SIZE = 100


def _format_reminder(task: Task, user_tz: str) -> str:
    """Build the Telegram body for one reminder.

    ``task.due_at`` is naive UTC (see ``app/shared/time.py``); render it
    in *user_tz* so the user sees their own clock-time, not UTC.
    """
    if task.due_at is not None:
        local = format_due_local(task.due_at, user_tz)
        if local is not None:
            return f"⏰ Напоминаю: {task.title} — в {local}."
    return f"⏰ Напоминаю: {task.title}"


async def tick_reminders(
    bot: Bot,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send pending reminders whose ``fire_at`` has passed.

    On a successful Telegram call the row flips to ``sent`` and ``sent_at``
    is stamped. On any error ``attempts`` is bumped and ``last_error`` is
    captured; once ``attempts`` reaches :data:`MAX_REMINDER_ATTEMPTS` the row
    is marked ``failed`` and excluded from future ticks.
    """
    cutoff = now if now is not None else utcnow_naive()
    sent = retry = failed = 0

    async with session_scope() as session:
        rows = list(
            (
                await session.exec(
                    select(Reminder, Task, User)
                    .join(Task, Task.id == Reminder.task_id)  # type: ignore[arg-type]
                    .join(User, User.id == Reminder.user_id)  # type: ignore[arg-type]
                    .where(Reminder.status == "pending")
                    .where(Reminder.fire_at <= cutoff)
                    .order_by(Reminder.fire_at)  # type: ignore[arg-type]
                    .limit(REMINDER_BATCH_SIZE),
                )
            ).all(),
        )

        for reminder, task, user in rows:
            try:
                text = _format_reminder(task, user.tz)
                await bot.send_message(chat_id=user.telegram_id, text=text)
            except Exception as exc:
                reminder.attempts += 1
                reminder.last_error = str(exc)[:512]
                if reminder.attempts >= MAX_REMINDER_ATTEMPTS:
                    reminder.status = "failed"
                    failed += 1
                else:
                    retry += 1
                logger.warning(
                    "reminder.send_failed",
                    reminder_id=reminder.id,
                    attempts=reminder.attempts,
                    error=str(exc)[:200],
                )
            else:
                reminder.status = "sent"
                reminder.sent_at = utcnow_naive()
                reminder.last_error = None
                sent += 1
            session.add(reminder)

    if sent or retry or failed:
        logger.info("reminders.tick", sent=sent, retry=retry, failed=failed)
    return {"sent": sent, "retry": retry, "failed": failed}


async def main_async() -> int:
    """Entrypoint coroutine for the cron worker."""
    configure_logging()
    settings = get_settings()
    if not settings.database_url:
        logger.warning("scheduler.no_db_url")
        return 1
    if not settings.telegram_bot_token:
        logger.warning("scheduler.no_bot_token")
        return 1
    init_engine(settings.database_url)
    bot = Bot(token=settings.telegram_bot_token)
    try:
        rem = await tick_reminders(bot)
        dig = await tick_digests(bot)
        logger.info("scheduler.done", reminders=rem, digests=dig)
    finally:
        await bot.session.close()
        await dispose_engine()
    return 0


def main() -> int:
    """Sync entrypoint for ``python -m app.workers.scheduler``."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
