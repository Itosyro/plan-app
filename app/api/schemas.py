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
    description: str | None = Field(default=None, max_length=4096)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    horizon_slug: HorizonSlug | None = None
    category_id: int | None = None
    due_at: datetime | None = None


class TaskCountsOut(_ConfiguredModel):
    """Counts of open (non-``done``) tasks per horizon.

    Returned by ``GET /api/tasks/counts`` so the Mini-App can render
    `Сегодня (3) / Завтра (1) / Неделя (8)` badges on the horizon
    pills without paginating each tab.

    Fields mirror ``HorizonSlug`` literals 1-to-1 plus a ``no_horizon``
    bucket for tasks whose horizon was never resolved (legacy rows or
    Notes-likes). Default 0 keeps clients oblivious to whether the
    user has any task at all yet.
    """

    today: int = 0
    tomorrow: int = 0
    week: int = 0
    month: int = 0
    year: int = 0
    someday: int = 0
    no_horizon: int = 0


# ── /api/notes ───────────────────────────────────────────────────────


class NoteOut(_ConfiguredModel):
    id: int
    title: str
    body: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    created_at: datetime


class NoteCreateIn(BaseModel):
    """Body for ``POST /api/notes``.

    The Mini-App lets users create notes directly (a «new note» FAB on
    the Notes tab). Bot-side flows go through ``app.bot.services.notes``
    which writes the row itself; this schema is API-only.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=256)
    body: str | None = Field(default=None, max_length=8192)
    category_id: int | None = None


class NoteUpdateIn(BaseModel):
    """Body for ``PATCH /api/notes/{id}``.

    Every field is optional; only the supplied fields are mutated. The
    handler validates each value explicitly rather than ``setattr``-ing
    in a loop, matching ``TaskUpdateIn`` (defensive-programming G-1).
    Empty string in ``body`` clears the field; ``None`` means «don't
    touch this key».
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=256)
    body: str | None = Field(default=None, max_length=8192)
    category_id: int | None = None


# ── /api/me ──────────────────────────────────────────────────────────


class UserSettingsOut(_ConfiguredModel):
    critic_mode: str
    morning_digest_at: str
    evening_digest_at: str
    response_style_source: str
    courier_template_style: str
    week_due_semantic: str


class UserSettingsUpdateIn(BaseModel):
    """Body for ``PATCH /api/me`` ``settings`` field.

    Every key is optional; only the supplied fields are mutated. Each
    value is validated against the same allow-list as the bot
    ``/settings`` callbacks (``ALLOWED_SETTING_VALUES``). Unknown values
    bubble up as 422 from the service layer; unknown keys are rejected
    here by ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    critic_mode: str | None = None
    morning_digest_at: str | None = None
    evening_digest_at: str | None = None
    response_style_source: str | None = None
    courier_template_style: str | None = None
    week_due_semantic: str | None = None


class MeUpdateIn(BaseModel):
    """Body for ``PATCH /api/me``.

    All fields optional; only supplied keys are mutated. ``display_name``
    must be non-empty when present (``None`` means "don't touch it").
    ``tz`` is validated as a real IANA timezone server-side.
    ``settings`` is a nested patch against ``UserSettings``.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    tz: str | None = Field(default=None, min_length=1, max_length=64)
    settings: UserSettingsUpdateIn | None = None


class MeOut(_ConfiguredModel):
    id: int
    telegram_id: int
    display_name: str | None = None
    tz: str
    onboarded: bool
    settings: UserSettingsOut | None = None


# ── /api/timezones ───────────────────────────────────────────────────


class TimezoneOut(_ConfiguredModel):
    """A single popular-timezone choice for the Settings UI.

    Mirrors ``app/bot/onboarding.py::POPULAR_TIMEZONES``. ``label`` is
    the friendly Russian city name shown in the picker; ``iana`` is the
    persisted value.
    """

    label: str
    iana: str


# ── /api/inbox ───────────────────────────────────────────────────────


class InboxEntryOut(_ConfiguredModel):
    id: int
    kind: str
    raw_text: str | None = None
    transcript: str | None = None
    received_at: datetime


# ── /api/trash ───────────────────────────────────────────────────────

TrashKind = Literal["task", "note"]


class TrashItemOut(_ConfiguredModel):
    """One soft-deleted record shown in the Trash page."""

    id: int
    kind: TrashKind
    title: str
    deleted_at: datetime
    category_name: str | None = None


class TrashCountsOut(_ConfiguredModel):
    """Aggregate counts for the trash badge."""

    tasks: int = 0
    notes: int = 0


__all__ = [
    "CategoryCreateIn",
    "CategoryOut",
    "HorizonOut",
    "InboxEntryOut",
    "MeOut",
    "MeUpdateIn",
    "NoteCreateIn",
    "NoteOut",
    "NoteUpdateIn",
    "TaskCountsOut",
    "TaskOut",
    "TaskPriority",
    "TaskStatus",
    "TaskUpdateIn",
    "TimezoneOut",
    "TrashCountsOut",
    "TrashItemOut",
    "TrashKind",
    "UserSettingsOut",
    "UserSettingsUpdateIn",
]
