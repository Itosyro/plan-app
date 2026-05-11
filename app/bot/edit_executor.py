"""Execute edit intents detected by ``app.ai.intent.detect_intent`` (PR-I1).

Each executor receives a ``task_id`` and performs the action in its own
``session_scope``, returning a human-readable confirmation string.
The top-level ``execute_edit`` dispatches to the right executor and
handles multi-match disambiguation via inline keyboard.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ai.schemas import EditIntent
from app.bot.services import (
    delete_task,
    find_tasks_by_query,
    get_task_by_id,
    mark_task_done,
    mark_task_undone,
    update_task_horizon,
)
from app.db.base import session_scope
from app.db.models import Task
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Intents handled by this module (PR-I1 scope).
EDIT_INTENTS_I1 = frozenset({"complete", "delete", "reopen", "reorder_horizon"})

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


async def execute_edit(
    intent: EditIntent,
    user_id: int,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Dispatch an edit intent: find the task, handle ambiguity, execute.

    Returns ``(reply_text, keyboard_or_none)``.
    """
    query = (intent.task_query or "").strip()

    # For reopen, search among completed tasks too.
    include_done = intent.intent == "reopen"

    if not query:
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
        keyboard = _disambiguation_keyboard(intent, matches)
        return (
            f"Нашёл несколько подходящих задач по запросу «{query}», уточни какую:",
            keyboard,
        )

    task = matches[0]
    if task.id is None:
        return "Ошибка: задача без ID.", None

    if intent.intent == "complete":
        reply = await _execute_complete(task.id, user_id)
    elif intent.intent == "delete":
        reply = await _execute_delete(task.id, user_id)
    elif intent.intent == "reopen":
        reply = await _execute_reopen(task.id, user_id)
    elif intent.intent == "reorder_horizon":
        reply = await _execute_reorder_horizon(task.id, user_id, intent)
    else:
        reply = f"Действие «{intent.intent}» пока не поддерживается — скоро добавлю."

    logger.info(
        "edit.executed",
        intent=intent.intent,
        task_id=task.id,
        user_id=user_id,
    )
    return reply, None
