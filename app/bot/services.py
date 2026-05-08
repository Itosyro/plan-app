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

from app.db.models import InboxEntry, TelegramUpdate, User, UserSettings


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
