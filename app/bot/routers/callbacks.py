"""Inline-button callback handlers for task actions.

Phase 3b: ✅ done, 🔄 move (horizon picker), 🗑 delete.
Phase 3 finish: 🏷 change category (category picker).
Callback data format: ``task:<action>:<task_id>[:<extra>]``.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.ai.courier import (
    NOTE_PREFIX,
    TASK_DONE_PREFIX,
    TASK_PENDING_PREFIX,
)
from app.bot.edit_executor import (
    _execute_complete,
    _execute_delete,
    _execute_reopen,
)
from app.bot.pinned_today import refresh_pinned_morning
from app.bot.services import (
    delete_task,
    get_or_create_user,
    get_task_by_id,
    get_user_categories_full,
    mark_task_done,
    mark_task_undone,
    update_task_category,
    update_task_horizon,
)
from app.db.base import session_scope
from app.db.models import Category
from app.shared.logging import get_logger

logger = get_logger(__name__)

HORIZON_OPTIONS: list[tuple[str, str]] = [
    ("today", "Сегодня"),
    ("tomorrow", "Завтра"),
    ("week", "На неделе"),
    ("month", "В месяце"),
    ("year", "В году"),
    ("someday", "Когда-нибудь"),
]


def parse_task_callback(data: str, action: str, *, arity: int = 3) -> tuple[int, list[str]] | None:
    """Parse a ``task:<action>:<task_id>[:<extra>...]`` callback string.

    Returns ``(task_id, extra_parts)`` where ``extra_parts`` are the raw
    string components after ``task_id`` (length ``arity - 3``). Returns
    ``None`` when the prefix, action, arity check, or ``int()`` parse of
    ``task_id`` fails — the handler should answer "Неверный формат." in
    that case instead of letting ``ValueError`` propagate. Regression
    fix for ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-1``.
    """
    parts = data.split(":")
    if len(parts) != arity or parts[0] != "task" or parts[1] != action:
        return None
    try:
        task_id = int(parts[2])
    except ValueError:
        return None
    return task_id, parts[3:]


def parse_summary_toggle_callback(data: str) -> tuple[str, int] | None:
    """Parse a ``summary:toggle:<kind>:<id>`` callback string.

    PR-E recognised-card payload — separate from
    :func:`parse_task_callback` because the shape is different
    (``summary`` prefix, ``kind`` is a string discriminant, not a row
    number). Returns ``(kind, entity_id)`` on success or ``None`` for
    malformed / unknown-kind payloads. ``kind`` is one of
    ``{"task", "note"}`` — anything else is rejected.

    Mirrors the R-NEW-I-1 discipline: all ``int(...)`` calls on
    user-controlled payload components live here, behind a guarded
    ``try/except``, so handlers can stay free of unguarded parses.
    """
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "summary" or parts[1] != "toggle":
        return None
    kind = parts[2]
    if kind not in {"task", "note"}:
        return None
    try:
        entity_id = int(parts[3])
    except ValueError:
        return None
    return kind, entity_id


def task_action_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Build the inline keyboard shown under each task."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton(
                    text="🔄 Перенести", callback_data=f"task:pick_move:{task_id}"
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:delete:{task_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="🏷 Категория", callback_data=f"task:pick_category:{task_id}"
                ),
            ],
        ],
    )


def horizon_list_keyboard(tasks_with_indices: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Build a compact action keyboard listing every task in a horizon view.

    Each task gets one keyboard row of four emoji-only buttons:
    ``N ✅``, ``N 🔄``, ``N 🗑``, ``N 🏷`` (where ``N`` is the
    1-based row number shown in the summary). The callback_data
    payload is identical to :func:`task_action_keyboard` so all
    existing handlers work unchanged. Replaces the per-task message
    spam in ``/today``-style commands. See
    ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-6``.

    ``tasks_with_indices`` is a list of ``(index, task_id)`` pairs.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for idx, task_id in tasks_with_indices:
        rows.append(
            [
                InlineKeyboardButton(text=f"{idx} ✅", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton(text=f"{idx} 🔄", callback_data=f"task:pick_move:{task_id}"),
                InlineKeyboardButton(text=f"{idx} 🗑", callback_data=f"task:delete:{task_id}"),
                InlineKeyboardButton(
                    text=f"{idx} 🏷", callback_data=f"task:pick_category:{task_id}"
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_picker_keyboard(task_id: int, categories: list[Category]) -> InlineKeyboardMarkup:
    """Build the category-selection keyboard for changing task category."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        if cat.id is None:
            continue
        row.append(
            InlineKeyboardButton(
                text=cat.name,
                callback_data=f"task:set_category:{task_id}:{cat.id}",
            ),
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="↩ Назад", callback_data=f"task:cancel:{task_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def horizon_picker_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Build the horizon-selection keyboard for moving a task."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug, label in HORIZON_OPTIONS:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"task:move:{task_id}:{slug}",
            ),
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="↩ Назад", callback_data=f"task:cancel:{task_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_edit_resolve_callback(data: str) -> tuple[str, int] | None:
    """Parse an ``edit:resolve:<intent>:<task_id>`` callback string.

    PR-I1 disambiguation pick. Returns ``(intent_name, task_id)`` on
    success, ``None`` on malformed input — same discipline as
    :func:`parse_task_callback`.
    """
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "edit" or parts[1] != "resolve":
        return None
    try:
        task_id = int(parts[3])
    except ValueError:
        return None
    return parts[2], task_id


def create_router() -> Router:
    """Build a fresh ``callbacks`` router."""
    router = Router(name="callbacks")

    @router.callback_query(F.data.startswith("task:done:"))
    async def cb_task_done(callback: CallbackQuery) -> None:
        """Mark a task as completed."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "done")
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, _ = parsed

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            await mark_task_done(session, task, user.id)
            user_id_for_pin = user.id

        await callback.answer("✅ Выполнено!")
        if isinstance(callback.message, Message):
            # No parse_mode: task.title is user-controlled and can contain
            # Markdown metachars that crash Telegram's parser.
            await callback.message.edit_text(f"✅ Выполнено: «{task.title}»")

        # Phase 6.3: refresh the pinned morning digest so the strikethrough
        # state is live. Best-effort — handled inside refresh_pinned_morning.
        if callback.bot is not None:
            async with session_scope() as session:
                try:
                    await refresh_pinned_morning(callback.bot, session, user_id_for_pin)
                except Exception:
                    logger.warning(
                        "callbacks.refresh_pinned_failed",
                        user_id=user_id_for_pin,
                        exc_info=True,
                    )

    @router.callback_query(F.data.startswith("task:delete:"))
    async def cb_task_delete(callback: CallbackQuery) -> None:
        """Delete a task."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "delete")
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, _ = parsed

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            title = task.title
            await delete_task(session, task, user.id)

        await callback.answer("🗑 Удалено!")
        if isinstance(callback.message, Message):
            await callback.message.edit_text(f"🗑 Удалено: «{title}»")

    @router.callback_query(F.data.startswith("task:pick_move:"))
    async def cb_task_pick_move(callback: CallbackQuery) -> None:
        """Show horizon picker for moving a task."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "pick_move")
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, _ = parsed

        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=horizon_picker_keyboard(task_id),
            )

    @router.callback_query(F.data.startswith("task:move:"))
    async def cb_task_move(callback: CallbackQuery) -> None:
        """Move a task to a chosen horizon."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "move", arity=4)
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, extras = parsed
        target_horizon = extras[0]

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            await update_task_horizon(session, task, target_horizon, user.id)

        horizon_labels = dict(HORIZON_OPTIONS)
        label = horizon_labels.get(target_horizon, target_horizon)
        await callback.answer(f"Перенесено → {label}")
        if isinstance(callback.message, Message):
            await callback.message.edit_text(f"🔄 «{task.title}» → {label}")

    @router.callback_query(F.data.startswith("task:cancel:"))
    async def cb_task_cancel(callback: CallbackQuery) -> None:
        """Cancel horizon / category picker — restore action buttons."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "cancel")
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, _ = parsed

        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=task_action_keyboard(task_id),
            )

    @router.callback_query(F.data.startswith("task:pick_category:"))
    async def cb_task_pick_category(callback: CallbackQuery) -> None:
        """Show category picker for changing task category."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "pick_category")
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, _ = parsed

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            categories = await get_user_categories_full(session, user.id)

        if not categories:
            await callback.answer("Категорий пока нет — добавятся при разборе сообщений.")
            return

        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=category_picker_keyboard(task_id, categories),
            )

    @router.callback_query(F.data.startswith("task:set_category:"))
    async def cb_task_set_category(callback: CallbackQuery) -> None:
        """Apply a chosen category to the task."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_task_callback(callback.data, "set_category", arity=4)
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        task_id, extras = parsed
        try:
            new_category_id = int(extras[0])
        except ValueError:
            await callback.answer("Неверный формат.")
            return

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, task_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            categories = await get_user_categories_full(session, user.id)
            cat = next((c for c in categories if c.id == new_category_id), None)
            if cat is None:
                await callback.answer("Категория не найдена.")
                return
            await update_task_category(session, task, new_category_id, user.id)

        await callback.answer(f"Категория → {cat.name}")
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"🏷 «{task.title}» → {cat.name}",
                reply_markup=task_action_keyboard(task_id),
            )

    @router.callback_query(F.data.startswith("summary:toggle:"))
    async def cb_summary_toggle(callback: CallbackQuery) -> None:
        """Toggle a task's done/pending status from the recognised-card.

        Callback payload: ``summary:toggle:<kind>:<id>`` where ``kind``
        is ``task`` or ``note`` and ``<id>`` is the row's primary key.

        - **task** → flip the row prefix between ☐ and ✅ in the
          keyboard, and mirror the change in the DB via
          :func:`mark_task_done` / :func:`mark_task_undone`.
        - **note** → no DB mutation (notes don't have a ``done``
          state). Just answer the callback with a short toast so the
          spinner clears. Final semantics TBD per HANDOFF v15
          §Open-questions.
        """
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_summary_toggle_callback(callback.data)
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        kind, entity_id = parsed

        if kind == "note":
            # Pending the open-question resolution (archive vs delete
            # vs ignore), tapping a note row is intentionally inert:
            # the keyboard stays as-is and the user just gets a toast.
            # This keeps the surface honest — we don't yet promise any
            # destructive semantic.
            await callback.answer("Заметка — не требует действий.")
            return

        # ── kind == "task" ────────────────────────────────────────
        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            task = await get_task_by_id(session, user.id, entity_id)
            if task is None:
                await callback.answer("Задача не найдена.")
                return
            currently_done = task.status == "done"
            if currently_done:
                await mark_task_undone(session, task, user.id)
                toast = "Снова в работе."
            else:
                await mark_task_done(session, task, user.id)
                toast = "Готово!"
            user_id_for_pin = user.id

        await callback.answer(toast)

        # Rebuild the keyboard with the flipped prefix on this row.
        if isinstance(callback.message, Message) and callback.message.reply_markup is not None:
            new_markup = _flip_summary_row(
                callback.message.reply_markup,
                kind="task",
                entity_id=entity_id,
                now_done=not currently_done,
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=new_markup)
            except Exception:
                logger.warning(
                    "callbacks.summary_toggle.edit_failed",
                    user_id=user_id_for_pin,
                    task_id=entity_id,
                    exc_info=True,
                )

        # Mirror :func:`cb_task_done` — keep the pinned morning digest
        # in sync with the task's new status.
        if callback.bot is not None:
            async with session_scope() as session:
                try:
                    await refresh_pinned_morning(callback.bot, session, user_id_for_pin)
                except Exception:
                    logger.warning(
                        "callbacks.summary_toggle.refresh_pinned_failed",
                        user_id=user_id_for_pin,
                        exc_info=True,
                    )

    @router.callback_query(F.data.startswith("edit:resolve:"))
    async def cb_edit_resolve(callback: CallbackQuery) -> None:
        """Handle disambiguation pick from edit-intent multi-match (PR-I1)."""
        if callback.from_user is None or callback.data is None:
            return
        parsed = parse_edit_resolve_callback(callback.data)
        if parsed is None:
            await callback.answer("Неверный формат.")
            return
        intent_name, task_id = parsed

        async with session_scope() as session:
            user, _ = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
            )
            if user.id is None:
                await callback.answer("Ошибка.")
                return
            user_id = user.id

        if intent_name == "complete":
            reply = await _execute_complete(task_id, user_id)
        elif intent_name == "delete":
            reply = await _execute_delete(task_id, user_id)
        elif intent_name == "reopen":
            reply = await _execute_reopen(task_id, user_id)
        else:
            reply = f"Действие «{intent_name}» пока не поддерживается."

        await callback.answer(reply[:200])
        if isinstance(callback.message, Message):
            await callback.message.edit_text(reply)

        if callback.bot is not None:
            async with session_scope() as session:
                try:
                    await refresh_pinned_morning(callback.bot, session, user_id)
                except Exception:
                    logger.warning(
                        "callbacks.edit_resolve.refresh_pinned_failed",
                        user_id=user_id,
                        exc_info=True,
                    )

    return router


def _flip_summary_row(
    markup: InlineKeyboardMarkup,
    *,
    kind: str,
    entity_id: int,
    now_done: bool,
) -> InlineKeyboardMarkup:
    """Return a copy of ``markup`` with the target row's prefix flipped.

    Used by :func:`cb_summary_toggle` to mutate just one row of the
    recognised-card keyboard without rebuilding the whole
    :class:`SummaryItem` list from scratch. Buttons we don't own (other
    rows, non-summary callbacks) are passed through untouched.

    The label format is exactly what ``app.ai.courier._row_label`` emits
    — a prefix from ``{☐, ✅, 📄}`` followed by the title. We flip
    *only* the prefix and only on the matching row, so e.g. titles with
    a leading "📄" can't accidentally be misread as a note label.
    """
    target_callback = f"summary:toggle:{kind}:{entity_id}"
    new_prefix = TASK_DONE_PREFIX if now_done else TASK_PENDING_PREFIX
    old_prefixes = (TASK_PENDING_PREFIX, TASK_DONE_PREFIX, NOTE_PREFIX)

    rows_out: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        new_row: list[InlineKeyboardButton] = []
        for button in row:
            if button.callback_data != target_callback:
                new_row.append(button)
                continue
            label = button.text
            for prefix in old_prefixes:
                if label.startswith(prefix):
                    label = new_prefix + label[len(prefix) :]
                    break
            new_row.append(
                InlineKeyboardButton(text=label, callback_data=button.callback_data),
            )
        rows_out.append(new_row)
    return InlineKeyboardMarkup(inline_keyboard=rows_out)
