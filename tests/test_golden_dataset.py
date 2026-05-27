"""CI-safe tests for the golden-eval dataset and scoring logic (P2.7).

No network: the live classifier eval lives in ``scripts/golden_eval.py``
and is gated behind ``GROQ_API_KEYS``. Here we only validate the curated
dataset and unit-test the pure scoring functions in ``app.ai.golden``.
"""

from __future__ import annotations

from pathlib import Path

from app.ai.golden import (
    GoldenCase,
    aggregate,
    load_cases,
    score_case,
)
from app.ai.schemas import ClassifierResult

_DATASET = Path(__file__).resolve().parent / "golden" / "ru" / "cases.json"

_HORIZONS = frozenset({"today", "tomorrow", "week", "month", "year", "someday"})
_PRIORITIES = frozenset({"low", "medium", "high"})


def _result(*, is_task: bool, horizon: str, priority: str) -> ClassifierResult:
    """Hand-build a ClassifierResult (open-vocab fields are filler)."""
    return ClassifierResult(
        category_name="личное",
        horizon=horizon,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        is_task=is_task,
        confidence=0.9,
        title="заглушка",
        reminder_offsets=None,
    )


# ── Dataset validation ───────────────────────────────────────────────


def test_dataset_has_enough_cases() -> None:
    cases = load_cases(_DATASET)
    assert len(cases) >= 50


def test_dataset_fields_in_valid_domains() -> None:
    cases = load_cases(_DATASET)
    for case in cases:
        assert isinstance(case.text, str)
        assert case.text.strip(), f"empty text in case: {case!r}"
        assert isinstance(case.is_task, bool), f"is_task not bool: {case!r}"
        assert case.horizon in _HORIZONS, f"bad horizon: {case!r}"
        assert case.priority in _PRIORITIES, f"bad priority: {case!r}"


def test_dataset_has_no_duplicate_texts() -> None:
    cases = load_cases(_DATASET)
    texts = [c.text for c in cases]
    assert len(texts) == len(set(texts)), "duplicate text entries in dataset"


def test_dataset_covers_variety() -> None:
    """Sanity: the set spans all horizons and both is_task values."""
    cases = load_cases(_DATASET)
    assert {c.horizon for c in cases} == _HORIZONS
    assert {c.is_task for c in cases} == {True, False}
    assert {c.priority for c in cases} == _PRIORITIES


# ── score_case ───────────────────────────────────────────────────────


def test_score_case_all_correct() -> None:
    expected = GoldenCase(text="t", is_task=True, horizon="today", priority="high")
    predicted = _result(is_task=True, horizon="today", priority="high")
    assert score_case(expected, predicted) == {
        "is_task": True,
        "horizon": True,
        "priority": True,
    }


def test_score_case_each_field_wrong() -> None:
    expected = GoldenCase(text="t", is_task=True, horizon="today", priority="high")

    wrong_is_task = _result(is_task=False, horizon="today", priority="high")
    assert score_case(expected, wrong_is_task) == {
        "is_task": False,
        "horizon": True,
        "priority": True,
    }

    wrong_horizon = _result(is_task=True, horizon="week", priority="high")
    assert score_case(expected, wrong_horizon) == {
        "is_task": True,
        "horizon": False,
        "priority": True,
    }

    wrong_priority = _result(is_task=True, horizon="today", priority="low")
    assert score_case(expected, wrong_priority) == {
        "is_task": True,
        "horizon": True,
        "priority": False,
    }


# ── aggregate ────────────────────────────────────────────────────────


def test_aggregate_empty() -> None:
    assert aggregate([]) == {
        "is_task": 0.0,
        "horizon": 0.0,
        "priority": 0.0,
        "overall": 0.0,
    }


def test_aggregate_fractions() -> None:
    results = [
        {"is_task": True, "horizon": True, "priority": True},  # all correct
        {"is_task": True, "horizon": False, "priority": True},  # horizon off
        {"is_task": False, "horizon": True, "priority": False},  # two off
        {"is_task": True, "horizon": True, "priority": True},  # all correct
    ]
    acc = aggregate(results)
    assert acc["is_task"] == 0.75  # 3/4
    assert acc["horizon"] == 0.75  # 3/4
    assert acc["priority"] == 0.75  # 3/4
    assert acc["overall"] == 0.5  # 2/4 all-correct


def test_aggregate_overall_requires_all_three() -> None:
    results = [
        {"is_task": True, "horizon": True, "priority": False},
        {"is_task": True, "horizon": False, "priority": True},
    ]
    acc = aggregate(results)
    assert acc["is_task"] == 1.0
    assert acc["overall"] == 0.0
