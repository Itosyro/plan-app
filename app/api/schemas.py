"""Pydantic v2 schemas for the Mini-App REST API.

Each schema mirrors a slice of the underlying SQLModel rows but is a
plain ``BaseModel`` so it can carry computed fields (``horizon_slug``
joined from the ``horizons`` table, ``category_name`` from
``categories``) without leaking the full ORM object across the API
boundary. Use ``model_validate(...)`` from `_helpers.py` to convert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Status / priority / horizon vocabularies are explicit literals so
# clients (and the OpenAPI consumers in tests) can rely on them.
TaskStatus = Literal["new", "in_progress", "done", "cancelled"]
TaskPriority = Literal["low", "medium", "high"]
HorizonSlug = Literal["today", "tomorrow", "week", "month", "year", "someday"]


class _ConfiguredModel(BaseModel):
    """Base for response models — strict, immutable-by-default, JSON-friendly."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


# ── /api/horizons ────────────────────────────────────────────────────


class HorizonOut(_ConfiguredModel):
    slug: str
    label: str


# ── /api/categories ──────────────────────────────────────────────────


class CategoryOut(_ConfiguredModel):
    id: int
    name: str
    task_count: int = 0


class CategoryCreateIn(BaseModel):
    """Body for ``POST /api/categories``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)


# ── /api/tasks ───────────────────────────────────────────────────────


class TaskOut(_ConfiguredModel):
    id: int
    title: str
    description: str | None = None
    priority: TaskPriority
    status: TaskStatus
    due_at: datetime | None = None
    created_at: datetime
    horizon_slug: HorizonSlug | None = None
    category_id: int | None = None
    category_name: str | None = None


class TaskUpdateIn(BaseModel):
    """Body for ``PATCH /api/tasks/{id}``.

    Every field is optional; only the supplied fields are mutated. Each
    value is validated against an explicit allow-list — there is no
    ``getattr(task, field, ...)`` setattr loop in the handler, in line
    with our defensive-programming skill (G-1).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=256)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    horizon_slug: HorizonSlug | None = None
    category_id: int | None = None
    due_at: datetime | None = None


# ── /api/notes ───────────────────────────────────────────────────────


class NoteOut(_ConfiguredModel):
    id: int
    title: str
    body: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    created_at: datetime


# ── /api/me ──────────────────────────────────────────────────────────


class UserSettingsOut(_ConfiguredModel):
    critic_mode: str
    morning_digest_at: str
    evening_digest_at: str
    response_style_source: str
    courier_template_style: str
    week_due_semantic: str


class MeOut(_ConfiguredModel):
    id: int
    telegram_id: int
    display_name: str | None = None
    tz: str
    onboarded: bool
    settings: UserSettingsOut | None = None


# ── /api/inbox ───────────────────────────────────────────────────────


class InboxEntryOut(_ConfiguredModel):
    id: int
    kind: str
    raw_text: str | None = None
    transcript: str | None = None
    received_at: datetime


__all__ = [
    "CategoryCreateIn",
    "CategoryOut",
    "HorizonOut",
    "InboxEntryOut",
    "MeOut",
    "NoteOut",
    "TaskOut",
    "TaskPriority",
    "TaskStatus",
    "TaskUpdateIn",
    "UserSettingsOut",
]
