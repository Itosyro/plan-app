"""Execute edit intents detected by ``app.ai.intent.detect_intent``.

PR-I1: complete, delete, reopen, reorder_horizon.
PR-I2: rename, set_due, set_priority, set_category, reorder_time.
PR-I3: LAST_TASK anaphora, PENDING_EDITS for multi-match I2 state,
       list_completed_today read-only intent.

Each executor receives a ``task_id`` and performs the action in its own
``session_scope``, returning a human-readable confirmation string.
The top-level ``execute_edit`` dispatches to the right executor and
handles multi-match disambiguation via inline keyboard.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlmodel import select

from app.ai.schemas import EditIntent
from app.bot.services import (
    delete_task,
    find_tasks_by_query,
    get_or_create_category,
    get_task_by_id,
    mark_task_done,
    mark_task_undone,
    update_task_category,
    update_task_due_at,
    update_task_horizon,
    update_task_priority,
    update_task_title,
)
from app.db.base import session_scope
from app.db.models import Task, TaskEvent
from app.shared.logging import get_logger

logger = get_logger(__name__)

# ── PR-I3: In-memory context stores ─────────────────────────────────

_LAST_TASK_TTL = 60  # seconds
_PENDING_EDITS_TTL = 60  # seconds

# {user_id: (task_id, monotonic_timestamp)}
LAST_TASK: dict[int, tuple[int, float]] = {}

# {user_id: (EditIntent, monotonic_timestamp)}
PENDING_EDITS: dict[int, tuple[EditIntent, float]] = {}


def touch_last_task(user_id: int, task_id: int) -> None:
    """Record the most-recently-used task for anaphora resolution."""
    LAST_TASK[user_id] = (task_id, time.monotonic())


def pop_last_task(user_id: int) -> int | None:
    """Return LAST_TASK task_id if TTL not expired, else None."""
    entry = LAST_TASK.get(user_id)
    if entry is None:
        return None
    task_id, ts = entry
    if time.monotonic() - ts > _LAST_TASK_TTL:
        LAST_TASK.pop(user_id, None)
        return None
    return task_id


def store_pending_edit(user_id: int, intent: EditIntent) -> None:
    """Save an EditIntent for later disambiguation callback."""
    PENDING_EDITS[user_id] = (intent, time.monotonic())


def pop_pending_edit(user_id: int) -> EditIntent | None:
    """Retrieve and remove the stored EditIntent if still valid."""
    entry = PENDING_EDITS.pop(user_id, None)
    if entry is None:
        return None
    intent, ts = entry
    if time.monotonic() - ts > _PENDING_EDITS_TTL:
        return None
    return intent


# Intents handled by this module.
EDIT_INTENTS_I1 = frozenset({"complete", "delete", "reopen", "reorder_horizon"})
EDIT_INTENTS_I2 = frozenset({"rename", "set_due", "set_priority", "set_category", "reorder_time"})
EDIT_INTENTS_I3_READONLY = frozenset({"list_done"})
EDIT_INTENTS_ALL = EDIT_INTENTS_I1 | EDIT_INTENTS_I2 | EDIT_INTENTS_I3_READONLY

PRIORITY_LABELS: dict[str, str] = {
    "high": "высокий",
    "medium": "средний",
    "low": "низкий",
}

HORIZON_LABELS: dict[str, str] = {
    "today": "сегодня",
    "tomorrow": "завтра",
    "week": "на эту неделю",
    "month": "на этот месяц",
    "year": "на этот год",
    "someday": "когда-нибудь",
}


def _disambiguation_keyboard(
    intent: EditIntent,
    tasks: list[Task],
) -> InlineKeyboardMarkup:
    """Build an inline keyboard for picking among multiple matching tasks."""
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks[:5]:
        if task.id is None:
            continue
        label = task.title[:40]
        cb_data = f"edit:resolve:{intent.intent}:{task.id}"
        rows.append([InlineKeyboardButton(text=label, callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _execute_complete(task_id: int, user_id: int) -> str:
    """Mark a task as done."""
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        if task.status == "done":
            return f"«{task.title}» уже отмечена как выполненная."
        await mark_task_done(session, task, user_id)
        title = task.title
    return f"Закрыл «{title}»."


async def _execute_delete(task_id: int, user_id: int) -> str:
    """Soft-delete a task."""
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        title = task.title
        await delete_task(session, task, user_id)
    return f"Удалил «{title}»."


async def _execute_reopen(task_id: int, user_id: int) -> str:
    """Re-open a previously completed task."""
    from sqlmodel import select

    async with session_scope() as session:
        # Need to find task including done ones.
        result = await session.exec(
            select(Task).where(
                Task.id == task_id,
                Task.user_id == user_id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            ),
        )
        task = result.first()
        if task is None:
            return "Задача не найдена."
        if task.status != "done":
            return f"«{task.title}» и так в активных."
        await mark_task_undone(session, task, user_id)
        title = task.title
    return f"Вернул «{title}» в активные."


async def _execute_reorder_horizon(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Move a task to a different horizon."""
    if not intent.new_horizon:
        return "Не понял, в какой горизонт перенести. Уточни: сегодня, завтра, неделя?"

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        await update_task_horizon(session, task, intent.new_horizon, user_id)
        title = task.title

    label = HORIZON_LABELS.get(intent.new_horizon, intent.new_horizon)
    return f"Перенёс «{title}» → {label}."


# ── PR-I2 executors ──────────────────────────────────────────────────


async def _execute_rename(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Rename a task."""
    if not intent.new_title:
        return "Не понял новое название. Уточни, как назвать задачу."

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        old_title = task.title
        await update_task_title(session, task, intent.new_title, user_id)

    return f"Переименовал «{old_title}» → «{intent.new_title}»."


async def _execute_set_due(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Set or change a task's due date/time."""
    import dateparser

    if not intent.new_due_raw:
        return "Не понял дату/время. Уточни: «до пятницы», «завтра в 10»."

    parsed = dateparser.parse(
        intent.new_due_raw,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if parsed is None:
        return f"Не смог разобрать дату «{intent.new_due_raw}». Попробуй иначе."

    from app.shared.time import to_naive_utc

    naive_utc = to_naive_utc(parsed)

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        await update_task_due_at(session, task, naive_utc, user_id)
        title = task.title

    formatted = parsed.strftime("%d.%m %H:%M")
    return f"Поставил дедлайн «{title}» → {formatted}."


async def _execute_set_priority(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Change a task's priority."""
    if not intent.new_priority:
        return "Не понял приоритет. Уточни: высокий, средний, низкий."

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        await update_task_priority(session, task, intent.new_priority, user_id)
        title = task.title

    label = PRIORITY_LABELS.get(intent.new_priority, intent.new_priority)
    return f"Приоритет «{title}» → {label}."


async def _execute_set_category(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Move a task to a different category."""
    if not intent.new_category:
        return "Не понял категорию. Уточни название."

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        cat = await get_or_create_category(session, user_id, intent.new_category)
        if cat.id is None:
            return "Ошибка создания категории."
        await update_task_category(session, task, cat.id, user_id)
        title = task.title

    return f"Перенёс «{title}» в категорию «{intent.new_category}»."


async def _execute_reorder_time(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Change the exact time of a task (reorder_time ≈ set_due for time changes)."""
    import dateparser

    if not intent.new_due_raw:
        return "Не понял, на какое время перенести. Уточни: «на 14:00», «на 8 утра»."

    parsed = dateparser.parse(
        intent.new_due_raw,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if parsed is None:
        return f"Не смог разобрать время «{intent.new_due_raw}». Попробуй иначе."

    from app.shared.time import to_naive_utc

    naive_utc = to_naive_utc(parsed)

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена."
        await update_task_due_at(session, task, naive_utc, user_id)
        title = task.title

    formatted = parsed.strftime("%d.%m %H:%M")
    return f"Перенёс «{title}» → {formatted}."


async def _dispatch_single(task_id: int, user_id: int, intent: EditIntent) -> str:
    """Run the appropriate executor for *one* resolved task."""
    if intent.intent == "complete":
        return await _execute_complete(task_id, user_id)
    if intent.intent == "delete":
        return await _execute_delete(task_id, user_id)
    if intent.intent == "reopen":
        return await _execute_reopen(task_id, user_id)
    if intent.intent == "reorder_horizon":
        return await _execute_reorder_horizon(task_id, user_id, intent)
    if intent.intent == "rename":
        return await _execute_rename(task_id, user_id, intent)
    if intent.intent == "set_due":
        return await _execute_set_due(task_id, user_id, intent)
    if intent.intent == "set_priority":
        return await _execute_set_priority(task_id, user_id, intent)
    if intent.intent == "set_category":
        return await _execute_set_category(task_id, user_id, intent)
    if intent.intent == "reorder_time":
        return await _execute_reorder_time(task_id, user_id, intent)
    return f"Действие «{intent.intent}» пока не поддерживается — скоро добавлю."


async def _execute_list_completed_today(
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Return a list of tasks completed today (read-only)."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    async with session_scope() as session:
        stmt = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status == "done",
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .join(
                TaskEvent,
                (TaskEvent.task_id == Task.id) & (TaskEvent.kind == "completed"),  # type: ignore[arg-type]
            )
            .where(TaskEvent.created_at >= today_start)
        )
        result = await session.exec(stmt)
        tasks = list(result.all())

    if not tasks:
        return "Сегодня пока ничего не завершено.", None

    lines = [f"Сегодня завершено ({len(tasks)}):"]
    for t in tasks:
        lines.append(f"  • {t.title}")
    return "\n".join(lines), None


async def execute_edit(
    intent: EditIntent,
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Dispatch an edit intent: find the task, handle ambiguity, execute.

    Returns ``(reply_text, keyboard_or_none)``.
    """
    query = (intent.task_query or "").strip()

    # PR-I3: list_completed_today is read-only, no task lookup needed.
    if intent.intent == "list_done":
        return await _execute_list_completed_today(user_id)

    # For reopen, search among completed tasks too.
    include_done = intent.intent == "reopen"

    if not query:
        # PR-I3: LAST_TASK anaphora — fallback when query is empty.
        last_id = pop_last_task(user_id)
        if last_id is not None:
            logger.info("edit.anaphora", user_id=user_id, task_id=last_id)
            reply = await _dispatch_single(last_id, user_id, intent)
            touch_last_task(user_id, last_id)
            return reply, None
        return (
            "Не понял, какую задачу ты имеешь в виду. Уточни название.",
            None,
        )

    async with session_scope() as session:
        matches = await find_tasks_by_query(
            session,
            user_id,
            query,
            include_done=include_done,
        )

    if not matches:
        return (
            f"Не нашёл задачу «{query}». Может, она уже удалена или ты её по-другому называл?",
            None,
        )

    if len(matches) > 1:
        # PR-I3: store intent for disambiguation callback (I2 intents need extra fields).
        store_pending_edit(user_id, intent)
        keyboard = _disambiguation_keyboard(intent, matches)
        return (
            f"Нашёл несколько подходящих задач по запросу «{query}», уточни какую:",
            keyboard,
        )

    task = matches[0]
    if task.id is None:
        return "Ошибка: задача без ID.", None

    reply = await _dispatch_single(task.id, user_id, intent)

    if task.id is not None:
        touch_last_task(user_id, task.id)

    logger.info(
        "edit.executed",
        intent=intent.intent,
        task_id=task.id,
        user_id=user_id,
    )
    return reply, None
