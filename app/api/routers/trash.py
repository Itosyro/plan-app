"""``/api/trash`` — list, restore, and hard-delete soft-deleted records."""

from __future__ import annotations

from typing import get_args

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import TrashCountsOut, TrashItemOut, TrashKind
from app.db.base import session_scope
from app.db.models import Category, Note, Task, User

router = APIRouter()

_VALID_KINDS: frozenset[str] = frozenset(get_args(TrashKind))


@router.get("", response_model=list[TrashItemOut])
async def list_trash(user: User = Depends(current_user)) -> list[TrashItemOut]:
    """Return all soft-deleted tasks and notes for the user."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    items: list[TrashItemOut] = []

    async with session_scope() as session:
        task_rows = list(
            (
                await session.exec(
                    select(Task, Category.name)
                    .join(Category, Category.id == Task.category_id, isouter=True)  # type: ignore[arg-type]
                    .where(
                        Task.user_id == user.id,
                        Task.deleted_at.is_not(None),  # type: ignore[union-attr]
                    )
                    .order_by(Task.deleted_at.desc())  # type: ignore[union-attr]
                )
            ).all()
        )
        for task, cat_name in task_rows:
            if task.id is None or task.deleted_at is None:
                continue
            items.append(
                TrashItemOut(
                    id=task.id,
                    kind="task",
                    title=task.title,
                    deleted_at=task.deleted_at,
                    category_name=cat_name,
                )
            )

        note_rows = list(
            (
                await session.exec(
                    select(Note, Category.name)
                    .join(Category, Category.id == Note.category_id, isouter=True)  # type: ignore[arg-type]
                    .where(
                        Note.user_id == user.id,
                        Note.deleted_at.is_not(None),  # type: ignore[union-attr]
                    )
                    .order_by(Note.deleted_at.desc())  # type: ignore[union-attr]
                )
            ).all()
        )
        for note, cat_name in note_rows:
            if note.id is None or note.deleted_at is None:
                continue
            items.append(
                TrashItemOut(
                    id=note.id,
                    kind="note",
                    title=note.title,
                    deleted_at=note.deleted_at,
                    category_name=cat_name,
                )
            )

    items.sort(key=lambda x: x.deleted_at, reverse=True)
    return items


@router.get("/counts", response_model=TrashCountsOut)
async def trash_counts(user: User = Depends(current_user)) -> TrashCountsOut:
    """Return the number of soft-deleted items per kind."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        task_result = await session.exec(
            select(Task).where(
                Task.user_id == user.id,
                Task.deleted_at.is_not(None),  # type: ignore[union-attr]
            )
        )
        task_count = len(list(task_result.all()))

        note_result = await session.exec(
            select(Note).where(
                Note.user_id == user.id,
                Note.deleted_at.is_not(None),  # type: ignore[union-attr]
            )
        )
        note_count = len(list(note_result.all()))

    return TrashCountsOut(tasks=task_count, notes=note_count)


@router.post("/{kind}/{item_id}/restore", status_code=status.HTTP_200_OK)
async def restore_item(
    kind: str,
    item_id: int,
    user: User = Depends(current_user),
) -> dict[str, str]:
    """Restore a soft-deleted item by clearing ``deleted_at``."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad kind")

    async with session_scope() as session:
        if kind == "task":
            task_result = await session.exec(
                select(Task).where(
                    Task.id == item_id,
                    Task.deleted_at.is_not(None),  # type: ignore[union-attr]
                )
            )
            task = task_result.first()
            if task is None or task.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
            task.deleted_at = None
            session.add(task)
            await session.flush()
        else:
            note_result = await session.exec(
                select(Note).where(
                    Note.id == item_id,
                    Note.deleted_at.is_not(None),  # type: ignore[union-attr]
                )
            )
            note = note_result.first()
            if note is None or note.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
            note.deleted_at = None
            session.add(note)
            await session.flush()

    return {"status": "restored"}


@router.delete("/{kind}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_item(
    kind: str,
    item_id: int,
    user: User = Depends(current_user),
) -> None:
    """Permanently delete a soft-deleted item (no recovery)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad kind")

    async with session_scope() as session:
        if kind == "task":
            task_result = await session.exec(
                select(Task).where(
                    Task.id == item_id,
                    Task.deleted_at.is_not(None),  # type: ignore[union-attr]
                )
            )
            task = task_result.first()
            if task is None or task.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
            await session.delete(task)
            await session.flush()
        else:
            note_result = await session.exec(
                select(Note).where(
                    Note.id == item_id,
                    Note.deleted_at.is_not(None),  # type: ignore[union-attr]
                )
            )
            note = note_result.first()
            if note is None or note.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
            await session.delete(note)
            await session.flush()

    return None
