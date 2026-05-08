"""Pydantic models for the AI pipeline input / output.

Phase 2.1 ships the Splitter schemas only. Classifier, Critic and Courier
schemas land in Phase 2.2 / 2.3.
"""

from __future__ import annotations

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
