"""In-process scheduler loop for reminders + daily digests.

Render's free plan does not support standalone Cron services. To keep the
deploy on the free tier we run the same tick logic *inside* the FastAPI web
process: a single asyncio task wakes every ``interval`` seconds, calls
:func:`app.workers.scheduler.tick_reminders` and
:func:`app.bot.digest.tick_digests`, then sleeps. An external pinger (e.g.
cron-job.org → ``GET /healthz`` every 5 min) keeps the free dyno warm so the
loop is actually alive.

Errors inside the loop are logged but never propagate — one bad tick must
not kill the worker for the rest of the lifetime of the process.
"""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot

from app.bot.digest import tick_digests
from app.shared.logging import get_logger
from app.workers.scheduler import tick_reminders

logger = get_logger(__name__)

DEFAULT_TICK_INTERVAL_SECONDS = 60.0
SHUTDOWN_GRACE_SECONDS = 10.0


async def run_scheduler_loop(
    bot: Bot,
    stop_event: asyncio.Event,
    *,
    interval: float = DEFAULT_TICK_INTERVAL_SECONDS,
) -> None:
    """Run reminder + digest ticks until ``stop_event`` is set.

    The loop sleeps in ``min(1.0, interval)`` slices so cancellation is fast.
    Each iteration wraps ticks in ``try/except`` so transient DB or Telegram
    failures don't kill the loop.
    """
    logger.info("scheduler.loop.start", interval=interval)
    try:
        while not stop_event.is_set():
            try:
                rem = await tick_reminders(bot)
                dig = await tick_digests(bot)
                logger.debug("scheduler.loop.tick", reminders=rem, digests=dig)
            except Exception as exc:
                logger.exception("scheduler.loop.tick_failed", error=str(exc)[:200])
            await _sleep_or_stop(stop_event, interval)
    finally:
        logger.info("scheduler.loop.stop")


async def _sleep_or_stop(stop_event: asyncio.Event, total: float) -> None:
    """Sleep up to ``total`` seconds, returning early when ``stop_event`` fires."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=total)
    except TimeoutError:
        return


def start_inproc_scheduler(
    bot: Bot,
    *,
    interval: float = DEFAULT_TICK_INTERVAL_SECONDS,
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Spawn the scheduler loop as a background task.

    Returns ``(task, stop_event)`` — pass both to
    :func:`stop_inproc_scheduler` on shutdown.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        run_scheduler_loop(bot, stop_event, interval=interval),
        name="scheduler.loop",
    )
    return task, stop_event


async def stop_inproc_scheduler(
    task: asyncio.Task[None],
    stop_event: asyncio.Event,
    *,
    grace: float = SHUTDOWN_GRACE_SECONDS,
) -> None:
    """Signal the loop to stop and wait up to ``grace`` seconds for it."""
    if task.done():
        return
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=grace)
    except TimeoutError:
        logger.warning("scheduler.loop.cancel_timeout")
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
