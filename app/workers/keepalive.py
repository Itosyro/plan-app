"""Self-ping background task to prevent Render free-tier idle spin-down.

Render's free plan spins the web dyno down after ~15 minutes of inactivity.
That also pauses the in-process scheduler (``app.workers.runner``), so
reminders and digest ticks stop firing until the next external request
wakes the dyno back up — and the first request that does the waking pays
a 30–60 s cold-start penalty.

To keep the dyno warm we run a background asyncio task that issues a
``GET`` against our **public** ``/healthz`` endpoint every
``KEEPALIVE_INTERVAL_SECONDS`` seconds. The request leaves the dyno over
the internet and comes back as a regular external HTTP hit, which Render
counts as activity and resets the idle timer.

Mirrors ``voice-bot``'s implementation (see commit ``b7d387a`` of
``Itosyro/voice-bot`` — ``_self_ping`` in ``src/main.py``). The only
difference is httpx instead of aiohttp because plan-app already depends
on httpx via the Telegram client stack.

Errors inside the loop are logged but never propagate — one bad ping
must not kill the task for the rest of the process lifetime.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx

from app.shared.logging import get_logger

logger = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 600.0
DEFAULT_INITIAL_DELAY_SECONDS = 60.0
DEFAULT_TIMEOUT_SECONDS = 10.0
SHUTDOWN_GRACE_SECONDS = 5.0


async def run_keepalive_loop(
    url: str,
    stop_event: asyncio.Event,
    *,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    initial_delay: float = DEFAULT_INITIAL_DELAY_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Ping ``url`` every ``interval`` seconds until ``stop_event`` fires.

    Skips the first ``initial_delay`` seconds so startup has time to settle
    before the first network call (matches the voice-bot behaviour). The
    loop checks ``stop_event`` between waits so shutdown is prompt.
    """
    logger.info("keepalive.loop.start", url=url, interval=interval)
    try:
        if await _wait_or_stop(stop_event, initial_delay):
            return
        async with httpx.AsyncClient(timeout=timeout) as client:
            while not stop_event.is_set():
                try:
                    response = await client.get(url)
                    logger.info(
                        "keepalive.ping_ok",
                        url=url,
                        status=response.status_code,
                    )
                except Exception as exc:
                    # Network blips, DNS failures, dyno transient 5xx — all
                    # safe to ignore; the next tick retries.
                    logger.warning(
                        "keepalive.ping_failed",
                        url=url,
                        error=str(exc)[:200],
                    )
                if await _wait_or_stop(stop_event, interval):
                    return
    finally:
        logger.info("keepalive.loop.stop")


async def _wait_or_stop(stop_event: asyncio.Event, total: float) -> bool:
    """Wait up to ``total`` seconds; return ``True`` if stop fired."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=total)
    except TimeoutError:
        return False
    return True


def start_keepalive(
    url: str,
    *,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    initial_delay: float = DEFAULT_INITIAL_DELAY_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Spawn the keepalive loop as a background task.

    Returns ``(task, stop_event)`` — pass both to :func:`stop_keepalive`
    on shutdown.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        run_keepalive_loop(
            url,
            stop_event,
            interval=interval,
            initial_delay=initial_delay,
            timeout=timeout,
        ),
        name="keepalive.loop",
    )
    return task, stop_event


async def stop_keepalive(
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
        logger.warning("keepalive.loop.cancel_timeout")
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
