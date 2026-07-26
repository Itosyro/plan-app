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


# ── Honest failure copy (pipeline crash) ─────────────────────────────
#
# Before: both routers said «сохранил во входящие, разберу позже».
# Both halves were false — nothing set ``needs_review`` (so the entry
# never showed up in the Mini-App «Входящие» tab, which filters on that
# flag), and no re-parse mechanism exists at all.


def _except_handler_sources(path: Path, func_name: str) -> list[str]:
    """Return the source of every ``except`` body inside *func_name*."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    bodies: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != func_name:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.ExceptHandler):
                bodies.append("\n".join(ast.unparse(stmt) for stmt in inner.body))
    return bodies


def test_routers_never_promise_a_later_re_parse() -> None:
    """No router may claim it will «разберу позже» — there is no
    retry/re-parse job anywhere in the product.
    """
    for name in ("text.py", "voice.py"):
        source = (_ROUTERS / name).read_text(encoding="utf-8")
        assert "разберу позже" not in source, f"{name} promises a re-parse that doesn't exist"


def test_text_router_flags_needs_review_on_pipeline_crash() -> None:
    """The ``_background`` except-branch must flag the inbox entry, or
    the reply's «лежит во Входящих» is a lie (``api/routers/inbox.py``
    only returns rows with ``needs_review=True``).
    """
    bodies = _except_handler_sources(_ROUTERS / "text.py", "_background")
    assert any("flag_needs_review" in body for body in bodies), (
        "text.py::_background must call flag_needs_review() when the pipeline crashes"
    )


def test_voice_router_flags_needs_review_on_pipeline_crash() -> None:
    """Voice mirrors text — but only when an inbox row actually exists
    (a Whisper failure happens before the entry is stored).
    """
    bodies = _except_handler_sources(_ROUTERS / "voice.py", "_background")
    assert any("flag_needs_review" in body for body in bodies), (
        "voice.py::_background must call flag_needs_review() when the pipeline crashes"
    )
    assert any("inbox_id is None" in body for body in bodies), (
        "voice.py must not promise «во Входящих» when the crash predates the inbox write"
    )
