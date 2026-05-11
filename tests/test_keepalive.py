"""Tests for the Render keep-alive self-ping loop (``app/workers/keepalive``).

The loop is small but its contract is touchy on Render free tier: too long
between pings → dyno spins down; an exploding tick → loop dies and the
scheduler eventually goes to sleep too. Tests cover the four properties
we actually care about:

1. ``run_keepalive_loop`` issues at least one GET against the configured
   URL within a few ticks (``initial_delay`` honoured but small in tests).
2. Network errors inside the loop are swallowed — the loop keeps going.
3. ``start_keepalive`` / ``stop_keepalive`` round-trip cleanly.
4. ``stop_keepalive`` is a no-op for an already-finished task (matches the
   shape of ``stop_inproc_scheduler``).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.workers.keepalive import (
    run_keepalive_loop,
    start_keepalive,
    stop_keepalive,
)


@pytest.mark.asyncio
@respx.mock
async def test_loop_pings_url_until_stopped() -> None:
    """One ping cycle should hit ``url`` then stop on ``stop_event``."""
    route = respx.get("https://example.test/healthz").mock(
        return_value=httpx.Response(200, text="ok"),
    )
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_keepalive_loop(
            "https://example.test/healthz",
            stop,
            interval=0.05,
            initial_delay=0.01,
            timeout=1.0,
        ),
    )
    # Let the loop settle past initial_delay + one tick.
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert route.called
    assert route.call_count >= 1


@pytest.mark.asyncio
@respx.mock
async def test_loop_swallows_errors() -> None:
    """A failing request must not kill the loop — next tick retries."""
    counter = {"n": 0}

    def _flaky(_request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text="ok")

    respx.get("https://example.test/healthz").mock(side_effect=_flaky)

    stop = asyncio.Event()
    task = asyncio.create_task(
        run_keepalive_loop(
            "https://example.test/healthz",
            stop,
            interval=0.02,
            initial_delay=0.01,
            timeout=1.0,
        ),
    )
    await asyncio.sleep(0.15)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    # First call raised, loop kept going → at least two attempts total.
    assert counter["n"] >= 2


@pytest.mark.asyncio
@respx.mock
async def test_start_and_stop_round_trip() -> None:
    """``start_keepalive`` returns a runnable task; ``stop_keepalive`` joins."""
    route = respx.get("https://example.test/healthz").mock(
        return_value=httpx.Response(200, text="ok"),
    )
    task, stop = start_keepalive(
        "https://example.test/healthz",
        interval=0.05,
        initial_delay=0.01,
        timeout=1.0,
    )
    await asyncio.sleep(0.1)
    await stop_keepalive(task, stop, grace=1.0)
    assert task.done()
    assert route.called


@pytest.mark.asyncio
async def test_stop_keepalive_noop_for_finished_task() -> None:
    """Stopping a task that already returned must not raise."""

    async def finished() -> None:
        return None

    task = asyncio.create_task(finished())
    await task
    stop = asyncio.Event()
    await stop_keepalive(task, stop, grace=0.1)
    assert task.done()


@pytest.mark.asyncio
async def test_loop_returns_immediately_if_stopped_during_initial_delay() -> None:
    """Stopping before ``initial_delay`` elapses must short-circuit cleanly."""
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_keepalive_loop(
            "https://example.test/healthz",
            stop,
            interval=10.0,
            initial_delay=10.0,
            timeout=1.0,
        ),
    )
    # Give the task one event-loop tick to enter the initial delay wait.
    await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
