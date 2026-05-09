"""``/api/inbox/{id}`` — view a single inbox entry (raw text or transcript)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import InboxEntryOut
from app.db.base import session_scope
from app.db.models import InboxEntry, User

router = APIRouter()


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
