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
    cancel_task_reminders,
    delete_category,
    delete_task,
    find_category_by_name,
    find_tasks_by_query,
    get_or_create_category,
    get_task_by_id,
    mark_task_done,
    mark_task_undone,
    rename_category,
    update_task_category,
    update_task_due_at,
    update_task_horizon,
    update_task_priority,
    update_task_title,
)
from app.db.base import session_scope
from app.db.models import Category, Task, TaskEditSnapshot, TaskEvent, User
from app.shared.logging import get_logger
from app.shared.time import format_reminder_local, plural_ru

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
EDIT_INTENTS_I4_REMINDERS = frozenset({"cancel_reminder"})
EDIT_INTENTS_CATEGORY = frozenset({"create_category", "rename_category", "delete_category"})
EDIT_INTENTS_ALL = (
    EDIT_INTENTS_I1
    | EDIT_INTENTS_I2
    | EDIT_INTENTS_I3_READONLY
    | EDIT_INTENTS_I4_REMINDERS
    | EDIT_INTENTS_CATEGORY
)

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


def _delete_confirm_keyboard(task_id: int, title: str) -> InlineKeyboardMarkup:
    """Build a two-step confirm/cancel keyboard for an LLM-detected delete.

    G3 / Excessive-Agency mitigation: when a ``delete`` intent is parsed
    from *free user text* (where a prompt-injection could coerce the
    model into emitting ``delete``), we never soft-delete immediately.
    Instead we surface this keyboard; the task is only soft-deleted when
    the user taps confirm (``edit:deldo:<id>``). The explicit 🗑 inline
    button (``task:delete:<id>``) is a deliberate tap and stays immediate.
    """
    label = title[:40]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Да, удалить «{label}»",
                    callback_data=f"edit:deldo:{task_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"edit:delno:{task_id}",
                ),
            ],
        ]
    )


_UNDO_TTL_SECONDS = 300  # 5 minutes


async def _save_snapshot(
    task_id: int,
    user_id: int,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> int | None:
    """Persist a TaskEditSnapshot and return its id."""
    async with session_scope() as session:
        snap = TaskEditSnapshot(
            task_id=task_id,
            user_id=user_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
        )
        session.add(snap)
        await session.flush()
        return snap.id


def _undo_keyboard(snapshot_id: int) -> InlineKeyboardMarkup:
    """Build a single-button [Отменить] inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=f"edit:undo:{snapshot_id}",
                )
            ]
        ]
    )


async def _execute_complete(task_id: int, user_id: int) -> tuple[str, int | None]:
    """Mark a task as done."""
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        if task.status == "done":
            return f"«{task.title}» уже отмечена как выполненная.", None
        old_status = task.status
        await mark_task_done(session, task, user_id)
        title = task.title
    snap_id = await _save_snapshot(task_id, user_id, "status", old_status, "done")
    return f"Закрыл «{title}».", snap_id


async def _execute_delete(task_id: int, user_id: int) -> tuple[str, int | None]:
    """Soft-delete a task."""
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        title = task.title
        await delete_task(session, task, user_id)
    snap_id = await _save_snapshot(task_id, user_id, "deleted_at", None, "soft_deleted")
    return f"Удалил «{title}».", snap_id


async def _execute_reopen(task_id: int, user_id: int) -> tuple[str, int | None]:
    """Re-open a previously completed task."""
    from sqlmodel import select

    async with session_scope() as session:
        result = await session.exec(
            select(Task).where(
                Task.id == task_id,
                Task.user_id == user_id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            ),
        )
        task = result.first()
        if task is None:
            return "Задача не найдена.", None
        if task.status != "done":
            return f"«{task.title}» и так в активных.", None
        await mark_task_undone(session, task, user_id)
        title = task.title
    snap_id = await _save_snapshot(task_id, user_id, "status", "done", "open")
    return f"Вернул «{title}» в активные.", snap_id


async def _execute_reorder_horizon(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Move a task to a different horizon."""
    if not intent.new_horizon:
        return "Не понял, в какой горизонт перенести. Уточни: сегодня, завтра, неделя?", None

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_horizon = str(task.horizon_id) if task.horizon_id else None
        await update_task_horizon(session, task, intent.new_horizon, user_id)
        title = task.title
        new_horizon = str(task.horizon_id) if task.horizon_id else None

    label = HORIZON_LABELS.get(intent.new_horizon, intent.new_horizon)
    snap_id = await _save_snapshot(task_id, user_id, "horizon_id", old_horizon, new_horizon)
    return f"Перенёс «{title}» → {label}.", snap_id


# ── PR-I2 executors ──────────────────────────────────────────────────


async def _execute_rename(task_id: int, user_id: int, intent: EditIntent) -> tuple[str, int | None]:
    """Rename a task."""
    if not intent.new_title:
        return "Не понял новое название. Уточни, как назвать задачу.", None

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_title = task.title
        await update_task_title(session, task, intent.new_title, user_id)

    snap_id = await _save_snapshot(task_id, user_id, "title", old_title, intent.new_title)
    return f"Переименовал «{old_title}» → «{intent.new_title}».", snap_id


async def _execute_set_due(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Set or change a task's due date/time."""
    import dateparser

    if not intent.new_due_raw:
        return "Не понял дату/время. Уточни: «до пятницы», «завтра в 10».", None

    parsed = dateparser.parse(
        intent.new_due_raw,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if parsed is None:
        return f"Не смог разобрать дату «{intent.new_due_raw}». Попробуй иначе.", None

    from app.shared.time import to_naive_utc

    naive_utc = to_naive_utc(parsed)

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_due = task.due_at.isoformat() if task.due_at else None
        await update_task_due_at(session, task, naive_utc, user_id)
        title = task.title

    formatted = parsed.strftime("%d.%m %H:%M")
    snap_id = await _save_snapshot(task_id, user_id, "due_at", old_due, naive_utc.isoformat())
    return f"Поставил дедлайн «{title}» → {formatted}.", snap_id


async def _execute_set_priority(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Change a task's priority."""
    if not intent.new_priority:
        return "Не понял приоритет. Уточни: высокий, средний, низкий.", None

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_priority = task.priority
        await update_task_priority(session, task, intent.new_priority, user_id)
        title = task.title

    label = PRIORITY_LABELS.get(intent.new_priority, intent.new_priority)
    snap_id = await _save_snapshot(task_id, user_id, "priority", old_priority, intent.new_priority)
    return f"Приоритет «{title}» → {label}.", snap_id


async def _execute_set_category(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Move a task to a different category."""
    if not intent.new_category:
        return "Не понял категорию. Уточни название.", None

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_cat_id = str(task.category_id) if task.category_id else None
        cat = await get_or_create_category(session, user_id, intent.new_category)
        if cat.id is None:
            return "Ошибка создания категории.", None
        await update_task_category(session, task, cat.id, user_id)
        title = task.title

    snap_id = await _save_snapshot(task_id, user_id, "category_id", old_cat_id, str(cat.id))
    return f"Перенёс «{title}» в категорию «{intent.new_category}».", snap_id


async def _execute_reorder_time(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Change the exact time of a task (reorder_time ≈ set_due for time changes)."""
    import dateparser

    if not intent.new_due_raw:
        return "Не понял, на какое время перенести. Уточни: «на 14:00», «на 8 утра».", None

    parsed = dateparser.parse(
        intent.new_due_raw,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if parsed is None:
        return f"Не смог разобрать время «{intent.new_due_raw}». Попробуй иначе.", None

    from app.shared.time import to_naive_utc

    naive_utc = to_naive_utc(parsed)

    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        old_due = task.due_at.isoformat() if task.due_at else None
        await update_task_due_at(session, task, naive_utc, user_id)
        title = task.title

    formatted = parsed.strftime("%d.%m %H:%M")
    snap_id = await _save_snapshot(task_id, user_id, "due_at", old_due, naive_utc.isoformat())
    return f"Перенёс «{title}» → {formatted}.", snap_id


async def _execute_cancel_reminder(task_id: int, user_id: int) -> tuple[str, int | None]:
    """Cancel pending reminders for a task without mutating the task itself.

    Reply lists *when* each cancelled reminder was scheduled in the
    user's local tz so they can sanity-check the action — a bare count
    ("отменил 3") doesn't tell them which 3.
    """
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        title = task.title
        user_row = (await session.exec(select(User).where(User.id == user_id))).first()
        user_tz = user_row.tz if user_row is not None else "UTC"
        cancelled = await cancel_task_reminders(session, user_id, task_id)
    if not cancelled:
        return f"У «{title}» нет активных напоминаний.", None
    times = ", ".join(format_reminder_local(r.fire_at, user_tz) for r in cancelled)
    n = len(cancelled)
    noun = plural_ru(n, ("напоминание", "напоминания", "напоминаний"))
    return f"Отменил {n} {noun} для «{title}»: {times}.", None


# ── Category management (voice/text) ─────────────────────────────────


def _category_delete_confirm_keyboard(category_id: int, name: str) -> InlineKeyboardMarkup:
    """Two-step confirm/cancel keyboard for deleting a whole category.

    Deleting a category detaches every task/note in it, so — like the
    free-text task delete — we never act on the model's say-so alone.
    """
    label = name[:40]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Да, удалить «{label}»",
                    callback_data=f"edit:catdo:{category_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"edit:catno:{category_id}",
                ),
            ],
        ]
    )


async def _execute_create_category(user_id: int, intent: EditIntent) -> str:
    """Create a new empty category (no task involved)."""
    name = (intent.new_category or "").strip()
    if not name:
        return "Не понял название категории. Уточни, как её назвать."
    async with session_scope() as session:
        existing = await find_category_by_name(session, user_id, name)
        if existing is not None:
            return f"Категория «{existing.name}» уже есть."
        await get_or_create_category(session, user_id, name)
    return f"Создал категорию «{name}»."


async def _execute_rename_category(user_id: int, intent: EditIntent) -> str:
    """Rename an existing category."""
    old = (intent.category_query or "").strip()
    new = (intent.new_category or "").strip()
    if not old or not new:
        return "Не понял, что переименовать. Пример: «переименуй категорию Работа в Дела»."
    async with session_scope() as session:
        cat = await find_category_by_name(session, user_id, old)
        if cat is None:
            return f"Не нашёл категорию «{old}»."
        clash = await find_category_by_name(session, user_id, new)
        if clash is not None and clash.id != cat.id:
            return f"Категория «{clash.name}» уже есть — выбери другое имя."
        old_name = cat.name
        await rename_category(session, cat, new)
    return f"Переименовал категорию «{old_name}» → «{new}»."


async def _category_delete_confirmation(
    user_id: int, intent: EditIntent
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Surface a confirm/cancel prompt for a free-text delete_category."""
    name = (intent.category_query or "").strip()
    if not name:
        return "Не понял, какую категорию удалить. Пример: «удали категорию Финансы».", None
    async with session_scope() as session:
        cat = await find_category_by_name(session, user_id, name)
        if cat is None:
            return f"Не нашёл категорию «{name}».", None
        if cat.id is None:
            return "Ошибка: категория без ID.", None
        cat_id, cat_name = cat.id, cat.name
    prompt = f"Удалить категорию «{cat_name}»? Задачи из неё станут без категории."
    return prompt, _category_delete_confirm_keyboard(cat_id, cat_name)


async def execute_delete_category(user_id: int, category_id: int) -> str:
    """Delete a category after the user confirmed (callback path)."""
    async with session_scope() as session:
        cat = (
            await session.exec(
                select(Category).where(
                    Category.id == category_id,
                    Category.user_id == user_id,
                ),
            )
        ).first()
        if cat is None:
            return "Категория не найдена."
        name = cat.name
        affected = await delete_category(session, cat)
    if affected:
        noun = plural_ru(affected, ("задачу", "задачи", "задач"))
        return f"Удалил категорию «{name}». {affected} {noun} перенёс в «Без категории»."
    return f"Удалил категорию «{name}»."


async def _execute_category_intent(
    intent: EditIntent, user_id: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Dispatch the category-management intents (no task lookup)."""
    if intent.intent == "create_category":
        return await _execute_create_category(user_id, intent), None
    if intent.intent == "rename_category":
        return await _execute_rename_category(user_id, intent), None
    if intent.intent == "delete_category":
        return await _category_delete_confirmation(user_id, intent)
    return f"Действие «{intent.intent}» пока не поддерживается.", None


async def _delete_confirmation(
    task_id: int, user_id: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build the two-step delete confirmation prompt for one task.

    G3: returns ``(prompt, keyboard)`` for a free-text ``delete`` intent
    *without* mutating the task. The task is only soft-deleted when the
    user confirms via the ``edit:deldo:<id>`` callback.
    """
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            return "Задача не найдена.", None
        title = task.title
    return f"Удалить «{title}»?", _delete_confirm_keyboard(task_id, title)


async def _dispatch_single(
    task_id: int, user_id: int, intent: EditIntent
) -> tuple[str, int | None]:
    """Run the appropriate executor for *one* resolved task.

    Returns ``(reply_text, snapshot_id_or_none)``.
    """
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
    if intent.intent == "cancel_reminder":
        return await _execute_cancel_reminder(task_id, user_id)
    return f"Действие «{intent.intent}» пока не поддерживается — скоро добавлю.", None


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

    # Category-management intents operate on a category, not a task —
    # they have no task_query, so route them before the task lookup.
    if intent.intent in EDIT_INTENTS_CATEGORY:
        return await _execute_category_intent(intent, user_id)

    # For reopen, search among completed tasks too.
    include_done = intent.intent == "reopen"

    if not query:
        # PR-I3: LAST_TASK anaphora — fallback when query is empty.
        last_id = pop_last_task(user_id)
        if last_id is not None:
            logger.info("edit.anaphora", user_id=user_id, task_id=last_id)
            touch_last_task(user_id, last_id)
            # G3: free-text delete needs explicit confirmation, never auto-runs.
            if intent.intent == "delete":
                return await _delete_confirmation(last_id, user_id)
            reply, snap_id = await _dispatch_single(last_id, user_id, intent)
            kb = _undo_keyboard(snap_id) if snap_id else None
            return reply, kb
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

    touch_last_task(user_id, task.id)

    # G3: a free-text delete intent that resolved to a single task is the
    # highest-risk Excessive-Agency path — surface a confirm/cancel prompt
    # instead of soft-deleting on the model's say-so.
    if intent.intent == "delete":
        logger.info("edit.delete_confirm", task_id=task.id, user_id=user_id)
        return await _delete_confirmation(task.id, user_id)

    reply, snap_id = await _dispatch_single(task.id, user_id, intent)

    logger.info(
        "edit.executed",
        intent=intent.intent,
        task_id=task.id,
        user_id=user_id,
    )
    kb = _undo_keyboard(snap_id) if snap_id else None
    return reply, kb
