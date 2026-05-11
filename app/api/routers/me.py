"""``/api/me`` — current user + settings (read + patch)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import MeOut, MeUpdateIn, UserSettingsOut
from app.bot.services import (
    get_user_settings,
    is_valid_timezone,
    update_user_settings,
)
from app.bot.services.settings import ALLOWED_SETTING_VALUES
from app.db.base import session_scope
from app.db.models import User, UserSettings
from app.shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _settings_to_out(settings: UserSettings | None) -> UserSettingsOut | None:
    if settings is None:
        return None
    return UserSettingsOut(
        critic_mode=settings.critic_mode,
        morning_digest_at=settings.morning_digest_at,
        evening_digest_at=settings.evening_digest_at,
        response_style_source=settings.response_style_source,
        courier_template_style=settings.courier_template_style,
        week_due_semantic=settings.week_due_semantic,
        concretize_tasks=settings.concretize_tasks,
    )


def _user_to_out(user: User, settings: UserSettings | None) -> MeOut:
    if user.id is None:
        # Should be unreachable: ``current_user`` enforces ``id is not None``.
        raise RuntimeError("authenticated user has no id")
    return MeOut(
        id=user.id,
        telegram_id=user.telegram_id,
        display_name=user.display_name,
        tz=user.tz,
        onboarded=user.onboarded_at is not None,
        settings=_settings_to_out(settings),
    )


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
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        settings = await get_user_settings(session, user.id)
    return _user_to_out(user, settings)


@router.patch("", response_model=MeOut)
async def patch_me(body: MeUpdateIn, user: User = Depends(current_user)) -> MeOut:
    """Patch user-level fields and (optionally) nested settings.

    Each supplied field is validated against an explicit allow-list.
    Mutations route through ``app.bot.services`` helpers so the bot's
    ``/settings`` flow and the Mini-App stay byte-identical (a settings
    change here is indistinguishable from one made via inline buttons).

    Returns the updated ``MeOut`` so the client can render fresh state
    without an extra GET round-trip.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        # Re-fetch the user inside this session so SQLAlchemy tracks edits.
        # ``current_user`` returned a detached instance.
        user_row_result = await session.exec(select(User).where(User.id == user.id))
        user_row = user_row_result.first()
        if user_row is None:
            # Should be unreachable: ``current_user`` already validated.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        if body.display_name is not None:
            user_row.display_name = body.display_name
            session.add(user_row)
            await session.flush()
            logger.info("api.me.display_name_updated", user_id=user.id)

        if body.tz is not None:
            if not is_valid_timezone(body.tz):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="invalid timezone",
                )
            user_row.tz = body.tz
            session.add(user_row)
            await session.flush()
            logger.info("api.me.tz_updated", user_id=user.id, tz=body.tz)

        if body.settings is not None:
            patches = body.settings.model_dump(exclude_unset=True)
            for field, raw_value in patches.items():
                if raw_value is None:
                    continue
                # PR-E: ``concretize_tasks`` is exposed as a bool over the
                # wire (cleaner Mini-App ergonomics) but the service
                # layer's allow-list uses the bot's "on"/"off" strings.
                # Translate here so both shapes converge before validation.
                if field == "concretize_tasks" and isinstance(raw_value, bool):
                    value: str = "on" if raw_value else "off"
                else:
                    value = str(raw_value)
                allowed = ALLOWED_SETTING_VALUES.get(field)
                if allowed is None or value not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"invalid value for {field}",
                    )
                updated = await update_user_settings(session, user.id, field, value)
                if updated is None:
                    # Race: settings row missing (pre-onboarding). Bail
                    # before partial writes corrupt the state. The
                    # session_scope rollback unwinds prior mutations.
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="settings not initialised",
                    )

        settings_row = await get_user_settings(session, user.id)
        return _user_to_out(user_row, settings_row)
