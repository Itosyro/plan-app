"""``/api/timezones`` — popular timezone choices for the Settings UI.

Mirrors the bot's onboarding keyboard so the Mini-App offers an
identical short-list (and the user is not forced to type an IANA
string). Frontend pairs this with a free-text input as the "Указать
другой" escape hatch.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import TimezoneOut
from app.bot.onboarding import POPULAR_TIMEZONES
from app.db.models import User

router = APIRouter()


@router.get("", response_model=list[TimezoneOut])
async def list_timezones(_user: User = Depends(current_user)) -> list[TimezoneOut]:
    """Return the popular-timezone short-list shared with bot onboarding."""
    return [TimezoneOut(label=label, iana=iana) for label, iana in POPULAR_TIMEZONES]
