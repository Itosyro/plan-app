"""Task / Note / Category / Horizon CRUD + classification persistence + reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import Insert as _PgInsert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as _SqliteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult
from app.db.models import (
    Category,
    Horizon,
    Note,
    Reminder,
    Task,
    TaskEvent,
)
from app.shared.logging import get_logger
from app.shared.time import to_naive_utc, utcnow_naive

logger = get_logger(__name__)


# ── Category / Horizon helpers ────────────────────────────────────────


def _dialect_insert(session: AsyncSession, table: type) -> _PgInsert | _SqliteInsert:
    """Pick the dialect-flavoured ``INSERT`` so we can use
    ``ON CONFLICT DO NOTHING`` (Postgres + SQLite both support it).

    We need the dialect-specific Insert because the generic
    ``sqlalchemy.insert(...)`` doesn't expose ``on_conflict_do_nothing()``.
    """
    bind = session.bind
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    if dialect_name == "sqlite":
        return sqlite_insert(table)
    return pg_insert(table)


async def get_or_create_category(
    session: AsyncSession,
    user_id: int,
    name: str,
) -> Category:
    """Find or create a category for the user.

    Race-safe under concurrent webhook deliveries: two pipelines for
    the same user that both decide to create the same category will
    not both raise. We use ``INSERT ... ON CONFLICT DO NOTHING`` (Core
    SQL — bypasses the ORM identity map so a no-op insert can't poison
    our session's pending state) followed by a re-SELECT for the row.
    The cheap SELECT-first path keeps the common case (category already
    exists) at one round-trip. See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-2``.
    """
    result = await session.exec(
        select(Category).where(Category.user_id == user_id, Category.name == name),
    )
    cat = result.first()
    if cat is not None:
        return cat
    stmt = (
        _dialect_insert(session, Category)
        .values(user_id=user_id, name=name)
        .on_conflict_do_nothing()
    )
    await session.exec(stmt)
    await session.flush()
    result = await session.exec(
        select(Category).where(Category.user_id == user_id, Category.name == name),
    )
    cat = result.first()
    if cat is None:
        # Should never happen: ON CONFLICT DO NOTHING means either we
        # inserted the row or someone else already had it — either way
        # the row exists at this point. Keep this branch for safety.
        raise RuntimeError(f"category {name!r} for user {user_id} not found after upsert")
    return cat


async def get_or_create_horizon(
    session: AsyncSession,
    user_id: int,
    slug: str,
) -> Horizon:
    """Find or create a horizon for the user.

    Race-safe under concurrent webhook deliveries — see the docstring
    of :func:`get_or_create_category` for the upsert strategy.
    See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-2``.
    """
    result = await session.exec(
        select(Horizon).where(Horizon.user_id == user_id, Horizon.slug == slug),
    )
    hor = result.first()
    if hor is not None:
        return hor
    label = {
        "today": "Сегодня",
        "tomorrow": "Завтра",
        "week": "На этой неделе",
        "month": "В этом месяце",
        "year": "В этом году",
        "someday": "Когда-нибудь",
    }.get(slug, slug)
    stmt = (
        _dialect_insert(session, Horizon)
        .values(user_id=user_id, slug=slug, label=label)
        .on_conflict_do_nothing()
    )
    await session.exec(stmt)
    await session.flush()
    result = await session.exec(
        select(Horizon).where(Horizon.user_id == user_id, Horizon.slug == slug),
    )
    hor = result.first()
    if hor is None:
        raise RuntimeError(f"horizon {slug!r} for user {user_id} not found after upsert")
    return hor


async def get_user_categories(
    session: AsyncSession,
    user_id: int,
) -> list[str]:
    """Return a list of category names for the user."""
    result = await session.exec(
        select(Category.name).where(Category.user_id == user_id),
    )
    return list(result.all())


async def get_user_categories_full(
    session: AsyncSession,
    user_id: int,
) -> list[Category]:
    """Return all ``Category`` rows for the user, ordered by name."""
    result = await session.exec(
        select(Category).where(Category.user_id == user_id).order_by(Category.name),
    )
    return list(result.all())


async def find_category_by_name(
    session: AsyncSession,
    user_id: int,
    name: str,
) -> Category | None:
    """Find one of the user's categories by name (case-insensitive).

    Voice/text commands rarely match the stored casing ("финансы" vs
    "Финансы"), so the lookup folds case. Folding happens in Python, not
    via SQL ``lower()`` — SQLite's ``lower()`` only folds ASCII, so a
    SQL-side comparison would silently miss Cyrillic. A user has at most a
    handful of categories, so loading them all is cheap.
    """
    folded = name.strip().lower()
    if not folded:
        return None
    result = await session.exec(
        select(Category).where(Category.user_id == user_id),
    )
    for cat in result.all():
        if cat.name.lower() == folded:
            return cat
    return None


async def rename_category(
    session: AsyncSession,
    category: Category,
    new_name: str,
) -> Category:
    """Rename a category in place."""
    category.name = new_name
    session.add(category)
    await session.flush()
    logger.info("category.renamed", category_id=category.id, user_id=category.user_id)
    return category


async def delete_category(
    session: AsyncSession,
    category: Category,
) -> int:
    """Delete a category, leaving its tasks and notes uncategorised.

    The category FK is nullable on both ``Task`` and ``Note``; rather than
    cascade-deleting the user's items we null their ``category_id`` so the
    work survives (just moves to "Без категории"). Returns the number of
    active (non-deleted) tasks that were detached, for the confirmation.
    """
    cat_id = category.id
    if cat_id is None:
        return 0

    affected = (
        await session.exec(
            select(func.count())
            .select_from(Task)
            .where(
                Task.category_id == cat_id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            ),
        )
    ).one()

    await session.exec(
        sa_update(Task).where(Task.category_id == cat_id).values(category_id=None),  # type: ignore[arg-type]
    )
    await session.exec(
        sa_update(Note).where(Note.category_id == cat_id).values(category_id=None),  # type: ignore[arg-type]
    )
    await session.delete(category)
    await session.flush()
    logger.info("category.deleted", category_id=cat_id, user_id=category.user_id, tasks=affected)
    return int(affected)


# ── Reminders ─────────────────────────────────────────────────────────


DEFAULT_REMINDER_OFFSETS: dict[str, list[int]] = {
    "same_day": [60, 15],
    "multi_day": [1440, 60],
}


def _select_reminder_offsets(
    cr: ClassifierResult,
    default_offsets: dict[str, list[int]] | None,
) -> list[int]:
    """Pick which minute-offsets to schedule reminders at.

    Explicit offsets from the classifier (LLM-detected "напомни за 30 минут")
    win over the user's defaults. ``0`` is preserved — it means "fire AT
    ``due_at``" and is the canonical offset for the bare "напомни мне в
    12:00" use case where the user wants exactly one reminder, at the
    due time itself.

    Defaults are drawn from ``UserSettings.default_reminder_offsets``
    (or ``DEFAULT_REMINDER_OFFSETS`` as a fallback) and only apply when
    the classifier did not request explicit offsets. Defaults are
    *advance-warning* offsets (e.g. 60 minutes before), so a non-positive
    value there is dropped.
    """
    if cr.reminder_offsets is not None:
        # Explicit list — preserve order and de-duplicate while keeping 0
        # as a legitimate "fire at due_at" sentinel. Negative values are
        # nonsense (would imply firing *after* the due time) and are
        # filtered out.
        seen: set[int] = set()
        result: list[int] = []
        for o in cr.reminder_offsets:
            v = int(o)
            if v < 0 or v in seen:
                continue
            seen.add(v)
            result.append(v)
        return result
    defaults = default_offsets or DEFAULT_REMINDER_OFFSETS
    bucket = "same_day" if cr.horizon in {"today", "tomorrow"} else "multi_day"
    raw = defaults.get(bucket) or []
    return [int(o) for o in raw if int(o) > 0]


# Backwards-compat alias: pre-2026-05-09 callers used the private name.
# Prefer :func:`app.shared.time.to_naive_utc` in new code.
_to_naive_utc = to_naive_utc


async def schedule_reminders(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    due_at: datetime,
    offsets: list[int],
    now: datetime | None = None,
) -> list[Reminder]:
    """Create ``Reminder`` rows ``offset`` minutes before *due_at*.

    Offsets resolving to a ``fire_at`` at or before *now* are skipped — there's
    no point scheduling a reminder that's already in the past. Inputs are
    normalised to **naive UTC** before storage so reads/writes are consistent
    with the rest of the schema (timestamps live as ``DateTime`` without tz).
    """
    if not offsets:
        return []
    ref_due = to_naive_utc(due_at)
    ref_now = to_naive_utc(now) if now is not None else utcnow_naive()
    created: list[Reminder] = []
    for offset in offsets:
        # ``offset == 0`` is the canonical "напомни в точно в это время"
        # case (fire AT ``due_at``). Negative offsets are nonsense
        # (would imply firing *after* the due time) and are skipped.
        if offset < 0:
            continue
        fire_at = ref_due - timedelta(minutes=offset)
        if fire_at <= ref_now:
            continue
        reminder = Reminder(
            user_id=user_id,
            task_id=task_id,
            fire_at=fire_at,
            status="pending",
        )
        session.add(reminder)
        created.append(reminder)
    if created:
        await session.flush()
    return created


async def list_pending_reminders(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
    include_overdue: bool = False,
    now: datetime | None = None,
) -> list[tuple[Reminder, Task]]:
    """Return pending reminders for active tasks.

    ``include_overdue=False`` (default) keeps only ``fire_at >= now`` —
    that's the "upcoming" view used by ``/reminders``. Setting it to
    ``True`` returns overdue pending rows too, used by ``/reminders all``
    so the user can still see reminders the scheduler hasn't fired yet
    (e.g. after a long Render cold-start).
    """
    stmt = (
        select(Reminder, Task)
        .join(Task, Task.id == Reminder.task_id)  # type: ignore[arg-type]
        .where(
            Reminder.user_id == user_id,
            Reminder.status == "pending",
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Reminder.fire_at)  # type: ignore[arg-type]
        .offset(offset)
        .limit(limit)
    )
    if not include_overdue:
        cutoff = to_naive_utc(now) if now is not None else utcnow_naive()
        stmt = stmt.where(Reminder.fire_at >= cutoff)
    result = await session.exec(stmt)
    return list(result.all())


async def count_pending_reminders(
    session: AsyncSession,
    user_id: int,
    *,
    include_overdue: bool = False,
    now: datetime | None = None,
) -> int:
    """Count pending reminders for active tasks, mirroring filters of
    :func:`list_pending_reminders`.

    Used by the ``/reminders`` UI to decide whether to render the "next
    page" button and the "Показано N из M" footer without re-querying
    every page.
    """
    stmt = (
        select(func.count(Reminder.id))  # type: ignore[arg-type]
        .join(Task, Task.id == Reminder.task_id)  # type: ignore[arg-type]
        .where(
            Reminder.user_id == user_id,
            Reminder.status == "pending",
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    if not include_overdue:
        cutoff = to_naive_utc(now) if now is not None else utcnow_naive()
        stmt = stmt.where(Reminder.fire_at >= cutoff)
    result = await session.exec(stmt)
    return int(result.one() or 0)


async def cancel_reminder(
    session: AsyncSession,
    user_id: int,
    reminder_id: int,
) -> Reminder | None:
    """Cancel one pending reminder owned by the user."""
    result = await session.exec(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.status == "pending",
        ),
    )
    reminder = result.first()
    if reminder is None:
        return None
    reminder.status = "cancelled"
    reminder.last_error = None
    session.add(reminder)
    await session.flush()

    if reminder.task_id is not None:
        session.add(
            TaskEvent(
                task_id=reminder.task_id,
                kind="reminder_cancelled",
                payload_json={
                    "reminder_id": reminder.id,
                    "fire_at": reminder.fire_at.isoformat() if reminder.fire_at else None,
                    "scope": "single",
                },
            ),
        )
        await session.flush()
        logger.info("reminder.cancelled", reminder_id=reminder.id, user_id=user_id)

    return reminder


async def cancel_task_reminders(
    session: AsyncSession,
    user_id: int,
    task_id: int,
) -> list[Reminder]:
    """Cancel all pending reminders for one active task.

    Returns the list of cancelled ``Reminder`` rows (with their original
    ``fire_at`` preserved) so callers can show *when* the cancelled
    reminders were scheduled, not just how many. Caller treats an empty
    list as "nothing to cancel".
    """
    result = await session.exec(
        select(Reminder)
        .join(Task, Task.id == Reminder.task_id)  # type: ignore[arg-type]
        .where(
            Reminder.user_id == user_id,
            Reminder.task_id == task_id,
            Reminder.status == "pending",
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Reminder.fire_at),  # type: ignore[arg-type]
    )
    reminders = list(result.all())
    for reminder in reminders:
        reminder.status = "cancelled"
        reminder.last_error = None
        session.add(reminder)
    if reminders:
        await session.flush()
        for reminder in reminders:
            session.add(
                TaskEvent(
                    task_id=task_id,
                    kind="reminder_cancelled",
                    payload_json={
                        "reminder_id": reminder.id,
                        "fire_at": reminder.fire_at.isoformat() if reminder.fire_at else None,
                        "scope": "task",
                    },
                ),
            )
        await session.flush()
        logger.info(
            "reminder.cancelled",
            task_id=task_id,
            user_id=user_id,
            count=len(reminders),
        )
    return reminders


# ── Classification persistence ────────────────────────────────────────


FIRST_STEP_PREFIX = "Шаг 1: "


def _build_task_description(cr: ClassifierResult, *, concretize: bool) -> str | None:
    """Compose ``Task.description`` from the classifier output.

    Pre-FirstStep behaviour: when ``concretize`` was on and the
    classifier returned a non-empty ``first_step``, we used to prepend
    "Шаг 1: <first_step>" to ``description``. Since the FirstStep
    rewrite (PR ``claude/first-step-rewriter``) the actionable phrasing
    now lives in ``Task.title`` directly (with the original abstract
    text preserved in ``title_original``), so the description prefix
    would be redundant. Kept as a no-op for callers that still pass
    ``concretize``; description stays ``None`` until we have another
    source for it.
    """
    del cr, concretize
    return None


def _resolve_titles(cr: ClassifierResult, *, concretize: bool) -> tuple[str, str | None]:
    """Return the ``(title, title_original)`` pair to persist.

    When ``concretize`` is enabled and the classifier proposed a
    concrete ``first_step`` for an abstract goal, we swap: the
    actionable step becomes the visible title and the original abstract
    phrasing is stashed in ``title_original`` for UI subtitle display.
    Otherwise the original title stays put and ``title_original`` is
    ``None`` (no rewrite happened).
    """
    step = (cr.first_step or "").strip() if concretize else ""
    if step:
        return step, cr.title
    return cr.title, None


async def persist_classification(
    session: AsyncSession,
    *,
    user_id: int,
    cr: ClassifierResult,
    due_at: datetime | None,
    inbox_id: int | None,
    default_reminder_offsets: dict[str, list[int]] | None = None,
    concretize_tasks: bool = False,
) -> Task | Note:
    """Persist a ClassifierResult as a Task or Note row.

    For tasks with a concrete ``due_at``, also schedules ``Reminder`` rows
    according to either ``cr.reminder_offsets`` (explicit user request) or
    the user's ``default_reminder_offsets`` (Phase 4a).

    ``concretize_tasks`` (PR-E) controls whether the classifier's
    optional ``first_step`` lands in ``Task.description`` — see
    :func:`_build_task_description`. Defaults to ``False`` so legacy
    callers (and tests) keep current behaviour without explicitly
    threading the flag through.
    """
    cat = await get_or_create_category(session, user_id, cr.category_name)
    hor = await get_or_create_horizon(session, user_id, cr.horizon)

    if cr.is_task:
        # Normalise ``due_at`` to naive UTC before persisting — ``dateparser``
        # returns a tz-aware value in the user's tz, and the column is tz-naive.
        # Without this we'd silently store user-local time in a column the rest
        # of the schema treats as UTC. See ``docs/REVIEW-2026-05-09.md::C-2``.
        due_at_utc = to_naive_utc(due_at) if due_at is not None else None
        description = _build_task_description(cr, concretize=concretize_tasks)
        title, title_original = _resolve_titles(cr, concretize=concretize_tasks)
        row: Task | Note = Task(
            user_id=user_id,
            category_id=cat.id,
            horizon_id=hor.id,
            title=title,
            title_original=title_original,
            description=description,
            priority=cr.priority,
            due_at=due_at_utc,
            confidence=cr.confidence,
            source_inbox_id=inbox_id,
        )
    else:
        row = Note(
            user_id=user_id,
            category_id=cat.id,
            title=cr.title,
            source_inbox_id=inbox_id,
        )

    session.add(row)
    await session.flush()

    reminders_created = 0
    subtasks_created = 0
    if cr.is_task:
        if not isinstance(row, Task) or row.id is None:
            raise RuntimeError("Expected a flushed Task row after persist")
        session.add(
            TaskEvent(task_id=row.id, kind="created", payload_json={"source": "classifier"}),
        )
        await session.flush()

        if due_at is not None:
            offsets = _select_reminder_offsets(cr, default_reminder_offsets)
            reminders = await schedule_reminders(
                session,
                user_id=user_id,
                task_id=row.id,
                due_at=due_at,
                offsets=offsets,
            )
            reminders_created = len(reminders)

        subtasks_created = await _persist_subtasks(
            session,
            parent=row,
            cr=cr,
            cat_id=cat.id,
            hor_id=hor.id,
        )

    logger.info(
        "persist.done",
        user_id=user_id,
        is_task=cr.is_task,
        category=cr.category_name,
        title=cr.title,
        reminders_created=reminders_created,
        subtasks_created=subtasks_created,
    )
    return row


# Hard cap on classifier-proposed subtasks per parent — anything beyond
# this is almost always LLM noise or runaway output and clutters the UI.
_MAX_SUBTASKS_PER_PARENT = 5


async def _persist_subtasks(
    session: AsyncSession,
    *,
    parent: Task,
    cr: ClassifierResult,
    cat_id: int | None,
    hor_id: int | None,
) -> int:
    """Persist classifier-proposed subtasks as child Tasks of ``parent``.

    Children inherit the parent's category / horizon / priority — the
    classifier only emits a list of titles. Empty / null subtasks list
    is a no-op. Capped at :data:`_MAX_SUBTASKS_PER_PARENT` items so a
    runaway LLM can't blow up a single parent into hundreds of rows.
    Returns the number of subtasks actually created (after de-duping
    blank strings).
    """
    if not cr.subtasks or parent.id is None:
        return 0
    titles: list[str] = []
    seen: set[str] = set()
    for raw in cr.subtasks[:_MAX_SUBTASKS_PER_PARENT]:
        title = raw.strip()
        if not title or title in seen:
            continue
        if len(title) > 256:
            title = title[:255].rstrip() + "…"
        seen.add(title)
        titles.append(title)
    if not titles:
        return 0
    for title in titles:
        child = Task(
            user_id=parent.user_id,
            parent_id=parent.id,
            category_id=cat_id,
            horizon_id=hor_id,
            title=title,
            priority=parent.priority,
            confidence=parent.confidence,
            source_inbox_id=parent.source_inbox_id,
        )
        session.add(child)
    await session.flush()
    return len(titles)


async def split_existing_task(
    session: AsyncSession,
    parent: Task,
    titles: list[str],
) -> list[Task]:
    """Persist *titles* as subtasks of an existing *parent* task.

    Mirrors the dedup / cap / truncate logic of :func:`_persist_subtasks`
    but operates on an already-persisted parent rather than a fresh
    classifier result. Children inherit the parent's user, category,
    horizon and priority — only the title varies. Returns the created
    ``Task`` rows in input order (after dedup / blanks filtering).
    Empty input or a parent with no id is a no-op returning ``[]``.
    """
    if not titles or parent.id is None:
        return []
    normalised: list[str] = []
    seen: set[str] = set()
    for raw in titles[:_MAX_SUBTASKS_PER_PARENT]:
        title = raw.strip()
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        if len(title) > 256:
            title = title[:255].rstrip() + "…"
        seen.add(key)
        normalised.append(title)
    if not normalised:
        return []
    children: list[Task] = []
    for title in normalised:
        child = Task(
            user_id=parent.user_id,
            parent_id=parent.id,
            category_id=parent.category_id,
            horizon_id=parent.horizon_id,
            title=title,
            priority=parent.priority,
        )
        session.add(child)
        children.append(child)
    await session.flush()
    return children


# ── Task search / reorder ─────────────────────────────────────────────


def _escape_like(value: str) -> str:
    """Escape ``%`` / ``_`` / ``\\`` so they're treated as literals in LIKE."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def find_task_by_query(
    session: AsyncSession,
    user_id: int,
    query: str,
) -> Task | None:
    """Find a user's task whose title best matches *query*.

    Uses a simple case-insensitive LIKE search with wildcard escaping.
    Returns the most recently created match, or ``None`` if nothing found.
    """
    pattern = f"%{_escape_like(query)}%"
    result = await session.exec(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.title.ilike(pattern, escape="\\"),  # type: ignore[attr-defined]
            Task.status != "done",
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Task.created_at.desc()),  # type: ignore[attr-defined]
    )
    return result.first()


async def find_tasks_by_query(
    session: AsyncSession,
    user_id: int,
    query: str,
    *,
    limit: int = 5,
    include_done: bool = False,
) -> list[Task]:
    """Find user tasks whose title matches *query* (multi-match).

    PR-I1: returns up to *limit* matches so the edit-intent executor
    can present a disambiguation keyboard when >1 task matches.
    By default excludes completed tasks; ``include_done=True`` searches
    everything (useful for ``reopen`` intent).
    """
    pattern = f"%{_escape_like(query)}%"
    stmt = (
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.title.ilike(pattern, escape="\\"),  # type: ignore[attr-defined]
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Task.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    if not include_done:
        stmt = stmt.where(Task.status != "done")
    result = await session.exec(stmt)
    return list(result.all())


async def update_task_horizon(
    session: AsyncSession,
    task: Task,
    new_horizon_slug: str,
    user_id: int,
) -> Task:
    """Move a task to a different horizon and log the event."""
    old_horizon_id = task.horizon_id
    new_horizon = await get_or_create_horizon(session, user_id, new_horizon_slug)
    task.horizon_id = new_horizon.id
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="reordered",
                payload_json={
                    "old_horizon_id": old_horizon_id,
                    "new_horizon_slug": new_horizon_slug,
                },
            ),
        )
        await session.flush()

    logger.info(
        "task.reordered",
        task_id=task.id,
        user_id=user_id,
        new_horizon=new_horizon_slug,
    )
    return task


async def update_task_category(
    session: AsyncSession,
    task: Task,
    new_category_id: int | None,
    user_id: int,
) -> Task:
    """Move a task to a different category (or clear it) and log the event.

    ``new_category_id=None`` clears the category — used by the kanban
    "Без категории" column drop.
    """
    old_category_id = task.category_id
    task.category_id = new_category_id
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="recategorized",
                payload_json={
                    "old_category_id": old_category_id,
                    "new_category_id": new_category_id,
                },
            ),
        )
        await session.flush()

    logger.info(
        "task.recategorized",
        task_id=task.id,
        user_id=user_id,
        new_category_id=new_category_id,
    )
    return task


async def update_task_title(
    session: AsyncSession,
    task: Task,
    new_title: str,
    user_id: int,
) -> Task:
    """Rename a task and log the event."""
    old_title = task.title
    task.title = new_title
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="renamed",
                payload_json={"old_title": old_title, "new_title": new_title},
            ),
        )
        await session.flush()

    logger.info("task.renamed", task_id=task.id, user_id=user_id)
    return task


async def update_task_due_at(
    session: AsyncSession,
    task: Task,
    new_due_at: datetime | None,
    user_id: int,
) -> Task:
    """Change a task's due_at and log the event."""
    old_due = task.due_at.isoformat() if task.due_at else None
    task.due_at = new_due_at
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="due_changed",
                payload_json={
                    "old": old_due,
                    "new": new_due_at.isoformat() if new_due_at else None,
                },
            ),
        )
        await session.flush()

    logger.info("task.due_changed", task_id=task.id, user_id=user_id)
    return task


async def update_task_priority(
    session: AsyncSession,
    task: Task,
    new_priority: str,
    user_id: int,
) -> Task:
    """Change a task's priority and log the event."""
    old_priority = task.priority
    task.priority = new_priority
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="priority_changed",
                payload_json={"old": old_priority, "new": new_priority},
            ),
        )
        await session.flush()

    logger.info("task.priority_changed", task_id=task.id, user_id=user_id)
    return task


# ── View queries ──────────────────────────────────────────────────────


async def get_tasks_by_horizon(
    session: AsyncSession,
    user_id: int,
    horizon_slug: str,
) -> list[Task]:
    """Return active tasks for a user filtered by horizon slug."""
    hor_result = await session.exec(
        select(Horizon).where(Horizon.user_id == user_id, Horizon.slug == horizon_slug),
    )
    horizon = hor_result.first()
    if horizon is None:
        return []
    result = await session.exec(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.horizon_id == horizon.id,
            Task.status != "done",
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Task.created_at.desc()),  # type: ignore[attr-defined]
    )
    return list(result.all())


async def get_all_notes(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 20,
) -> list[Note]:
    """Return the most recent notes for a user (excludes soft-deleted)."""
    result = await session.exec(
        select(Note)
        .where(
            Note.user_id == user_id,
            Note.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Note.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit),
    )
    return list(result.all())


async def find_note_by_query(
    session: AsyncSession,
    user_id: int,
    query: str,
) -> Note | None:
    """Find a user's note whose title or body matches *query*.

    Case-insensitive LIKE over both ``title`` and ``body`` (notes carry
    most of their text in the body). Returns the most recently created
    match, or ``None``. Voice/text note edits resolve to a single note;
    the executor echoes its title so the user can catch a wrong pick.
    """
    pattern = f"%{_escape_like(query)}%"
    result = await session.exec(
        select(Note)
        .where(
            Note.user_id == user_id,
            Note.deleted_at.is_(None),  # type: ignore[union-attr]
            Note.title.ilike(pattern, escape="\\")  # type: ignore[attr-defined]
            | Note.body.ilike(pattern, escape="\\"),  # type: ignore[union-attr]
        )
        .order_by(Note.created_at.desc()),  # type: ignore[attr-defined]
    )
    return result.first()


async def get_note_by_id(
    session: AsyncSession,
    user_id: int,
    note_id: int,
) -> Note | None:
    """Return a note by ID if it belongs to the user (excludes soft-deleted)."""
    result = await session.exec(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user_id,
            Note.deleted_at.is_(None),  # type: ignore[union-attr]
        ),
    )
    return result.first()


async def update_note_title(
    session: AsyncSession,
    note: Note,
    new_title: str,
    user_id: int,
) -> Note:
    """Rename a note in place."""
    note.title = new_title
    session.add(note)
    await session.flush()
    logger.info("note.renamed", note_id=note.id, user_id=user_id)
    return note


async def update_note_category(
    session: AsyncSession,
    note: Note,
    new_category_id: int | None,
    user_id: int,
) -> Note:
    """Move a note to a different category (or clear it)."""
    note.category_id = new_category_id
    session.add(note)
    await session.flush()
    logger.info(
        "note.recategorized", note_id=note.id, user_id=user_id, new_category_id=new_category_id
    )
    return note


async def delete_note(
    session: AsyncSession,
    note: Note,
    user_id: int,
) -> None:
    """Soft-delete a note by setting ``deleted_at`` (recoverable via Trash)."""
    note.deleted_at = utcnow_naive()
    session.add(note)
    await session.flush()
    logger.info("note.soft_deleted", note_id=note.id, user_id=user_id)


async def get_categories_with_counts(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[Category, int]]:
    """Return user categories with active task count for each.

    Uses a single LEFT OUTER JOIN + GROUP BY so the cost stays O(1) round-trips
    no matter how many categories the user has (was N+1 previously).
    """
    stmt = (
        select(Category, func.count(Task.id))  # type: ignore[arg-type]
        .join(
            Task,
            (Task.category_id == Category.id)
            & (Task.status != "done")
            & (Task.deleted_at.is_(None)),  # type: ignore[union-attr]
            isouter=True,
        )
        .where(Category.user_id == user_id)
        .group_by(Category.id)  # type: ignore[arg-type]
        .order_by(Category.name)
    )
    result = await session.exec(stmt)
    return [(cat, int(count)) for cat, count in result.all()]


async def _active_sibling_count(session: AsyncSession, parent_id: int) -> int:
    """Count non-deleted children of *parent_id* that are not yet done."""
    result = await session.exec(
        select(func.count(Task.id)).where(  # type: ignore[arg-type]
            Task.parent_id == parent_id,
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
            Task.status != "done",
        )
    )
    return int(result.one())


async def _maybe_complete_parent(session: AsyncSession, child: Task, user_id: int) -> Task | None:
    """Auto-complete the parent when its last open subtask is done.

    PR-Subtasks UX: finishing the final child of a project should close
    the project itself — otherwise the parent lingers as "open" with
    a full 3/3 progress chip, which reads as a bug. Returns the parent
    Task if it was just auto-completed (so callers can surface "проект
    закрыт"), else ``None``. Only one level deep — we don't support
    grandchildren.
    """
    if child.parent_id is None:
        return None
    if await _active_sibling_count(session, child.parent_id) > 0:
        return None
    parent = await session.get(Task, child.parent_id)
    if parent is None or parent.status == "done" or parent.deleted_at is not None:
        return None
    parent.status = "done"
    parent.completed_at = utcnow_naive()
    session.add(parent)
    await session.flush()
    if parent.id is not None:
        session.add(
            TaskEvent(
                task_id=parent.id,
                kind="completed",
                payload_json={"source": "subtask_cascade"},
            ),
        )
        await session.flush()
    logger.info("task.parent_auto_completed", parent_id=parent.id, user_id=user_id)
    return parent


async def mark_task_done(
    session: AsyncSession,
    task: Task,
    user_id: int,
) -> Task:
    """Mark a task as done and log the event.

    When *task* is the last open subtask of a parent, the parent is
    auto-completed too (see :func:`_maybe_complete_parent`).
    """
    task.status = "done"
    task.completed_at = utcnow_naive()
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="completed",
                payload_json={"source": "command"},
            ),
        )
        await session.flush()

    await _maybe_complete_parent(session, task, user_id)

    logger.info("task.completed", task_id=task.id, user_id=user_id)
    return task


async def mark_task_undone(
    session: AsyncSession,
    task: Task,
    user_id: int,
) -> Task:
    """Re-open a previously-completed task.

    PR-E recognised-card lets the user *toggle* a task between done and
    pending — tapping ✅ should not be one-way. We reset ``status`` back
    to ``"new"`` (the column's vocabulary; "in_progress" is also valid
    in the schema but unused on this path) and log a ``"reopened"``
    event so the audit trail mirrors :func:`mark_task_done`.
    """
    task.status = "new"
    task.completed_at = None
    session.add(task)
    await session.flush()

    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="reopened",
                payload_json={"source": "summary_toggle"},
            ),
        )
        await session.flush()

    # If this child was reopened, its parent is no longer fully complete —
    # reopen the parent too if it had been auto-completed by the cascade.
    if task.parent_id is not None:
        parent = await session.get(Task, task.parent_id)
        if parent is not None and parent.status == "done" and parent.deleted_at is None:
            parent.status = "new"
            parent.completed_at = None
            session.add(parent)
            await session.flush()
            if parent.id is not None:
                session.add(
                    TaskEvent(
                        task_id=parent.id,
                        kind="reopened",
                        payload_json={"source": "subtask_cascade"},
                    ),
                )
                await session.flush()
            logger.info("task.parent_auto_reopened", parent_id=parent.id, user_id=user_id)

    logger.info("task.reopened", task_id=task.id, user_id=user_id)
    return task


async def delete_task(
    session: AsyncSession,
    task: Task,
    user_id: int,
) -> None:
    """Soft-delete a task by setting ``deleted_at``.

    The record stays in the DB for 24 hours (recoverable via the Trash
    page); a background worker purges it after that.
    """
    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="deleted",
                payload_json={"source": "command"},
            ),
        )
        await session.flush()

    task.deleted_at = utcnow_naive()
    session.add(task)
    await session.flush()
    logger.info("task.soft_deleted", task_id=task.id, user_id=user_id)


async def get_task_by_id(
    session: AsyncSession,
    user_id: int,
    task_id: int,
) -> Task | None:
    """Return a task by ID if it belongs to the user (excludes soft-deleted)."""
    result = await session.exec(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user_id,
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        ),
    )
    return result.first()
