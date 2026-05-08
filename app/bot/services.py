"""Domain services used by handlers.

Handlers stay thin: they collect input, validate it, and delegate to these
functions. This makes them easier to unit-test (no aiogram fixtures needed)
and keeps SQL out of the routers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult
from app.db.models import (
    AiRun,
    Category,
    Horizon,
    InboxEntry,
    Note,
    Task,
    TaskEvent,
    TelegramUpdate,
    User,
    UserSettings,
)
from app.shared.logging import get_logger

logger = get_logger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    lang_code: str | None = None,
) -> tuple[User, bool]:
    """Look up a user by ``telegram_id`` or create a stub.

    Returns ``(user, created)``. The newly-created user has no name and
    no timezone yet — those are filled in by the onboarding wizard.
    For an existing user, refresh ``lang_code`` if Telegram now reports a
    different value (so locale-sensitive features stay in sync).
    """
    result = await session.exec(select(User).where(User.telegram_id == telegram_id))
    user = result.first()
    if user is not None:
        if lang_code is not None and lang_code != user.lang_code:
            user.lang_code = lang_code
            session.add(user)
            await session.flush()
        return user, False

    user = User(telegram_id=telegram_id, lang_code=lang_code)
    session.add(user)
    await session.flush()
    return user, True


def is_valid_timezone(tz: str) -> bool:
    """Return True if ``tz`` is a known IANA timezone name."""
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


async def complete_onboarding(
    session: AsyncSession,
    user: User,
    *,
    display_name: str,
    tz: str,
) -> UserSettings:
    """Persist the onboarding result.

    Sets the user's name + timezone, marks ``onboarded_at``, and creates a
    fresh ``UserSettings`` row with the documented defaults.
    """
    user.display_name = display_name
    user.tz = tz
    user.onboarded_at = datetime.now(UTC)
    session.add(user)

    assert user.id is not None, "user must be flushed before complete_onboarding()"
    settings = UserSettings(user_id=user.id)
    session.add(settings)
    await session.flush()
    return settings


async def is_update_processed(session: AsyncSession, update_id: int) -> bool:
    """Idempotency guard — return True if we've already seen this update_id."""
    result = await session.exec(select(TelegramUpdate).where(TelegramUpdate.update_id == update_id))
    return result.first() is not None


async def record_update(
    session: AsyncSession,
    *,
    update_id: int,
    user_id: int | None,
    kind: str | None,
) -> None:
    """Mark a Telegram update as processed."""
    session.add(TelegramUpdate(update_id=update_id, user_id=user_id, kind=kind))
    await session.flush()


async def store_inbox_text(
    session: AsyncSession,
    *,
    user_id: int,
    raw_text: str,
    telegram_message_id: int | None,
) -> InboxEntry:
    """Persist an incoming text message into the inbox."""
    entry = InboxEntry(
        user_id=user_id,
        kind="text",
        raw_text=raw_text,
        telegram_message_id=telegram_message_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def store_inbox_voice(
    session: AsyncSession,
    *,
    user_id: int,
    transcript: str,
    telegram_message_id: int | None,
) -> InboxEntry:
    """Persist an incoming voice message (with transcript) into the inbox."""
    entry = InboxEntry(
        user_id=user_id,
        kind="voice",
        transcript=transcript,
        telegram_message_id=telegram_message_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_user_settings(
    session: AsyncSession,
    user_id: int,
) -> UserSettings | None:
    """Return the user's settings row, or None if not onboarded yet."""
    result = await session.exec(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    return result.first()


# ── Phase 2.2 persistence ────────────────────────────────────────────


async def get_or_create_category(
    session: AsyncSession,
    user_id: int,
    name: str,
) -> Category:
    """Find or create a category for the user."""
    result = await session.exec(
        select(Category).where(Category.user_id == user_id, Category.name == name),
    )
    cat = result.first()
    if cat is not None:
        return cat
    cat = Category(user_id=user_id, name=name)
    session.add(cat)
    await session.flush()
    return cat


async def get_or_create_horizon(
    session: AsyncSession,
    user_id: int,
    slug: str,
) -> Horizon:
    """Find or create a horizon for the user."""
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
    hor = Horizon(user_id=user_id, slug=slug, label=label)
    session.add(hor)
    await session.flush()
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
        select(Category).where(Category.user_id == user_id).order_by(Category.name),  # type: ignore[union-attr]
    )
    return list(result.all())


async def persist_classification(
    session: AsyncSession,
    *,
    user_id: int,
    cr: ClassifierResult,
    due_at: datetime | None,
    inbox_id: int | None,
) -> Task | Note:
    """Persist a ClassifierResult as a Task or Note row."""
    cat = await get_or_create_category(session, user_id, cr.category_name)
    hor = await get_or_create_horizon(session, user_id, cr.horizon)

    if cr.is_task:
        row: Task | Note = Task(
            user_id=user_id,
            category_id=cat.id,
            horizon_id=hor.id,
            title=cr.title,
            priority=cr.priority,
            due_at=due_at,
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

    if cr.is_task:
        if not isinstance(row, Task) or row.id is None:
            raise RuntimeError("Expected a flushed Task row after persist")
        session.add(
            TaskEvent(task_id=row.id, kind="created", payload_json={"source": "classifier"}),
        )
        await session.flush()

    logger.info(
        "persist.done",
        user_id=user_id,
        is_task=cr.is_task,
        category=cr.category_name,
        title=cr.title,
    )
    return row


# ── Phase 2.3d reorder ────────────────────────────────────────────────


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
            Task.title.ilike(pattern, escape="\\"),  # type: ignore[union-attr]
            Task.status != "done",
        )
        .order_by(Task.created_at.desc()),  # type: ignore[union-attr]
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


# ── Phase 3c settings ─────────────────────────────────────────────────


REMINDER_PRESETS: dict[str, dict[str, list[int]]] = {
    "minimal": {"same_day": [15], "multi_day": [60]},
    "default": {"same_day": [60, 15], "multi_day": [1440, 60]},
    "extra": {"same_day": [180, 60, 15], "multi_day": [1440, 240, 60]},
}

# Allowed values for each user-editable setting field. Mirrors the options
# rendered by ``app/bot/routers/settings.py::SETTING_OPTIONS`` and is the
# authoritative validation gate at the service layer — a malformed callback
# (replayed, edited, or maliciously crafted) is rejected before it touches
# the database.
ALLOWED_SETTING_VALUES: dict[str, frozenset[str]] = {
    "critic_mode": frozenset({"always", "confidence", "never"}),
    "morning_digest_at": frozenset({"07:00", "08:00", "09:00", "10:00"}),
    "evening_digest_at": frozenset({"20:00", "21:00", "22:00", "23:00"}),
    "response_style_source": frozenset({"formal", "casual", "mix"}),
    "week_due_semantic": frozenset({"deadline_sunday", "deadline_saturday", "spread_evenly"}),
}


def reminder_preset_from_offsets(offsets: dict[str, list[int]] | dict[str, object]) -> str:
    """Return the preset name matching ``offsets`` (custom if no match)."""
    same = list(offsets.get("same_day") or [])
    multi = list(offsets.get("multi_day") or [])
    for name, preset in REMINDER_PRESETS.items():
        if preset["same_day"] == same and preset["multi_day"] == multi:
            return name
    return "custom"


async def update_user_settings(
    session: AsyncSession,
    user_id: int,
    field: str,
    value: str,
) -> UserSettings | None:
    """Update a single setting and return the latest UserSettings row.

    Most fields live on ``UserSettings``. Two virtual fields are handled
    specially:

    * ``tz`` — written to ``User.tz`` (after ``is_valid_timezone`` check).
    * ``reminder_preset`` — expanded via ``REMINDER_PRESETS`` and written
      to ``UserSettings.default_reminder_offsets``.
    """
    settings = await get_user_settings(session, user_id)
    if settings is None:
        return None

    if field == "tz":
        if not is_valid_timezone(value):
            return None
        user_result = await session.exec(select(User).where(User.id == user_id))
        user = user_result.first()
        if user is None:
            return None
        user.tz = value
        session.add(user)
        await session.flush()
        logger.info("settings.updated", user_id=user_id, field=field, value=value)
        return settings

    if field == "reminder_preset":
        preset = REMINDER_PRESETS.get(value)
        if preset is None:
            return None
        settings.default_reminder_offsets = dict(preset)
        session.add(settings)
        await session.flush()
        logger.info("settings.updated", user_id=user_id, field=field, value=value)
        return settings

    if field not in ALLOWED_SETTING_VALUES or value not in ALLOWED_SETTING_VALUES[field]:
        return None

    if field == "critic_mode":
        settings.critic_mode = value
    elif field == "morning_digest_at":
        settings.morning_digest_at = value
    elif field == "evening_digest_at":
        settings.evening_digest_at = value
    elif field == "response_style_source":
        settings.response_style_source = value
    elif field == "week_due_semantic":
        settings.week_due_semantic = value
    else:  # pragma: no cover - exhaustive above
        return None
    session.add(settings)
    await session.flush()
    logger.info("settings.updated", user_id=user_id, field=field, value=value)
    return settings


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


# ── Phase 3a view queries ─────────────────────────────────────────────


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
        )
        .order_by(Task.created_at.desc()),  # type: ignore[union-attr]
    )
    return list(result.all())


async def get_all_notes(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 20,
) -> list[Note]:
    """Return the most recent notes for a user."""
    result = await session.exec(
        select(Note)
        .where(Note.user_id == user_id)
        .order_by(Note.created_at.desc())  # type: ignore[union-attr]
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
        select(Category, func.count(Task.id))
        .join(
            Task,
            (Task.category_id == Category.id) & (Task.status != "done"),
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


async def delete_task(
    session: AsyncSession,
    task: Task,
    user_id: int,
) -> None:
    """Delete a task and log the event."""
    if task.id is not None:
        session.add(
            TaskEvent(
                task_id=task.id,
                kind="deleted",
                payload_json={"source": "command"},
            ),
        )
        await session.flush()

    await session.delete(task)
    await session.flush()
    logger.info("task.deleted", task_id=task.id, user_id=user_id)


async def get_task_by_id(
    session: AsyncSession,
    user_id: int,
    task_id: int,
) -> Task | None:
    """Return a task by ID if it belongs to the user."""
    result = await session.exec(
        select(Task).where(Task.id == task_id, Task.user_id == user_id),
    )
    return result.first()


async def log_ai_run(
    session: AsyncSession,
    *,
    user_id: int,
    inbox_id: int | None,
    stage: str,
    model: str,
    key_index: int = 0,
    latency_ms: int = 0,
    tokens: int = 0,
    status: str = "ok",
    error: str | None = None,
) -> AiRun:
    """Log an AI pipeline call to the ai_runs table."""
    run = AiRun(
        user_id=user_id,
        inbox_id=inbox_id,
        stage=stage,
        model=model,
        key_index=key_index,
        latency_ms=latency_ms,
        tokens=tokens,
        status=status,
        error=error,
    )
    session.add(run)
    await session.flush()
    return run
