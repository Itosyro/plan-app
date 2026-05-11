"""``/api/notes`` — list / view / delete notes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import NoteCreateIn, NoteOut, NoteUpdateIn
from app.db.base import session_scope
from app.db.models import Category, Note, User
from app.shared.time import utcnow_naive

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
        stmt = select(Note, Category.name).where(
            Note.user_id == user.id,
            Note.deleted_at.is_(None),  # type: ignore[union-attr]
        )
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
            .where(Note.id == note_id, Note.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        row = result.first()
        if row is None or row[0].user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        note, category_name = row
    return _note_to_out(note, category_name)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreateIn = Body(...),
    user: User = Depends(current_user),
) -> NoteOut:
    """Create a new note. Mini-App «new note» FAB calls this.

    Bot-side flows have their own writer in ``app.bot.services.notes``
    that runs LLM classification first; this endpoint is the plain
    user-driven path — it trusts the title/body verbatim.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    category_name: str | None = None
    async with session_scope() as session:
        if body.category_id is not None:
            cat_result = await session.exec(
                select(Category).where(
                    Category.id == body.category_id,
                    Category.user_id == user.id,
                )
            )
            cat = cat_result.first()
            if cat is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="category not found",
                )
            category_name = cat.name

        note = Note(
            user_id=user.id,
            title=body.title,
            body=body.body or None,
            category_id=body.category_id,
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)

    return _note_to_out(note, category_name)


@router.patch("/{note_id}", response_model=NoteOut)
async def patch_note(
    note_id: int,
    body: NoteUpdateIn = Body(...),
    user: User = Depends(current_user),
) -> NoteOut:
    """Mutate a note. Only supplied fields change.

    Empty string in ``body`` clears the note body; missing key keeps it.
    Changing ``category_id`` validates ownership of the target category.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        result = await session.exec(
            select(Note).where(Note.id == note_id, Note.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        note = result.first()
        if note is None or note.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

        if body.title is not None:
            note.title = body.title
        if body.body is not None:
            note.body = body.body or None
        if body.category_id is not None:
            cat_result = await session.exec(
                select(Category).where(
                    Category.id == body.category_id,
                    Category.user_id == user.id,
                )
            )
            cat = cat_result.first()
            if cat is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="category not found",
                )
            note.category_id = body.category_id

        await session.flush()
        await session.refresh(note)

        category_name: str | None = None
        if note.category_id is not None:
            cat_lookup = await session.exec(
                select(Category.name).where(Category.id == note.category_id)
            )
            row = cat_lookup.first()
            category_name = row if isinstance(row, str) else (row[0] if row else None)

    return _note_to_out(note, category_name)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, user: User = Depends(current_user)) -> None:
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        result = await session.exec(
            select(Note).where(Note.id == note_id, Note.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        note = result.first()
        if note is None or note.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        note.deleted_at = utcnow_naive()
        session.add(note)
        await session.flush()
    return None
