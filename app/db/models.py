"""SQLModel tables.

Phase 1: ``users``, ``user_settings``, ``inbox_entries``, ``telegram_updates``.
Phase 2.2: ``categories``, ``horizons``, ``tasks``, ``notes``, ``ai_runs``,
``task_events``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Timezone-aware UTC ``now`` (``datetime.utcnow`` is deprecated)."""
    return datetime.now(UTC)


def _default_offsets() -> dict[str, list[int]]:
    """Default reminder offsets (минуты до события).

    same_day: за 1 час и за 15 минут.
    multi_day: за 1 сутки и за 1 час.
    См. ``docs/PROGRESS.md`` (Phase 0 closing decisions).
    """
    return {"same_day": [60, 15], "multi_day": [1440, 60]}


class User(SQLModel, table=True):
    """Telegram user we have ever seen."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    telegram_id: int = Field(
        sa_column=Column(BigInteger, unique=True, index=True, nullable=False),
    )
    display_name: str | None = Field(default=None, max_length=128)
    lang_code: str | None = Field(default=None, max_length=8)
    tz: str = Field(default="UTC", max_length=64)
    onboarded_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class UserSettings(SQLModel, table=True):
    """Per-user preferences set during onboarding (later edited via /settings)."""

    __tablename__ = "user_settings"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    critic_mode: str = Field(default="confidence", max_length=16)
    critic_confidence_threshold: float = Field(default=0.7)
    default_reminder_offsets: dict[str, Any] = Field(
        default_factory=_default_offsets,
        sa_column=Column(JSON, nullable=False),
    )
    morning_digest_at: str = Field(default="08:00", max_length=5)
    evening_digest_at: str = Field(default="21:00", max_length=5)
    response_style_source: str = Field(default="mix", max_length=16)
    week_due_semantic: str = Field(default="deadline_sunday", max_length=24)


class InboxEntry(SQLModel, table=True):
    """Raw incoming text / voice transcript (one row per inbound message).

    Phase 1 stores text only; Phase 2 will populate ``transcript`` for voice
    messages (Whisper output).
    """

    __tablename__ = "inbox_entries"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str = Field(max_length=16)  # "text" | "voice" | "command"
    raw_text: str | None = Field(default=None)
    transcript: str | None = Field(default=None)
    telegram_message_id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    received_at: datetime = Field(default_factory=_utcnow, nullable=False)


class TelegramUpdate(SQLModel, table=True):
    """Idempotency cache: every Telegram ``update_id`` we've ever processed.

    Telegram retries the webhook on any non-2xx response, so without this
    table a slow handler could process the same update twice.
    """

    __tablename__ = "telegram_updates"

    update_id: int = Field(
        sa_column=Column(BigInteger, primary_key=True),
    )
    user_id: int | None = Field(default=None, foreign_key="users.id")
    kind: str | None = Field(default=None, max_length=32)
    processed_at: datetime = Field(default_factory=_utcnow, nullable=False)


# ── Phase 2.2 ────────────────────────────────────────────────────────


class Category(SQLModel, table=True):
    """Per-user category created on-the-fly by the Classifier."""

    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Horizon(SQLModel, table=True):
    """Per-user time horizon (today, tomorrow, week, …)."""

    __tablename__ = "horizons"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    slug: str = Field(max_length=32)
    label: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Task(SQLModel, table=True):
    """A classified task extracted from user input."""

    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int | None = Field(default=None, foreign_key="categories.id")
    horizon_id: int | None = Field(default=None, foreign_key="horizons.id")
    title: str = Field(max_length=256)
    description: str | None = Field(default=None)
    priority: str = Field(default="medium", max_length=16)
    due_at: datetime | None = Field(default=None)
    status: str = Field(default="new", max_length=16)
    source_inbox_id: int | None = Field(default=None, foreign_key="inbox_entries.id")
    needs_clarification: bool = Field(default=False)
    confidence: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Note(SQLModel, table=True):
    """A classified note extracted from user input."""

    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int | None = Field(default=None, foreign_key="categories.id")
    title: str = Field(max_length=256)
    body: str | None = Field(default=None)
    source_inbox_id: int | None = Field(default=None, foreign_key="inbox_entries.id")
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class AiRun(SQLModel, table=True):
    """Log entry for every LLM call."""

    __tablename__ = "ai_runs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    inbox_id: int | None = Field(default=None, foreign_key="inbox_entries.id")
    stage: str = Field(max_length=32)
    model: str = Field(max_length=64)
    key_index: int = Field(default=0)
    latency_ms: int = Field(default=0)
    tokens: int = Field(default=0)
    status: str = Field(default="ok", max_length=16)
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class TaskEvent(SQLModel, table=True):
    """Audit trail for task state changes."""

    __tablename__ = "task_events"

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    kind: str = Field(max_length=32)
    payload_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
