"""``/api/tasks`` — list, view, mutate, delete tasks."""

from __future__ import annotations

from typing import get_args

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import select

from app.api.auth import current_user
from app.api.schemas import HorizonSlug, TaskOut, TaskStatus, TaskUpdateIn
from app.bot.pinned_today import refresh_pinned_morning
from app.bot.services import (
    delete_task,
    get_task_by_id,
    mark_task_done,
    update_task_category,
    update_task_horizon,
)
from app.db.base import session_scope
from app.db.models import Category, Horizon, Task, User
from app.shared.logging import get_logger
from app.shared.time import to_naive_utc

logger = get_logger(__name__)

router = APIRouter()

_HORIZON_SLUGS: frozenset[str] = frozenset(get_args(HorizonSlug))
_TASK_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))


def _task_to_out(
    task: Task,
    horizon_slug: str | None,
    category_name: str | None,
) -> TaskOut:
    """Build a ``TaskOut`` response from a hydrated ORM tuple.

    The status / horizon literals were already validated when written
    (settings allow-lists + ``ClassifierResult`` schema), so casting via
    ``model_validate`` is safe — we shape the dict explicitly here so
    type-checkers see every field.
    """
    if task.id is None:
        raise RuntimeError("Task without id passed to _task_to_out")
    return TaskOut.model_validate(
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "due_at": task.due_at,
            "created_at": task.created_at,
            "horizon_slug": horizon_slug,
            "category_id": task.category_id,
            "category_name": category_name,
        }
    )


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    user: User = Depends(current_user),
    horizon: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    include_done: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[TaskOut]:
    """List the user's tasks with optional filters.

    * ``horizon`` — slug filter (today/tomorrow/...). Unknown slugs
      yield an empty list so the Mini-App never crashes on a stale tab.
    * ``category_id`` — only tasks with this category.
    * ``status`` — exact status match (overrides ``include_done``).
    * ``include_done`` — when no ``status`` is set, controls whether
      completed tasks are returned. Default ``False`` matches the
      Russian inbox semantics (done tasks live in archive, not list).
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        stmt = select(Task, Horizon.slug, Category.name).where(Task.user_id == user.id)
        # ``isouter=True`` so tasks with no horizon (only Notes-likes) still appear.
        stmt = stmt.join(Horizon, Horizon.id == Task.horizon_id, isouter=True)  # type: ignore[arg-type]
        stmt = stmt.join(Category, Category.id == Task.category_id, isouter=True)  # type: ignore[arg-type]

        if horizon is not None:
            if horizon not in _HORIZON_SLUGS:
                return []
            # ``Horizon.slug`` is per-user; the join above already filters
            # via the FK so the slug equality is well-defined.
            stmt = stmt.where(Horizon.slug == horizon)
        if category_id is not None:
            stmt = stmt.where(Task.category_id == category_id)

        if status_filter is not None:
            if status_filter not in _TASK_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="bad status",
                )
            stmt = stmt.where(Task.status == status_filter)
        elif not include_done:
            stmt = stmt.where(Task.status != "done")

        stmt = stmt.order_by(Task.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        result = await session.exec(stmt)
        rows = list(result.all())

    return [
        _task_to_out(task, horizon_slug, category_name)
        for task, horizon_slug, category_name in rows
    ]


async def _load_task_owned(user_id: int, task_id: int) -> tuple[Task, str | None, str | None]:
    """Load a task by id, raising 404 if missing or owned by someone else."""
    async with session_scope() as session:
        task = await get_task_by_id(session, user_id, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        horizon_slug: str | None = None
        if task.horizon_id is not None:
            hor_res = await session.exec(select(Horizon.slug).where(Horizon.id == task.horizon_id))
            horizon_slug = hor_res.first()
        category_name: str | None = None
        if task.category_id is not None:
            cat_res = await session.exec(
                select(Category.name).where(Category.id == task.category_id)
            )
            category_name = cat_res.first()
    return task, horizon_slug, category_name


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    user: User = Depends(current_user),
) -> TaskOut:
    """Return one task by id (404 if missing or owned by another user)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    task, horizon_slug, category_name = await _load_task_owned(user.id, task_id)
    return _task_to_out(task, horizon_slug, category_name)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(
    task_id: int,
    body: TaskUpdateIn,
    request: Request,
    user: User = Depends(current_user),
) -> TaskOut:
    """Update specific fields of a task.

    Only the supplied fields are mutated. Each mutation goes through the
    same ``app.bot.services`` helper the Telegram callbacks use, so the
    audit trail (``TaskEvent``) and side-effects (reminder scheduling)
    stay consistent across both surfaces.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    horizon_slug: str | None = None
    category_name: str | None = None
    refresh_pin = False

    async with session_scope() as session:
        task = await get_task_by_id(session, user.id, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

        if body.title is not None:
            task.title = body.title

        if body.priority is not None:
            task.priority = body.priority

        if body.due_at is not None:
            task.due_at = to_naive_utc(body.due_at)

        if body.status is not None:
            if body.status == "done":
                await mark_task_done(session, task, user.id)
                # Phase 6.3: trigger a pinned-digest refresh after commit
                # so the strikethrough state is live across surfaces.
                refresh_pin = True
            else:
                task.status = body.status

        if body.horizon_slug is not None:
            await update_task_horizon(session, task, body.horizon_slug, user.id)

        if body.category_id is not None:
            cat_check = await session.exec(
                select(Category).where(Category.id == body.category_id, Category.user_id == user.id)
            )
            if cat_check.first() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="category not found"
                )
            await update_task_category(session, task, body.category_id, user.id)

        # Persist any unrelated direct-attribute mutations (title/priority/due_at).
        session.add(task)
        await session.flush()

        # Re-hydrate joined fields for the response.
        if task.horizon_id is not None:
            hor_res = await session.exec(select(Horizon.slug).where(Horizon.id == task.horizon_id))
            horizon_slug = hor_res.first()
        if task.category_id is not None:
            cat_res = await session.exec(
                select(Category.name).where(Category.id == task.category_id)
            )
            category_name = cat_res.first()

    # Refresh the pinned morning digest in a fresh transaction (the prior
    # session_scope is closed, so the ``mark_task_done`` write is durable
    # before we render the new digest text). Best-effort — never breaks
    # the API response.
    if refresh_pin and user.id is not None:
        bot = getattr(request.app.state, "bot", None)
        if bot is not None:
            try:
                async with session_scope() as session:
                    await refresh_pinned_morning(bot, session, user.id)
            except Exception:
                logger.warning("api.refresh_pinned_failed", user_id=user.id, exc_info=True)

    return _task_to_out(task, horizon_slug, category_name)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: int,
    user: User = Depends(current_user),
) -> None:
    """Delete a task (404 if missing or owned by another user)."""
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    async with session_scope() as session:
        task = await get_task_by_id(session, user.id, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        await delete_task(session, task, user.id)
    return None
