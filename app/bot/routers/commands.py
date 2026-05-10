"""View + quick-input commands.

Phase 3a: read-only commands that display tasks grouped by horizon,
notes, and category summaries.  Inline-button actions come in Phase 3b.
Phase 8b adds quick-input commands so users can manage tasks without
opening the Mini-App or relying on the AI pipeline:

* ``/add <text>``               — push *text* through the full pipeline.
* ``/done <query>``             — mark the most recent matching task done.
* ``/del <query>``              — delete the most recent matching task.
* ``/move <query> <horizon>``   — move the matching task to *horizon*.
* ``/postpone <query> <horizon>`` — alias of ``/move`` (separate verb the
  user already learned in chat — kept as a soft-synonym).

The lookup is case-insensitive substring match against ``Task.title``
(see ``find_task_by_query``). When nothing matches we tell the user
plainly — no AI fallback, slash commands are deterministic by design.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.bot.courier_templates import NOT_ONBOARDED
from app.bot.routers._pipeline import enqueue_text_pipeline
from app.bot.routers.callbacks import horizon_list_keyboard
from app.bot.services import (
    delete_task,
    find_task_by_query,
    get_all_notes,
    get_categories_with_counts,
    get_or_create_user,
    get_tasks_by_horizon,
    mark_task_done,
    update_task_horizon,
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

# Single-token aliases for ``/move`` / ``/postpone``. Multi-word
# Russian variants like "на этой неделе" are intentionally not
# accepted — the parser treats the LAST whitespace-separated token
# as the horizon, so an alias must fit in one word for unambiguous
# splitting against the query (which itself is free-form).
HORIZON_ALIASES: dict[str, str] = {
    # English (canonical slugs)
    "today": "today",
    "tomorrow": "tomorrow",
    "week": "week",
    "month": "month",
    "year": "year",
    "someday": "someday",
    # Russian — most natural single-word forms
    "сегодня": "today",
    "завтра": "tomorrow",
    "неделя": "week",
    "неделю": "week",
    "месяц": "month",
    "год": "year",
    "когда-нибудь": "someday",
    "потом": "someday",
}

# Russian labels for confirmation replies. Mirrors the table in
# ``_pipeline._try_reorder`` so messaging stays consistent across
# AI- and command-driven moves.
HORIZON_LABELS: dict[str, str] = {
    "today": "сегодня",
    "tomorrow": "завтра",
    "week": "на эту неделю",
    "month": "на этот месяц",
    "year": "на этот год",
    "someday": "когда-нибудь",
}


def parse_horizon(value: str) -> str | None:
    """Resolve a user-typed horizon token to a canonical slug, or ``None``.

    Case-insensitive. See ``HORIZON_ALIASES`` for the supported forms.
    """
    return HORIZON_ALIASES.get(value.strip().lower())


def parse_move_args(args: str | None) -> tuple[str, str] | None:
    """Split ``/move`` arguments into ``(query, horizon_slug)``.

    The horizon is always the last whitespace-separated token, so a
    multi-word query is fine: ``/move купить хлеб завтра`` →
    ``("купить хлеб", "tomorrow")``. Returns ``None`` when *args*
    has fewer than two tokens or the trailing token is not a known
    horizon alias.
    """
    if not args:
        return None
    parts = args.strip().split()
    if len(parts) < 2:
        return None
    horizon = parse_horizon(parts[-1])
    if horizon is None:
        return None
    query = " ".join(parts[:-1]).strip()
    if not query:
        return None
    return query, horizon


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

    # ── Phase 8b: quick-input commands ───────────────────────────────

    async def _ensure_onboarded(message: Message) -> int | None:
        """Return ``user.id`` for an onboarded sender, else reply + ``None``.

        Centralised so every quick-input command can short-circuit at
        the top with the same NOT_ONBOARDED nudge.
        """
        if message.from_user is None:
            return None
        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                lang_code=message.from_user.language_code,
            )
            if user.onboarded_at is None:
                await message.answer(NOT_ONBOARDED)
                return None
            return user.id

    @router.message(Command("add"))
    async def cmd_add(message: Message, command: CommandObject) -> None:
        """Push command arguments through the AI pipeline.

        Identical UX to a free-form text message: store in inbox,
        reaction ack, ⏳ placeholder, streamed reply. Useful when the
        user wants the bot to ignore everything *before* the command
        word — e.g. ``/add 5km утром, отчёт в пятницу``.
        """
        if message.from_user is None:
            return
        text = (command.args or "").strip()
        if not text:
            await message.answer("Использование: /add <текст задачи или мысль>")
            return
        await enqueue_text_pipeline(message, text)

    @router.message(Command("done"))
    async def cmd_done(message: Message, command: CommandObject) -> None:
        """Mark the most recent task matching *query* as done."""
        user_id = await _ensure_onboarded(message)
        if user_id is None:
            return
        query = (command.args or "").strip()
        if not query:
            await message.answer("Использование: /done <часть названия задачи>")
            return

        async with session_scope() as session:
            task = await find_task_by_query(session, user_id, query)
            if task is None:
                await message.answer(f"Не нашёл задачу «{query}».")
                return
            await mark_task_done(session, task, user_id)
            title = task.title

        await message.answer(f"✅ {title}")

    @router.message(Command("del"))
    async def cmd_del(message: Message, command: CommandObject) -> None:
        """Delete the most recent task matching *query*."""
        user_id = await _ensure_onboarded(message)
        if user_id is None:
            return
        query = (command.args or "").strip()
        if not query:
            await message.answer("Использование: /del <часть названия задачи>")
            return

        async with session_scope() as session:
            task = await find_task_by_query(session, user_id, query)
            if task is None:
                await message.answer(f"Не нашёл задачу «{query}».")
                return
            title = task.title
            await delete_task(session, task, user_id)

        await message.answer(f"🗑 Удалил «{title}».")

    async def _handle_move(
        message: Message,
        command: CommandObject,
        *,
        usage_verb: str,
    ) -> None:
        """Shared body for ``/move`` and ``/postpone``.

        ``usage_verb`` is interpolated into the help string so each
        command shows its own name when the user passes bad args.
        """
        user_id = await _ensure_onboarded(message)
        if user_id is None:
            return
        parsed = parse_move_args(command.args)
        if parsed is None:
            aliases = ", ".join(sorted(HORIZON_ALIASES))
            await message.answer(
                f"Использование: /{usage_verb} <часть названия> <горизонт>\n\nГоризонты: {aliases}",
            )
            return
        query, horizon_slug = parsed

        async with session_scope() as session:
            task = await find_task_by_query(session, user_id, query)
            if task is None:
                await message.answer(f"Не нашёл задачу «{query}».")
                return
            await update_task_horizon(session, task, horizon_slug, user_id)
            title = task.title

        label = HORIZON_LABELS.get(horizon_slug, horizon_slug)
        await message.answer(f"✅ Перенёс «{title}» → {label}.")

    @router.message(Command("move"))
    async def cmd_move(message: Message, command: CommandObject) -> None:
        await _handle_move(message, command, usage_verb="move")

    @router.message(Command("postpone"))
    async def cmd_postpone(message: Message, command: CommandObject) -> None:
        await _handle_move(message, command, usage_verb="postpone")

    return router
