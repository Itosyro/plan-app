"""View commands: /today, /tomorrow, /week, /month, /year, /someday, /notes, /categories.

Phase 3a: read-only commands that display tasks grouped by horizon,
notes, and category summaries.  Inline-button actions come in Phase 3b.
"""

from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from app.backup import TELEGRAM_DOCUMENT_LIMIT, build_backup, sqlite_path
from app.bot.courier_templates import (
    BACKUP_CAPTION,
    BACKUP_FAILED,
    BACKUP_FORBIDDEN,
    BACKUP_NOT_CONFIGURED,
    BACKUP_NOT_SQLITE,
    BACKUP_PRIVATE_ONLY,
    BACKUP_TOO_BIG,
    NOT_ONBOARDED,
    app_or,
)
from app.bot.reminder_view import format_reminder_list
from app.bot.routers.callbacks import horizon_list_keyboard, reminder_list_keyboard
from app.bot.services import (
    count_pending_reminders,
    get_all_notes,
    get_categories_with_counts,
    get_or_create_user,
    get_tasks_by_horizon,
    list_pending_reminders,
)
from app.db.base import session_scope
from app.db.models import Category, Note, Task
from app.shared.config import get_settings
from app.shared.logging import get_logger
from app.shared.time import format_due_local, plural_ru

# /reminders renders one page at a time. The button below the list
# loads the next page in-place via the rem:page:<offset> callback.
REMINDERS_PAGE_SIZE = 20

# /reminders all bounds the query so a runaway pending table can't
# blow past Telegram's message size limits. Anything beyond the cap
# is reported via the "Показано N из M" footer.
REMINDERS_ALL_CAP = 200

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
        # Без мини-аппа отсылать «смотри в приложении» некуда — остаётся
        # честное «столько-то не поместилось».
        where_rest = app_or(
            "Остальные — в приложении, кнопка «Открыть план» рядом с полем ввода.",
            "Остальные покажу, когда разберёшься с этими.",
        )
        lines.append(f"\nПоказано {shown} из {total_count}. {where_rest}")
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


def _format_category_list(pairs: list[tuple[Category, int]]) -> str:
    """Format categories + task counts.

    Counts go through ``plural_ru`` — the old ``{count} задач(и)``
    hedge is the kind of thing a spreadsheet writes, not a person.
    """
    if not pairs:
        return "🏷 Категории\n\nПусто — категории создаются автоматически при добавлении задач."

    lines = ["🏷 Категории\n"]
    for cat, count in pairs:
        noun = plural_ru(count, ("задача", "задачи", "задач"))
        lines.append(f"• {cat.name} — {count} {noun}")
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

        await message.answer(_format_category_list(pairs))

    @router.message(Command("reminders"))
    async def cmd_reminders(message: Message, command: CommandObject) -> None:
        """Show pending reminders with cancel buttons.

        Default form (``/reminders``) shows the first page of upcoming
        reminders, with a ``[➡️ Ещё]`` button when more pages exist.
        ``/reminders all`` drops the cutoff (so overdue rows show too)
        and renders one capped page.
        """
        if message.from_user is None:
            return

        show_all = (command.args or "").strip().lower() == "all"

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
            if show_all:
                rows = await list_pending_reminders(
                    session,
                    user.id,
                    limit=REMINDERS_ALL_CAP,
                    include_overdue=True,
                )
                total = await count_pending_reminders(
                    session,
                    user.id,
                    include_overdue=True,
                )
            else:
                rows = await list_pending_reminders(
                    session,
                    user.id,
                    limit=REMINDERS_PAGE_SIZE,
                )
                total = await count_pending_reminders(session, user.id)

        text = format_reminder_list(rows, user_tz, total_count=total)
        ids = [
            (i, reminder.id)
            for i, (reminder, _task) in enumerate(rows, 1)
            if reminder.id is not None
        ]
        # Next-page button only for the default (paginated) view.
        next_offset = (
            REMINDERS_PAGE_SIZE if (not show_all and total > REMINDERS_PAGE_SIZE) else None
        )
        if ids or next_offset is not None:
            await message.answer(
                text,
                reply_markup=reminder_list_keyboard(ids, next_offset=next_offset),
            )
        else:
            await message.answer(text)

    @router.message(Command("backup"))
    async def cmd_backup(message: Message) -> None:
        """Send the owner a ``.env`` + database archive for server migration.

        Owner-only: the archive carries the bot token and the Groq keys.
        Self-hosted (SQLite) deploys only — on a managed Postgres there
        is no file to pack.
        """
        if message.from_user is None:
            return
        if message.chat.type != "private":
            # Ответ уходит туда, откуда пришла команда: в группе архив с
            # токеном и ключами увидели бы все участники.
            await message.answer(BACKUP_PRIVATE_ONLY)
            return
        settings = get_settings()
        if settings.owner_telegram_id is None:
            await message.answer(BACKUP_NOT_CONFIGURED.format(tg_id=message.from_user.id))
            return
        if message.from_user.id != settings.owner_telegram_id:
            await message.answer(BACKUP_FORBIDDEN)
            return
        db_path = sqlite_path(settings.database_url)
        if db_path is None or not db_path.exists():
            await message.answer(BACKUP_NOT_SQLITE)
            return

        # sqlite3 + gzip держат GIL — уводим в поток, чтобы не морозить
        # приём апдейтов на время упаковки.
        try:
            filename, blob = await asyncio.to_thread(build_backup, db_path)
        except Exception as exc:
            # Молчание в ответ на команду-страховку хуже любой ошибки:
            # владелец решит, что архив ушёл, и снесёт сервер.
            logger.exception("backup.failed")
            await message.answer(BACKUP_FAILED.format(error=str(exc)[:200]))
            return
        if len(blob) > TELEGRAM_DOCUMENT_LIMIT:
            await message.answer(BACKUP_TOO_BIG.format(mb=len(blob) // (1024 * 1024)))
            return
        await message.answer_document(
            BufferedInputFile(blob, filename=filename),
            caption=BACKUP_CAPTION.format(filename=filename),
        )
        logger.info("backup.sent", size_bytes=len(blob))

    return router
