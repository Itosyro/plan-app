"""Task / Note / Category / Horizon CRUD + classification persistence + reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
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
    await session.execute(stmt)
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
    await session.execute(stmt)
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


# ── Classification persistence ────────────────────────────────────────


FIRST_STEP_PREFIX = "Шаг 1: "


def _build_task_description(cr: ClassifierResult, *, concretize: bool) -> str | None:
    """Compose ``Task.description`` from the classifier output.

    PR-E "make it concrete": when ``concretize`` is true and the
    classifier returned a non-empty ``first_step`` for an abstract task,
    we prepend "Шаг 1: <first_step>" so the user has an obvious starting
    point in the Mini-App task detail. When the feature is off, or the
    classifier didn't emit a first step, the column stays ``None`` (we
    have no other source for ``description`` yet).
    """
    if not concretize:
        return None
    step = (cr.first_step or "").strip()
    if not step:
        return None
    return f"{FIRST_STEP_PREFIX}{step}"


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
        row: Task | Note = Task(
            user_id=user_id,
            category_id=cat.id,
            horizon_id=hor.id,
            title=cr.title,
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

    logger.info(
        "persist.done",
        user_id=user_id,
        is_task=cr.is_task,
        category=cr.category_name,
        title=cr.title,
        reminders_created=reminders_created,
    )
    return row


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
    new_category_id: int,
    user_id: int,
) -> Task:
    """Move a task to a different category and log the event."""
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


async def mark_task_done(
    session: AsyncSession,
    task: Task,
    user_id: int,
) -> Task:
    """Mark a task as done and log the event."""
    task.status = "done"
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
