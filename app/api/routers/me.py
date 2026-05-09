"""``/api/me`` — current user + settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import MeOut, UserSettingsOut
from app.bot.services import get_user_settings
from app.db.base import session_scope
from app.db.models import User

router = APIRouter()


@router.get("", response_model=MeOut)
async def get_me(user: User = Depends(current_user)) -> MeOut:
    """Return the authenticated user, with their settings inlined.

    The Mini-App calls this on first load to populate the user header
    (display name / timezone) and to know which feature toggles to
    render. ``settings`` is ``None`` only for users created mid-flight
    (before onboarding finished) — that should never happen because
    ``current_user`` already 404s pre-onboarding users, but it's
    cheaper to model it as optional than to raise.
    """
    if user.id is None:
        # Should be unreachable: ``current_user`` enforces ``id is not None``.
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        settings = await get_user_settings(session, user.id)

    settings_out = (
        UserSettingsOut(
            critic_mode=settings.critic_mode,
            morning_digest_at=settings.morning_digest_at,
            evening_digest_at=settings.evening_digest_at,
            response_style_source=settings.response_style_source,
            courier_template_style=settings.courier_template_style,
            week_due_semantic=settings.week_due_semantic,
        )
        if settings is not None
        else None
    )
    return MeOut(
        id=user.id,
        telegram_id=user.telegram_id,
        display_name=user.display_name,
        tz=user.tz,
        onboarded=user.onboarded_at is not None,
        settings=settings_out,
    )
