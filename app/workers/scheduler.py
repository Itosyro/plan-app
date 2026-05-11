"""Cron tick: deliver due reminders, send daily digests (Phase 4b).

Render's worker service invokes ``python -m app.workers.scheduler`` once per
minute; each invocation processes a single batch and exits. Reminders flip
from ``pending`` → ``processing`` (atomic claim) → ``sent``/``failed``
with a commit after every Telegram round-trip, so a crash mid-batch
can never produce duplicate sends on the next tick. Digests are
dispatched only when the user's *local* HH:MM exactly matches their
``UserSettings`` slots (with catch-up for delayed ticks; see
``app/bot/digest.py``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlmodel import select

from app.bot.digest import tick_digests
from app.db.base import dispose_engine, init_engine, session_scope
from app.db.models import Note, Reminder, Task, User
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

    Each row goes through a three-step state machine to make the tick
    crash-safe under SIGTERM / OOM (see
    ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-5``):

    1. **Claim** — atomic ``UPDATE … SET status='processing' WHERE
       status='pending' AND id=:id``. If the rowcount is 0 the row was
       claimed by another worker (or its status changed) — skip. The
       claim is committed *before* the Telegram call.
    2. **Send** — call ``bot.send_message``; on success flip
       ``status='sent'`` (with ``sent_at`` stamped), on failure bump
       ``attempts`` and either flip ``status='failed'`` (after
       :data:`MAX_REMINDER_ATTEMPTS`) or revert ``status='pending'``
       so the next tick can retry. Each terminal state is committed
       in its own transaction so a crash after the Telegram call
       can't lose the state-flip and trigger a duplicate send next
       tick.
    3. **Stuck rows** — if a worker is killed between claim and
       state-flip, the row is left in ``status='processing'`` and a
       human cleanup is required. We deliberately don't auto-revert
       (we can't tell whether Telegram delivered the message).
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
                    .where(Task.deleted_at.is_(None))  # type: ignore[union-attr]
                    .order_by(Reminder.fire_at)  # type: ignore[arg-type]
                    .limit(REMINDER_BATCH_SIZE),
                )
            ).all(),
        )

        for reminder, task, user in rows:
            assert reminder.id is not None  # SELECT-loaded → never NULL
            # ── 1. Claim the row atomically ────────────────────────
            claim_result = await session.execute(
                update(Reminder)
                .where(
                    Reminder.id == reminder.id,  # type: ignore[arg-type]
                    Reminder.status == "pending",  # type: ignore[arg-type]
                )
                .values(status="processing"),
            )
            await session.commit()
            # ``execute`` of an ``UPDATE`` always returns a CursorResult;
            # the runtime check on the union return type is impossible
            # without `cast` because mypy widens it to ``Result[Any]``.
            assert isinstance(claim_result, CursorResult)
            if claim_result.rowcount != 1:
                # Another worker beat us to it — skip silently.
                continue
            reminder.status = "processing"

            # ── 2. Send + terminal state flip ──────────────────────
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
                    # Revert to pending so the next tick retries; we
                    # can't leave it in 'processing' or it'd be stuck.
                    reminder.status = "pending"
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
            # Commit per-row so a crash on the *next* row can't roll
            # back this row's terminal state and re-send next tick.
            await session.commit()

    if sent or retry or failed:
        logger.info("reminders.tick", sent=sent, retry=retry, failed=failed)
    return {"sent": sent, "retry": retry, "failed": failed}


TRASH_RETENTION_HOURS = 24
PURGE_BATCH_SIZE = 200


async def purge_trash(*, now: datetime | None = None) -> dict[str, int]:
    """Permanently delete soft-deleted records older than 24 hours.

    Tasks are deleted via ``session.delete`` so the FK CASCADE
    on ``reminders`` and ``task_events`` cleans up dependents.
    """
    cutoff = (now if now is not None else utcnow_naive()) - timedelta(hours=TRASH_RETENTION_HOURS)
    purged_tasks = 0
    purged_notes = 0

    async with session_scope() as session:
        stale_tasks = list(
            (
                await session.exec(
                    select(Task)
                    .where(
                        Task.deleted_at.is_not(None),  # type: ignore[union-attr]
                        Task.deleted_at <= cutoff,  # type: ignore[operator]
                    )
                    .limit(PURGE_BATCH_SIZE)
                )
            ).all()
        )
        for task in stale_tasks:
            await session.delete(task)
            purged_tasks += 1
        if stale_tasks:
            await session.flush()

        stale_notes = list(
            (
                await session.exec(
                    select(Note)
                    .where(
                        Note.deleted_at.is_not(None),  # type: ignore[union-attr]
                        Note.deleted_at <= cutoff,  # type: ignore[operator]
                    )
                    .limit(PURGE_BATCH_SIZE)
                )
            ).all()
        )
        for note in stale_notes:
            await session.delete(note)
            purged_notes += 1
        if stale_notes:
            await session.flush()

    if purged_tasks or purged_notes:
        logger.info("trash.purged", tasks=purged_tasks, notes=purged_notes)
    return {"tasks": purged_tasks, "notes": purged_notes}


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
        trash = await purge_trash()
        logger.info("scheduler.done", reminders=rem, digests=dig, trash=trash)
    finally:
        await bot.session.close()
        await dispose_engine()
    return 0


def main() -> int:
    """Sync entrypoint for ``python -m app.workers.scheduler``."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
