"""Rendering helpers for the /reminders command + its pagination callback.

Lives in its own module so both ``app.bot.routers.commands`` (which
issues the first page) and ``app.bot.routers.callbacks`` (which serves
the ``rem:page:<offset>`` follow-ups) can share the same formatting
without a circular import — commands already imports keyboard builders
from callbacks.
"""

from __future__ import annotations

from datetime import datetime

from app.db.models import Reminder, Task
from app.shared.time import format_due_local, format_reminder_local, utcnow_naive

OVERDUE_MARKER = "❗"


def format_reminder_list(
    rows: list[tuple[Reminder, Task]],
    user_tz: str,
    *,
    now: datetime | None = None,
    total_count: int | None = None,
    page_offset: int = 0,
) -> str:
    """Render the reminder list as plain text.

    *rows* are ordered by ``fire_at`` asc. ``now`` (defaults to
    :func:`utcnow_naive`) is used to mark overdue rows. ``total_count``,
    when larger than the page, drives the "Показано N из M" footer.
    ``page_offset`` shifts the 1-based numbering so a second page
    continues from where the first ended.
    """
    if not rows:
        if page_offset > 0:
            return "⏰ Напоминания\n\nНа этой странице ничего нет."
        return "⏰ Напоминания\n\nАктивных напоминаний нет."

    cutoff = now or utcnow_naive()
    lines = ["⏰ Напоминания\n"]
    for i, (reminder, task) in enumerate(rows, page_offset + 1):
        if reminder.fire_at < cutoff:
            ts = format_reminder_local(reminder.fire_at, user_tz)
            lines.append(f"{i}. {OVERDUE_MARKER} {ts} (просрочено) — {task.title}")
        else:
            ts = format_due_local(reminder.fire_at, user_tz) or "без времени"
            lines.append(f"{i}. {ts} — {task.title}")

    shown = len(rows) + page_offset
    if total_count is not None and total_count > shown:
        lines.append(
            f"\nПоказано {shown} из {total_count}. Используй /reminders all, чтобы увидеть все."
        )
    else:
        lines.append(f"\nВсего: {shown}")
    return "\n".join(lines)
