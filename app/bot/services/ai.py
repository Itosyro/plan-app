"""AI run logging."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import AiRun


async def log_ai_run(
    session: AsyncSession,
    *,
    user_id: int,
    inbox_id: int | None,
    stage: str,
    model: str,
    key_index: int = 0,
    latency_ms: int = 0,
    tokens: int = 0,
    status: str = "ok",
    error: str | None = None,
) -> AiRun:
    """Log an AI pipeline call to the ai_runs table."""
    run = AiRun(
        user_id=user_id,
        inbox_id=inbox_id,
        stage=stage,
        model=model,
        key_index=key_index,
        latency_ms=latency_ms,
        tokens=tokens,
        status=status,
        error=error,
    )
    session.add(run)
    await session.flush()
    return run
