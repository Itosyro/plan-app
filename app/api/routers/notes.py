"""``/api/notes`` — list / view / delete notes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import NoteOut
from app.db.base import session_scope
from app.db.models import Category, Note, User

router = APIRouter()


def _note_to_out(note: Note, category_name: str | None) -> NoteOut:
    if note.id is None:
        raise RuntimeError("Note without id passed to _note_to_out")
    return NoteOut.model_validate(
        {
            "id": note.id,
            "title": note.title,
            "body": note.body,
            "category_id": note.category_id,
            "category_name": category_name,
            "created_at": note.created_at,
        }
    )


@router.get("", response_model=list[NoteOut])
async def list_notes(
    user: User = Depends(current_user),
    category_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[NoteOut]:
    """List the user's notes, most-recent first."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        stmt = select(Note, Category.name).where(Note.user_id == user.id)
        stmt = stmt.join(Category, Category.id == Note.category_id, isouter=True)  # type: ignore[arg-type]
        if category_id is not None:
            stmt = stmt.where(Note.category_id == category_id)
        stmt = stmt.order_by(Note.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        result = await session.exec(stmt)
        rows = list(result.all())
    return [_note_to_out(note, category_name) for note, category_name in rows]


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: int, user: User = Depends(current_user)) -> NoteOut:
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        result = await session.exec(
            select(Note, Category.name)
            .join(Category, Category.id == Note.category_id, isouter=True)  # type: ignore[arg-type]
            .where(Note.id == note_id)
        )
        row = result.first()
        if row is None or row[0].user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        note, category_name = row
    return _note_to_out(note, category_name)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, user: User = Depends(current_user)) -> None:
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        result = await session.exec(select(Note).where(Note.id == note_id))
        note = result.first()
        if note is None or note.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        await session.delete(note)
        await session.flush()
    return None
