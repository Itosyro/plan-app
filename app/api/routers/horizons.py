"""``/api/horizons`` — list of horizons known to the user."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import HorizonOut
from app.db.base import session_scope
from app.db.models import Horizon, User

router = APIRouter()

# Canonical labels for horizons that may not yet have a row in the
# ``horizons`` table for this user (the table is populated lazily on
# first classification, so a brand-new user has none). The Mini-App
# wants to render an empty "Сегодня" tab even before any task lands
# in it — we always respond with the full vocabulary.
_BUILTIN_HORIZONS: list[tuple[str, str]] = [
    ("today", "Сегодня"),
    ("tomorrow", "Завтра"),
    ("week", "На этой неделе"),
    ("month", "В этом месяце"),
    ("year", "В этом году"),
    ("someday", "Когда-нибудь"),
]


@router.get("", response_model=list[HorizonOut])
async def list_horizons(user: User = Depends(current_user)) -> list[HorizonOut]:
    """Return every horizon the Mini-App should render as a tab.

    Strategy: start from the canonical builtin vocabulary and overlay
    any user-specific labels that have already been auto-created (so a
    custom future label survives the response). Slugs not in the
    builtin list still appear at the end so admin tooling that pokes
    new horizons doesn't lose them.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        result = await session.exec(select(Horizon).where(Horizon.user_id == user.id))
        existing = {row.slug: row.label for row in result.all()}

    seen: set[str] = set()
    out: list[HorizonOut] = []
    for slug, label in _BUILTIN_HORIZONS:
        out.append(HorizonOut(slug=slug, label=existing.get(slug, label)))
        seen.add(slug)
    for slug, label in existing.items():
        if slug not in seen:
            out.append(HorizonOut(slug=slug, label=label))
    return out
