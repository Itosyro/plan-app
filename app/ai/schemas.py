"""Pydantic models for the AI pipeline input / output.

Phase 2.1: Splitter schemas.
Phase 2.2: Classifier + ResolvedTime schemas.
Phase 2.3: CriticVerdict.
Phase 2.3d: ReorderRequest.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IntentUnit(BaseModel):
    """A single atomic intent extracted by the Splitter."""

    text: str = Field(description="Original Russian text of the intent.")


class SplitterResult(BaseModel):
    """Output of the Splitter LLM call — a list of intent units."""

    units: list[IntentUnit] = Field(
        default_factory=list,
        description="Atomic intent units extracted from the user message.",
    )


# ── Phase 2.2 ────────────────────────────────────────────────────────


class ClassifierResult(BaseModel):
    """Output of the Classifier LLM call."""

    category_name: str = Field(description="Category name in Russian")
    horizon: Literal["today", "tomorrow", "week", "month", "year", "someday"] = Field(
        description="Horizon slug: today/tomorrow/week/month/year/someday",
    )
    priority: Literal["low", "medium", "high"] = Field(
        description="Priority: low/medium/high",
    )
    is_task: bool = Field(description="True if task, False if note")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    title: str = Field(description="Short title in Russian, max 50 chars")
    reminder_offsets: list[int] | None = Field(
        default=None,
        description="Minutes before due_at to remind (only if user explicitly asked)",
    )
    # PR-E "make it concrete" (опционально): когда классификатор видит,
    # что задача абстрактная / большая ("научиться играть на гитаре",
    # "разобраться с английским"), он может предложить конкретный
    # первый шаг — короткое действие на 5–15 минут, с которого реально
    # можно начать сегодня. Если задача и так конкретная — ``null``.
    # Применяется только если у юзера ``UserSettings.concretize_tasks``
    # включён (см. :class:`app.db.models.UserSettings`).
    first_step: str | None = Field(
        default=None,
        description=(
            "Optional concrete first action (5–15 min) for abstract goals. "
            "Null when the task is already concrete."
        ),
    )


class ResolvedTime(BaseModel):
    """Output of the time resolver (pure Python, no LLM)."""

    original_text: str
    resolved_dt: datetime | None = None
    is_reminder: bool = False
    horizon_hint: str | None = None


class ReminderInfo(BaseModel):
    """Extracted reminder from user text (pure Python, no LLM)."""

    fire_at: datetime
    original_text: str


# ── Phase 2.3 ────────────────────────────────────────────────────────


class CriticVerdict(BaseModel):
    """Output of the Critic LLM call.

    The critic reviews the classifier output and either approves it
    or returns a corrected ``ClassifierResult``.
    """

    approved: bool = Field(description="True if classifier result is correct")
    reason: str = Field(description="Short explanation in Russian (why approved or what was wrong)")
    corrected: ClassifierResult | None = Field(
        default=None,
        description="Corrected result if approved=False, null if approved=True",
    )


# ── Phase 2.3d ───────────────────────────────────────────────────────


class ReorderRequest(BaseModel):
    """Output of the reorder detection LLM call."""

    is_reorder: bool = Field(description="True if this is a task reorder/reschedule request")
    task_query: str | None = Field(
        default=None,
        description="Search string to find the task (Russian, original wording)",
    )
    target_horizon: Literal["today", "tomorrow", "week", "month", "year", "someday"] | None = Field(
        default=None,
        description="New horizon for the task",
    )
    target_raw: str | None = Field(
        default=None,
        description="Raw time expression from the user",
    )


# ── PR-I1: Edit intent detection ─────────────────────────────────────


class EditIntent(BaseModel):
    """Output of the intent detection LLM call (PR-I1..I3).

    Determines whether the user wants to *edit* an existing task
    (complete / delete / reopen / rename / change deadline / priority /
    category) or *create* a new one (the default path).
    """

    intent: Literal[
        "create",
        "reorder_horizon",
        "reorder_time",
        "complete",
        "delete",
        "reopen",
        "rename",
        "set_due",
        "set_priority",
        "set_category",
        "list_done",
        "none",
    ] = Field(description="Detected user intent")
    task_query: str | None = Field(
        default=None,
        description="Search string to find the target task (Russian)",
    )
    new_horizon: Literal["today", "tomorrow", "week", "month", "year", "someday"] | None = Field(
        default=None,
        description="Target horizon for reorder_horizon intent",
    )
    new_due_raw: str | None = Field(
        default=None,
        description="Raw time expression for reorder_time / set_due",
    )
    new_title: str | None = Field(
        default=None,
        description="New title for rename intent",
    )
    new_priority: Literal["high", "medium", "low"] | None = Field(
        default=None,
        description="New priority for set_priority intent",
    )
    new_category: str | None = Field(
        default=None,
        description="New category name for set_category intent",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in the detected intent",
    )
