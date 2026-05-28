"""``/api/tasks`` — list, view, mutate, delete tasks."""

from __future__ import annotations

from datetime import datetime
from typing import get_args

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.task_splitter import split_task_to_subtasks
from app.api.auth import current_user
from app.api.schemas import (
    HorizonSlug,
    TaskCountsOut,
    TaskDetailOut,
    TaskOut,
    TaskStatus,
    TaskUpdateIn,
)
from app.bot.pinned_today import refresh_pinned_morning
from app.bot.routers._pipeline import get_groq_router
from app.bot.services import (
    delete_task,
    get_task_by_id,
    mark_task_done,
    split_existing_task,
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
    *,
    subtasks_total: int = 0,
    subtasks_done: int = 0,
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
            "title_original": task.title_original,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "due_at": task.due_at,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
            "horizon_slug": horizon_slug,
            "category_id": task.category_id,
            "category_name": category_name,
            "parent_id": task.parent_id,
            "subtasks_total": subtasks_total,
            "subtasks_done": subtasks_done,
        }
    )


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    user: User = Depends(current_user),
    horizon: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    due_at_from: datetime | None = Query(None, description="Inclusive lower bound on due_at."),
    due_at_to: datetime | None = Query(None, description="Exclusive upper bound on due_at."),
    include_done: bool = Query(default=False),
    include_subtasks: bool = Query(default=False),
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
    * ``include_subtasks`` — when ``False`` (default), only top-level
      tasks (``parent_id IS NULL``) are returned. Children are surfaced
      via the parent's ``GET /tasks/{id}`` detail. Set ``True`` for the
      legacy flat list (used in a few admin / debug views).
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        stmt = select(Task, Horizon.slug, Category.name).where(
            Task.user_id == user.id,
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        # ``isouter=True`` so tasks with no horizon (only Notes-likes) still appear.
        stmt = stmt.join(Horizon, Horizon.id == Task.horizon_id, isouter=True)  # type: ignore[arg-type]
        stmt = stmt.join(Category, Category.id == Task.category_id, isouter=True)  # type: ignore[arg-type]

        if not include_subtasks:
            stmt = stmt.where(Task.parent_id.is_(None))  # type: ignore[union-attr]

        if horizon is not None:
            if horizon not in _HORIZON_SLUGS:
                return []
            # ``Horizon.slug`` is per-user; the join above already filters
            # via the FK so the slug equality is well-defined.
            stmt = stmt.where(Horizon.slug == horizon)
        if category_id is not None:
            stmt = stmt.where(Task.category_id == category_id)

        if due_at_from is not None:
            stmt = stmt.where(Task.due_at >= due_at_from)  # type: ignore[operator]
        if due_at_to is not None:
            stmt = stmt.where(Task.due_at < due_at_to)  # type: ignore[operator]

        if status_filter is not None:
            if status_filter not in _TASK_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="bad status",
                )
            stmt = stmt.where(Task.status == status_filter)
        elif not include_done:
            stmt = stmt.where(Task.status != "done")

        # The "Выполненные" screen asks status=done — order by when they
        # were completed (most recent first), falling back to created_at
        # for legacy done rows with a NULL completed_at.
        if status_filter == "done":
            stmt = stmt.order_by(
                Task.completed_at.desc().nullslast(),  # type: ignore[union-attr]
                Task.created_at.desc(),  # type: ignore[attr-defined]
            ).limit(limit)
        else:
            stmt = stmt.order_by(Task.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        result = await session.exec(stmt)
        rows = list(result.all())

        # One aggregate query for subtask counts of the parents we just
        # fetched. Keeps the endpoint O(1) round-trips regardless of how
        # many parents have children. Empty parent_ids list → skip the
        # query entirely.
        parent_ids = [task.id for task, _h, _c in rows if task.id is not None]
        counts = await _aggregate_subtask_counts(session, parent_ids)

    out: list[TaskOut] = []
    for task, horizon_slug, category_name in rows:
        total, done = counts.get(task.id, (0, 0)) if task.id is not None else (0, 0)
        out.append(
            _task_to_out(
                task,
                horizon_slug,
                category_name,
                subtasks_total=total,
                subtasks_done=done,
            )
        )
    return out


async def _aggregate_subtask_counts(
    session: AsyncSession, parent_ids: list[int]
) -> dict[int, tuple[int, int]]:
    """Return ``{parent_id: (total, done)}`` for non-deleted children.

    One ``GROUP BY`` over ``tasks`` filtered by ``parent_id IN (...)`` —
    avoids the N+1 the list endpoint would otherwise have. Parents with
    no children are absent from the result (caller defaults to ``(0, 0)``).
    """
    if not parent_ids:
        return {}
    # ``SUM(CASE WHEN status='done' THEN 1 ELSE 0 END)`` works on both
    # Postgres and SQLite. Wrapping in ``COALESCE`` so the empty-bucket
    # case sums to ``0`` instead of ``NULL``.
    done_expr = func.coalesce(
        func.sum(case((Task.status == "done", 1), else_=0)),  # type: ignore[arg-type]
        0,
    )
    stmt = (
        select(Task.parent_id, func.count(Task.id), done_expr)  # type: ignore[arg-type]
        .where(
            Task.parent_id.in_(parent_ids),  # type: ignore[union-attr]
            Task.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .group_by(Task.parent_id)  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    out: dict[int, tuple[int, int]] = {}
    for parent_id, total, done in result.all():
        if parent_id is None:
            continue
        out[int(parent_id)] = (int(total or 0), int(done or 0))
    return out


@router.get("/counts", response_model=TaskCountsOut)
async def task_counts(user: User = Depends(current_user)) -> TaskCountsOut:
    """Return per-horizon counts of open (non-``done``) tasks.

    One round-trip serves all horizon badges in the Mini-App so we
    don't paginate every tab on first paint. ``done`` and ``cancelled``
    are excluded — those live in archive flows, not the list. Tasks
    with no horizon (legacy rows or notes-likes) are aggregated under
    ``no_horizon`` so the totals never silently drop.

    The route is registered **before** ``/{task_id}`` so FastAPI
    matches ``GET /api/tasks/counts`` to this handler instead of
    coercing ``"counts"`` into an int and returning 422.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        # Single GROUP BY on ``horizons.slug``. ``isouter=True`` keeps
        # tasks without a horizon visible (we bucket them as ``None``
        # and surface as ``no_horizon`` in the response below).
        stmt = (
            select(Horizon.slug, func.count(Task.id))  # type: ignore[arg-type]
            .join(Horizon, Horizon.id == Task.horizon_id, isouter=True)  # type: ignore[arg-type]
            .where(
                Task.user_id == user.id,
                Task.status != "done",
                Task.status != "cancelled",
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .group_by(Horizon.slug)
        )
        result = await session.exec(stmt)
        rows = list(result.all())

    payload: dict[str, int] = dict.fromkeys(get_args(HorizonSlug), 0)
    payload["no_horizon"] = 0
    for slug, n in rows:
        if slug is None:
            payload["no_horizon"] = int(n)
        elif slug in payload:
            payload[slug] = int(n)
        # Unknown slugs (shouldn't happen — schema is fixed) are dropped
        # silently rather than raising; callers see only the documented
        # buckets.
    return TaskCountsOut.model_validate(payload)


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


@router.get("/{task_id}", response_model=TaskDetailOut)
async def get_task(
    task_id: int,
    user: User = Depends(current_user),
) -> TaskDetailOut:
    """Return one task by id with hydrated subtasks.

    404 when missing or owned by another user. Children are returned
    in the ``subtasks`` array, each as a full ``TaskOut`` so the
    Mini-App can render checkboxes / titles / status without a second
    fetch. The parent's ``subtasks_total`` and ``subtasks_done`` are
    populated from the same list so the UI shows "1/3 готово" without
    re-counting client-side.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")
    task, horizon_slug, category_name = await _load_task_owned(user.id, task_id)

    async with session_scope() as session:
        if task.id is None:
            raise RuntimeError("Task without id passed to get_task")
        child_stmt = (
            select(Task, Horizon.slug, Category.name)
            .where(
                Task.parent_id == task.id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .join(Horizon, Horizon.id == Task.horizon_id, isouter=True)  # type: ignore[arg-type]
            .join(Category, Category.id == Task.category_id, isouter=True)  # type: ignore[arg-type]
            .order_by(Task.created_at.asc())  # type: ignore[attr-defined]
        )
        child_rows = list((await session.exec(child_stmt)).all())

    children = [_task_to_out(c, cslug, cname) for c, cslug, cname in child_rows]
    total = len(children)
    done = sum(1 for c in children if c.status == "done")
    parent = _task_to_out(
        task,
        horizon_slug,
        category_name,
        subtasks_total=total,
        subtasks_done=done,
    )
    return TaskDetailOut.model_validate(
        {**parent.model_dump(), "subtasks": [c.model_dump() for c in children]}
    )


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

        if body.description is not None:
            # Empty string clears the field; the API does not mark it
            # as ``"unset"`` separately from ``None`` to keep the
            # surface boring (PATCH body without the key = no change).
            task.description = body.description or None

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

        # ``category_id`` distinguishes an explicit null (clear the
        # category — kanban "Без категории" drop) from an omitted key
        # (no change). ``model_fields_set`` carries that intent that a
        # bare ``is not None`` check would lose.
        if "category_id" in body.model_fields_set:
            if body.category_id is not None:
                cat_check = await session.exec(
                    select(Category).where(
                        Category.id == body.category_id, Category.user_id == user.id
                    )
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


@router.post(
    "/{task_id}/split",
    response_model=list[TaskOut],
    status_code=status.HTTP_201_CREATED,
)
async def split_task(
    task_id: int,
    user: User = Depends(current_user),
) -> list[TaskOut]:
    """Break a task into 2–5 atomic subtasks via LLM, persist & return them.

    Used by the «Входящие» review card. Errors:

    * 404 — task not found / belongs to another user / soft-deleted.
    * 409 ``"task is already a subtask"`` — ``parent_id`` is not null
      (only one level of nesting is allowed).
    * 409 ``"task already split"`` — the task already has children;
      splitting again would silently duplicate steps.
    * 503 — Groq router not configured (no API keys at boot).
    * 422 ``"task is already atomic, nothing to split"`` — the LLM
      decided the task can't be usefully decomposed.
    """
    if user.id is None:
        raise RuntimeError("authenticated user has no id")

    async with session_scope() as session:
        task = await get_task_by_id(session, user.id, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        if task.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task is already a subtask",
            )
        # Cheap existence check — we only need to know whether at least
        # one non-deleted child exists, not how many.
        existing_children = await session.exec(
            select(func.count())
            .select_from(Task)
            .where(
                Task.parent_id == task.id,
                Task.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        if (existing_children.first() or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="task already split",
            )

    groq_router = get_groq_router()
    if groq_router is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI temporarily unavailable",
        )

    titles = await split_task_to_subtasks(groq_router, task.title)
    if not titles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="task is already atomic, nothing to split",
        )

    out: list[TaskOut] = []
    async with session_scope() as session:
        # Re-load the parent inside the fresh session before mutating —
        # the original ``task`` is detached from the prior session_scope.
        parent = await get_task_by_id(session, user.id, task_id)
        if parent is None:
            # Vanishingly unlikely (the parent was here moments ago) but
            # if it raced with a delete we surface a clean 404.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        children = await split_existing_task(session, parent, titles)

        # Re-hydrate horizon slug + category name once — children all
        # inherit them from the parent, so we look them up just once.
        horizon_slug: str | None = None
        category_name: str | None = None
        if parent.horizon_id is not None:
            hor_res = await session.exec(
                select(Horizon.slug).where(Horizon.id == parent.horizon_id)
            )
            horizon_slug = hor_res.first()
        if parent.category_id is not None:
            cat_res = await session.exec(
                select(Category.name).where(Category.id == parent.category_id)
            )
            category_name = cat_res.first()

        for child in children:
            out.append(_task_to_out(child, horizon_slug, category_name))
    return out


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
