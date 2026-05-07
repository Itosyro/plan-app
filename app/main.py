"""FastAPI entry point.

Phase 0 placeholder. Real Telegram webhook + REST API land in Phase 1.

When the container boots in Phase 1 it will:
- spin up an aiogram Dispatcher,
- register a Telegram webhook on startup (lifespan),
- expose `/tg/<secret>` for incoming updates,
- expose `/api/*` for the future mini-app,
- expose `/healthz` for Render health checks.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="plan-app", version="0.0.0")


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    """Liveness probe used by Render."""
    return {"status": "ok"}
