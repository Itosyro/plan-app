"""Domain services used by handlers.

Handlers stay thin: they collect input, validate it, and delegate to these
functions. This makes them easier to unit-test (no aiogram fixtures needed)
and keeps SQL out of the routers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

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
    """
    result = await session.exec(select(User).where(User.telegram_id == telegram_id))
    user = result.first()
    if user is not None:
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
