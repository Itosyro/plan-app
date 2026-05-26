"""Golden-eval scoring for the intent classifier (ROADMAP P2.7).

Pure, dependency-light helpers used by the offline eval runner
(``scripts/golden_eval.py``) and by the CI-safe unit tests
(``tests/test_golden_dataset.py``).

The classifier produces an open-vocabulary Russian ``category_name`` —
we deliberately do **not** score that field. We score the three
structured fields that have a well-defined finite domain: ``is_task``,
``horizon`` and ``priority``.

Nothing here touches the network. ``load_cases`` is the only I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.schemas import ClassifierResult

SCORED_FIELDS = ("is_task", "horizon", "priority")


@dataclass(frozen=True)
class GoldenCase:
    """A single curated example with its expected structured labels."""

    text: str
    is_task: bool
    horizon: str
    priority: str


def load_cases(path: str | Path) -> list[GoldenCase]:
    """Load the golden dataset from a JSON array file.

    Each element must carry ``text``, ``is_task``, ``horizon`` and
    ``priority``; any extra keys (e.g. ``note``) are ignored.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        GoldenCase(
            text=item["text"],
            is_task=item["is_task"],
            horizon=item["horizon"],
            priority=item["priority"],
        )
        for item in raw
    ]


def score_case(expected: GoldenCase, predicted: ClassifierResult) -> dict[str, bool]:
    """Return per-field correctness for one prediction.

    Keys are :data:`SCORED_FIELDS`; each value is ``True`` when the
    predicted field matches the expected label.
    """
    return {
        "is_task": expected.is_task == predicted.is_task,
        "horizon": expected.horizon == predicted.horizon,
        "priority": expected.priority == predicted.priority,
    }


def aggregate(results: list[dict[str, bool]]) -> dict[str, float]:
    """Aggregate per-case scores into accuracy fractions.

    Returns one fraction per scored field plus ``overall`` — the share
    of cases where *all three* fields were correct. Empty input yields
    all-zero accuracies (no division by zero).
    """
    total = len(results)
    if total == 0:
        return dict.fromkeys((*SCORED_FIELDS, "overall"), 0.0)

    acc: dict[str, float] = {}
    for field in SCORED_FIELDS:
        acc[field] = sum(1 for r in results if r[field]) / total
    acc["overall"] = sum(1 for r in results if all(r.values())) / total
    return acc
