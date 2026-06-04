"""``/api/boards`` — list / create / view / update / delete Excalidraw boards.

Boards are free-form visual canvases (mind-maps) the user draws on
directly in the Mini-App. The list endpoint is deliberately light
(no ``scene_json``); the detail endpoint returns the full scene. All
mutations are owner-scoped — a board belonging to another user 404s
rather than 403 so we don't leak existence.

See ``docs/BOARDS-PLAN.md``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import (
    BOARD_SCENE_MAX_BYTES,
    BoardCreateIn,
    BoardDetailOut,
    BoardOut,
    BoardUpdateIn,
)
from app.db.base import session_scope
from app.db.models import Board, User
from app.shared.logging import get_logger
from app.shared.time import utcnow_naive

logger = get_logger(__name__)

router = APIRouter()


def _board_to_out(board: Board) -> BoardOut:
    if board.id is None:
        raise RuntimeError("Board without id passed to _board_to_out")
    return BoardOut.model_validate(
        {
            "id": board.id,
            "name": board.name,
            "created_at": board.created_at,
            "updated_at": board.updated_at,
        }
    )


def _board_to_detail(board: Board) -> BoardDetailOut:
    if board.id is None:
        raise RuntimeError("Board without id passed to _board_to_detail")
    return BoardDetailOut.model_validate(
        {
            "id": board.id,
            "name": board.name,
            "created_at": board.created_at,
            "updated_at": board.updated_at,
            "scene_json": board.scene_json,
        }
    )


def _reject_oversize_scene(scene_json: dict[str, object] | None) -> None:
    """Raise 413 if the serialised scene exceeds ``BOARD_SCENE_MAX_BYTES``.

    Pydantic can't bound a nested dict's serialised size declaratively,
    so we measure it here before it reaches the DB. Uses ``ensure_ascii``
    off to count real UTF-8 bytes (Cyrillic labels would otherwise be
    under-counted).
    """
    if scene_json is None:
        return
    size = len(json.dumps(scene_json, ensure_ascii=False).encode("utf-8"))
    if size > BOARD_SCENE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"scene too large: {size} bytes (max {BOARD_SCENE_MAX_BYTES})",
        )


@router.get("", response_model=list[BoardOut])
async def list_boards(
    user: User = Depends(current_user),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[BoardOut]:
    """List the user's boards, most-recently-updated first (no scene)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        stmt = (
            select(Board)
            .where(
                Board.user_id == user.id,
                Board.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(Board.updated_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        result = await session.exec(stmt)
        boards = list(result.all())
    return [_board_to_out(b) for b in boards]


@router.post("", response_model=BoardDetailOut, status_code=status.HTTP_201_CREATED)
async def create_board(body: BoardCreateIn, user: User = Depends(current_user)) -> BoardDetailOut:
    """Create a new (empty) board and return it with its fresh id."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        board = Board(
            user_id=user.id,
            name=(body.name or "Без названия"),
        )
        session.add(board)
        await session.flush()
        detail = _board_to_detail(board)
    logger.info("api.boards.created", user_id=user.id, board_id=detail.id)
    return detail


async def _get_owned_board(session: object, user_id: int, board_id: int) -> Board:
    """Fetch a non-deleted board owned by ``user_id`` or raise 404."""
    result = await session.exec(  # type: ignore[attr-defined]
        select(Board).where(
            Board.id == board_id,
            Board.user_id == user_id,
            Board.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    board = result.first()
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    return board


@router.get("/{board_id}", response_model=BoardDetailOut)
async def get_board(board_id: int, user: User = Depends(current_user)) -> BoardDetailOut:
    """Return the full board (with scene) for the canvas view."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        board = await _get_owned_board(session, user.id, board_id)
        return _board_to_detail(board)


@router.patch("/{board_id}", response_model=BoardDetailOut)
async def update_board(
    board_id: int, body: BoardUpdateIn, user: User = Depends(current_user)
) -> BoardDetailOut:
    """Patch name and/or scene. The Mini-App debounce-saves the scene here."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    _reject_oversize_scene(body.scene_json)
    async with session_scope() as session:
        board = await _get_owned_board(session, user.id, board_id)
        if body.name is not None:
            board.name = body.name
        if body.scene_json is not None:
            board.scene_json = body.scene_json
        board.updated_at = utcnow_naive()
        session.add(board)
        await session.flush()
        return _board_to_detail(board)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: int, user: User = Depends(current_user)) -> None:
    """Soft-delete a board (recoverable; mirrors task/note deletion)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        board = await _get_owned_board(session, user.id, board_id)
        board.deleted_at = utcnow_naive()
        session.add(board)
        await session.flush()
    logger.info("api.boards.deleted", user_id=user.id, board_id=board_id)
