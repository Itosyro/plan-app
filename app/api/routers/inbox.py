"""``/api/inbox`` — view inbox entries and run the «Входящие» review flow.

* ``GET /api/inbox/pending`` — entries flagged ``needs_review`` with the
  tasks they produced (the review tab).
* ``POST /api/inbox/{id}/confirm`` — keep the checked tasks, drop the
  rest, and clear the flag.
* ``GET /api/inbox/{id}`` — raw text / transcript for a single entry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.routers.notes import _note_to_out
from app.api.routers.tasks import _task_to_out
from app.api.schemas import InboxConfirmIn, InboxEntryOut, InboxReviewOut
from app.bot.services import delete_note, delete_task
from app.db.base import session_scope
from app.db.models import Category, Horizon, InboxEntry, Note, Task, User

router = APIRouter()


@router.get("/pending", response_model=list[InboxReviewOut])
async def list_pending_reviews(
    user: User = Depends(current_user),
) -> list[InboxReviewOut]:
    """Return inbox entries awaiting review, newest first.

    Each entry carries its still-present top-level tasks (soft-deleted
    ones are excluded). Entries whose tasks were all deleted elsewhere
    are skipped so the tab never shows an empty card.

    Declared before ``/{entry_id}`` so FastAPI doesn't coerce
    ``"pending"`` into an int and 422.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        entries = (
            await session.exec(
                select(InboxEntry)
                .where(
                    InboxEntry.user_id == user.id,
                    InboxEntry.needs_review.is_(True),  # type: ignore[attr-defined]
                )
                .order_by(InboxEntry.received_at.desc())  # type: ignore[attr-defined]
            )
        ).all()

        reviews: list[InboxReviewOut] = []
        for entry in entries:
            rows = (
                await session.exec(
                    select(Task, Horizon.slug, Category.name)
                    .where(
                        Task.source_inbox_id == entry.id,
                        Task.parent_id.is_(None),  # type: ignore[union-attr]
                        Task.deleted_at.is_(None),  # type: ignore[union-attr]
                    )
                    .join(Horizon, Horizon.id == Task.horizon_id, isouter=True)  # type: ignore[arg-type]
                    .join(Category, Category.id == Task.category_id, isouter=True)  # type: ignore[arg-type]
                    .order_by(Task.created_at.asc())  # type: ignore[attr-defined]
                )
            ).all()
            note_rows = (
                await session.exec(
                    select(Note, Category.name)
                    .where(
                        Note.source_inbox_id == entry.id,
                        Note.deleted_at.is_(None),  # type: ignore[union-attr]
                    )
                    .join(Category, Category.id == Note.category_id, isouter=True)  # type: ignore[arg-type]
                    .order_by(Note.created_at.asc())  # type: ignore[attr-defined]
                )
            ).all()
            if not rows and not note_rows:
                continue
            tasks_out = [_task_to_out(t, hslug, cname) for t, hslug, cname in rows]
            notes_out = [_note_to_out(n, cname) for n, cname in note_rows]
            reviews.append(
                InboxReviewOut.model_validate(
                    {
                        "id": entry.id,
                        "kind": entry.kind,
                        "text": entry.transcript or entry.raw_text,
                        "received_at": entry.received_at,
                        "tasks": [t.model_dump() for t in tasks_out],
                        "notes": [n.model_dump() for n in notes_out],
                    }
                )
            )
    return reviews


@router.post("/{entry_id}/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_review(
    entry_id: int,
    body: InboxConfirmIn,
    user: User = Depends(current_user),
) -> None:
    """Resolve a review: keep the checked tasks, soft-delete the rest.

    Clears ``needs_review`` so the entry leaves the tab. 404 when the
    entry is missing or owned by another user.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    keep = set(body.keep_task_ids)
    keep_notes = set(body.keep_note_ids)
    async with session_scope() as session:
        entry = await session.get(InboxEntry, entry_id)
        if entry is None or entry.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="inbox entry not found"
            )

        rows = (
            await session.exec(
                select(Task).where(
                    Task.source_inbox_id == entry_id,
                    Task.user_id == user.id,
                    Task.parent_id.is_(None),  # type: ignore[union-attr]
                    Task.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
        ).all()
        for task in rows:
            if task.id not in keep:
                await delete_task(session, task, user.id)

        note_rows = (
            await session.exec(
                select(Note).where(
                    Note.source_inbox_id == entry_id,
                    Note.user_id == user.id,
                    Note.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
        ).all()
        for note in note_rows:
            if note.id not in keep_notes:
                await delete_note(session, note, user.id)

        entry.needs_review = False
        session.add(entry)
    return None


@router.get("/{entry_id}", response_model=InboxEntryOut)
async def get_inbox_entry(
    entry_id: int,
    user: User = Depends(current_user),
) -> InboxEntryOut:
    """Return the raw text + transcript for an inbox entry the user owns."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        result = await session.exec(select(InboxEntry).where(InboxEntry.id == entry_id))
        entry = result.first()
        if entry is None or entry.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="inbox entry not found"
            )
    return InboxEntryOut.model_validate(
        {
            "id": entry.id,
            "kind": entry.kind,
            "raw_text": entry.raw_text,
            "transcript": entry.transcript,
            "received_at": entry.received_at,
        }
    )
