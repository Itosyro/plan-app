"""``/api/categories`` — categories (with task counts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import current_user
from app.api.schemas import CategoryCreateIn, CategoryOut
from app.bot.services import (
    get_categories_with_counts,
    get_or_create_category,
)
from app.db.base import session_scope
from app.db.models import User

router = APIRouter()


@router.get("", response_model=list[CategoryOut])
async def list_categories(user: User = Depends(current_user)) -> list[CategoryOut]:
    """Return every category the user has, with active task counts."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        rows = await get_categories_with_counts(session, user.id)
    out: list[CategoryOut] = []
    for cat, count in rows:
        if cat.id is None:
            # Defence: skip ghost rows that somehow lack an id.
            continue
        out.append(CategoryOut(id=cat.id, name=cat.name, task_count=count))
    return out


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreateIn,
    user: User = Depends(current_user),
) -> CategoryOut:
    """Create a category for the user (idempotent — race-safe upsert)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="empty name",
        )
    async with session_scope() as session:
        cat = await get_or_create_category(session, user.id, name)
    if cat.id is None:
        raise RuntimeError("created category has no id")
    return CategoryOut(id=cat.id, name=cat.name, task_count=0)
