"""REST API for the Telegram Mini-App (Phase 5.1).

Routers under ``app/api/routers/`` are mounted at ``/api/...`` from
``app/main.py``. Authentication is handled by
``app.api.auth.current_user`` — a FastAPI dependency that validates the
``X-Telegram-Init-Data`` header (HMAC-SHA256 against the bot token, per
the Telegram Mini Apps spec).
"""

from __future__ import annotations
