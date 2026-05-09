"""Structural tests for ``app/bot/routers/voice.py``.

These tests use AST inspection because the voice handler's inner
``_background`` task is hard to drive end-to-end without mocking
Telegram file downloads and Whisper. Instead we assert the structural
invariant: both ``text.py`` and ``voice.py`` must load the user's
``default_reminder_offsets`` from settings and forward it as a
``default_reminder_offsets=`` kwarg to ``run_pipeline``. The old
``voice.py`` did neither, so voice users always got the global default
preset regardless of their personal ``reminder_preset`` setting. See
``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-6``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROUTERS = Path(__file__).resolve().parents[1] / "app" / "bot" / "routers"


def _has_run_pipeline_call_with_kwarg(source: str, kwarg: str) -> bool:
    """Return True if any call to ``run_pipeline`` passes ``kwarg=``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "run_pipeline":
            for kw in node.keywords:
                if kw.arg == kwarg:
                    return True
    return False


def test_text_router_forwards_default_reminder_offsets() -> None:
    """Sanity: text.py already does this — guards against regressions."""
    source = (_ROUTERS / "text.py").read_text(encoding="utf-8")
    assert _has_run_pipeline_call_with_kwarg(source, "default_reminder_offsets"), (
        "text.py must pass default_reminder_offsets= to run_pipeline"
    )


def test_voice_router_forwards_default_reminder_offsets() -> None:
    """Regression for R-NEW-C-6: voice.py must mirror text.py."""
    source = (_ROUTERS / "voice.py").read_text(encoding="utf-8")
    assert _has_run_pipeline_call_with_kwarg(source, "default_reminder_offsets"), (
        "voice.py must pass default_reminder_offsets= to run_pipeline "
        "(see docs/REVIEW-2026-05-09-v2.md::R-NEW-C-6)"
    )


def test_voice_router_loads_default_reminder_offsets_from_settings() -> None:
    """Voice handler must compute the offsets the same way text.py does
    — by iterating ``settings.default_reminder_offsets.items()``.
    """
    source = (_ROUTERS / "voice.py").read_text(encoding="utf-8")
    assert "settings.default_reminder_offsets.items()" in source, (
        "voice.py must load default_reminder_offsets from UserSettings "
        "(see docs/REVIEW-2026-05-09-v2.md::R-NEW-C-6)"
    )
