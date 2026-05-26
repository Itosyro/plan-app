"""Golden-eval runner for the intent classifier (ROADMAP P2.7).

Runs the live classifier over the curated Russian phrase set and prints
a per-field + overall accuracy report. This calls Groq (a real LLM), so
it is **gated** behind the ``GROQ_API_KEYS`` env var and is meant to be
run manually / locally — never in CI.

Usage::

    GROQ_API_KEYS=gsk_xxx,gsk_yyy uv run python scripts/golden_eval.py

When ``GROQ_API_KEYS`` is unset the script prints a skip notice and
exits 0, so it is safe to wire into any pipeline.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow ``python scripts/golden_eval.py`` from the repo root: put the
# project root (one level above this script) on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.classifier import classify_intent
from app.ai.golden import (
    SCORED_FIELDS,
    GoldenCase,
    aggregate,
    load_cases,
    score_case,
)
from app.ai.router import GroqKeyRouter
from app.ai.schemas import ClassifierResult

_DATASET = Path(__file__).resolve().parent.parent / "tests" / "golden" / "ru" / "cases.json"
_USER_TZ = "Europe/Moscow"
_MAX_MISMATCHES = 15


async def _run(router: GroqKeyRouter, cases: list[GoldenCase]) -> None:
    results: list[dict[str, bool]] = []
    mismatches: list[tuple[GoldenCase, ClassifierResult, dict[str, bool]]] = []

    for case in cases:
        predicted = await classify_intent(
            router,
            case.text,
            None,
            [],
            _USER_TZ,
        )
        score = score_case(case, predicted)
        results.append(score)
        if not all(score.values()):
            mismatches.append((case, predicted, score))

    acc = aggregate(results)

    print(f"\nGolden eval — {len(cases)} cases\n" + "=" * 40)
    for field in SCORED_FIELDS:
        print(f"  {field:<10} accuracy: {acc[field]:.1%}")
    print(f"  {'overall':<10} accuracy: {acc['overall']:.1%}  (all 3 fields correct)")

    if mismatches:
        print(f"\nMismatches ({len(mismatches)} total, showing up to {_MAX_MISMATCHES}):")
        for case, predicted, score in mismatches[:_MAX_MISMATCHES]:
            wrong = [f for f, ok in score.items() if not ok]
            print(f"  - {case.text!r}")
            for field in wrong:
                exp = getattr(case, field)
                got = getattr(predicted, field)
                print(f"      {field}: expected {exp!r}, got {got!r}")


def main() -> int:
    keys_raw = os.environ.get("GROQ_API_KEYS")
    if not keys_raw or not keys_raw.strip():
        print("skipped (no GROQ_API_KEYS)")
        return 0

    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
    router = GroqKeyRouter(keys=keys)
    cases = load_cases(_DATASET)
    asyncio.run(_run(router, cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
