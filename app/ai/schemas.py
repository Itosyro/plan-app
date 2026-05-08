"""Pydantic models for the AI pipeline input / output.

Phase 2.1: Splitter schemas.
Phase 2.2: Classifier + ResolvedTime schemas.
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
