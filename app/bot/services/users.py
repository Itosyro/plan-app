"""User management — CRUD + onboarding."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import User, UserSettings
from app.shared.logging import get_logger
from app.shared.time import utcnow_naive

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

    Sets the user's name + timezone and marks ``onboarded_at``. If a
    ``UserSettings`` row for this user does not yet exist, creates one
    with the documented defaults; otherwise leaves the existing row
    intact (we don't want to wipe the user's tweaks like
    ``critic_mode`` / digest times when they re-run ``/start``).

    Idempotent on re-onboarding: a user who wipes their chat and runs
    ``/start`` again must not crash with ``IntegrityError`` on the
    ``UserSettings.user_id`` PK. See
    ``docs/REVIEW-2026-05-09-v2.md::R-NEW-I-3``.
    """
    user.display_name = display_name
    user.tz = tz
    user.onboarded_at = utcnow_naive()
    session.add(user)

    assert user.id is not None, "user must be flushed before complete_onboarding()"
    result = await session.exec(
        select(UserSettings).where(UserSettings.user_id == user.id),
    )
    settings = result.first()
    if settings is None:
        settings = UserSettings(user_id=user.id)
        session.add(settings)
    await session.flush()
    return settings
