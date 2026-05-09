"""FastAPI routes for the Telegram mini-app and admin endpoints.

Reserved namespace — populated in **Phase 5** (mini-app JSON API:
``GET /api/today``, ``GET /api/inbox``, ``POST /api/tasks``, etc.).
Kept as an empty package so reviewers don't think it's an oversight
and so future imports (``from app.api import router``) don't break
during the staged rollout.

See ``docs/REVIEW-2026-05-09.md::M-7`` and ``ARCHITECTURE.md`` for
the phase plan.
"""
