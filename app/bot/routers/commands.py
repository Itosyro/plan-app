"""View commands: /today, /tomorrow, /week, /month, /year, /someday, /notes, /categories.

Phase 3a: read-only commands that display tasks grouped by horizon,
notes, and category summaries.  Inline-button actions come in Phase 3b.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.routers.callbacks import horizon_list_keyboard
from app.bot.services import (
    get_all_notes,
    get_categories_with_counts,
    get_or_create_user,
    get_tasks_by_horizon,
)
from app.db.base import session_scope
from app.db.models import Note, Task
from app.shared.logging import get_logger
from app.shared.time import format_due_local

# Cap the number of tasks shown per /today-like command. With four
# action buttons per row, 25 tasks fills 100 inline-keyboard buttons,
# Telegram's hard limit. We pick a tighter cap so the overflow note
# is rare-but-helpful and the keyboard stays readable on mobile. See
# docs/REVIEW-2026-05-09-v2.md::R-NEW-I-6.
HORIZON_PAGE_SIZE = 20

logger = get_logger(__name__)

HORIZON_TITLES: dict[str, str] = {
    "today": "Сегодня",
    "tomorrow": "Завтра",
    "week": "На этой неделе",
    "month": "В этом месяце",
    "year": "В этом году",
    "someday": "Когда-нибудь",
}

PRIORITY_ICONS: dict[str, str] = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
}


def _format_task_list(
    tasks: list[Task],
    title: str,
    user_tz: str,
    *,
    total_count: int | None = None,
) -> str:
    """Format a list of tasks into a readable plain-text message.

    Plain text only — ``parse_mode`` is intentionally **not** set on send,
    because ``task.title`` is user-controlled and routinely contains
    Markdown-active characters (``*``, ``_``, ``[``) that would break
    Telegram's parser. See ``docs/REVIEW-findings.md::C-2``.

    ``task.due_at`` is naive UTC; rendered in *user_tz* so the user sees
    their own clock-time. See ``docs/REVIEW-2026-05-09.md::C-2``.

    ``total_count`` is the unfiltered task count for the horizon. When
    larger than ``len(tasks)``, the message includes an overflow line
    so the user knows there are more tasks than rendered (paged out
    by ``HORIZON_PAGE_SIZE``). See R-NEW-I-6.
    """
    if not tasks:
        return f"📋 {title}\n\nПусто — ни одной задачи."

    lines = [f"📋 {title}\n"]
    for i, task in enumerate(tasks, 1):
        icon = PRIORITY_ICONS.get(task.priority, "⚪")
        due_part = ""
        if task.due_at is not None:
            local = format_due_local(task.due_at, user_tz)
            if local is not None:
                due_part = f" · {local}"
        lines.append(f"{i}. {icon} {task.title}{due_part}")

    shown = len(tasks)
    if total_count is not None and total_count > shown:
        lines.append(
            f"\nПоказано {shown} из {total_count}. "
            "Используй /search или фильтр по категории, чтобы найти остальные."
        )
    else:
        lines.append(f"\nВсего: {shown}")
    return "\n".join(lines)


def _format_note_list(notes: list[Note]) -> str:
    """Format a list of notes into a readable plain-text message.

    Same plain-text rationale as ``_format_task_list``.
    """
    if not notes:
        return "📝 Заметки\n\nПусто — ни одной заметки."

    lines = ["📝 Заметки\n"]
    for i, note in enumerate(notes, 1):
        lines.append(f"{i}. {note.title}")

    lines.append(f"\nВсего: {len(notes)}")
    return "\n".join(lines)


def create_router() -> Router:
    """Build a fresh ``commands`` router with view handlers."""
    router = Router(name="commands")

    async def _horizon_handler(message: Message, slug: str) -> None:
        """Generic handler for horizon-based commands.

        Sends *one* message per call: the formatted task list with a
        single compact action keyboard listing all visible tasks.
        Replaces the previous N+1 message blast (1 summary + N
        per-task messages with their own keyboards). See
        ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-6``.
        """
        if message.from_user is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            if user.id is None:
                return
            user_tz = user.tz
            all_tasks = await get_tasks_by_horizon(session, user.id, slug)

        title = HORIZON_TITLES.get(slug, slug)
        if not all_tasks:
            await message.answer(_format_task_list(all_tasks, title, user_tz))
            return

        # Cap the visible page so the inline keyboard stays under
        # Telegram's 100-button limit and the message is readable.
        visible = all_tasks[:HORIZON_PAGE_SIZE]
        text = _format_task_list(visible, title, user_tz, total_count=len(all_tasks))
        indices = [(i, t.id) for i, t in enumerate(visible, 1) if t.id is not None]
        if indices:
            await message.answer(text, reply_markup=horizon_list_keyboard(indices))
        else:
            await message.answer(text)

    @router.message(Command("today"))
    async def cmd_today(message: Message) -> None:
        await _horizon_handler(message, "today")

    @router.message(Command("tomorrow"))
    async def cmd_tomorrow(message: Message) -> None:
        await _horizon_handler(message, "tomorrow")

    @router.message(Command("week"))
    async def cmd_week(message: Message) -> None:
        await _horizon_handler(message, "week")

    @router.message(Command("month"))
    async def cmd_month(message: Message) -> None:
        await _horizon_handler(message, "month")

    @router.message(Command("year"))
    async def cmd_year(message: Message) -> None:
        await _horizon_handler(message, "year")

    @router.message(Command("someday"))
    async def cmd_someday(message: Message) -> None:
        await _horizon_handler(message, "someday")

    @router.message(Command("notes"))
    async def cmd_notes(message: Message) -> None:
        """Show the most recent notes."""
        if message.from_user is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            if user.id is None:
                return
            notes = await get_all_notes(session, user.id)

        await message.answer(_format_note_list(notes))

    @router.message(Command("categories"))
    async def cmd_categories(message: Message) -> None:
        """Show all categories with task counts."""
        if message.from_user is None:
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return
            if user.id is None:
                return
            pairs = await get_categories_with_counts(session, user.id)

        if not pairs:
            await message.answer(
                "🏷 Категории\n\nПусто — категории создаются автоматически при добавлении задач.",
            )
            return

        lines = ["🏷 Категории\n"]
        for cat, count in pairs:
            lines.append(f"• {cat.name} — {count} задач(и)")
        await message.answer("\n".join(lines))

    return router
