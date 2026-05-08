"""Tests for the in-process scheduler loop (`app/workers/runner.py`)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.workers import runner as runner_mod
from app.workers.runner import (
    run_scheduler_loop,
    start_inproc_scheduler,
    stop_inproc_scheduler,
)


class _FakeBot:
    """Sentinel — runner only forwards `bot` into the tick functions."""


@pytest.mark.asyncio
async def test_loop_calls_tick_functions_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    rem_calls: list[Any] = []
    dig_calls: list[Any] = []

    async def fake_tick_reminders(bot: Any) -> dict[str, int]:
        rem_calls.append(bot)
        return {"sent": 0, "retry": 0, "failed": 0}

    async def fake_tick_digests(bot: Any) -> dict[str, int]:
        dig_calls.append(bot)
        return {"morning": 0, "evening": 0, "errors": 0}

    monkeypatch.setattr(runner_mod, "tick_reminders", fake_tick_reminders)
    monkeypatch.setattr(runner_mod, "tick_digests", fake_tick_digests)

    bot = _FakeBot()
    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(bot, stop, interval=0.05))

    # Let it tick at least once, then stop.
    await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(rem_calls) >= 1
    assert len(dig_calls) >= 1
    assert rem_calls[0] is bot


@pytest.mark.asyncio
async def test_loop_swallows_tick_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """One exploding tick must not kill the loop."""
    counter = {"reminders": 0, "digests": 0}

    async def boom_reminders(_: Any) -> dict[str, int]:
        counter["reminders"] += 1
        if counter["reminders"] == 1:
            raise RuntimeError("boom")
        return {"sent": 0, "retry": 0, "failed": 0}

    async def ok_digests(_: Any) -> dict[str, int]:
        counter["digests"] += 1
        return {"morning": 0, "evening": 0, "errors": 0}

    monkeypatch.setattr(runner_mod, "tick_reminders", boom_reminders)
    monkeypatch.setattr(runner_mod, "tick_digests", ok_digests)

    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(_FakeBot(), stop, interval=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    # Loop kept going after the first failure → reminders called more than once.
    assert counter["reminders"] >= 2


@pytest.mark.asyncio
async def test_start_and_stop_inproc_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def noop_reminders(_: Any) -> dict[str, int]:
        seen.append("rem")
        return {"sent": 0, "retry": 0, "failed": 0}

    async def noop_digests(_: Any) -> dict[str, int]:
        seen.append("dig")
        return {"morning": 0, "evening": 0, "errors": 0}

    monkeypatch.setattr(runner_mod, "tick_reminders", noop_reminders)
    monkeypatch.setattr(runner_mod, "tick_digests", noop_digests)

    task, stop = start_inproc_scheduler(_FakeBot(), interval=0.02)
    await asyncio.sleep(0.05)
    await stop_inproc_scheduler(task, stop, grace=1.0)

    assert task.done()
    assert "rem" in seen and "dig" in seen


@pytest.mark.asyncio
async def test_stop_inproc_scheduler_is_noop_for_finished_task() -> None:
    """Calling stop on an already-finished task must not raise."""

    async def finished() -> None:
        return None

    task = asyncio.create_task(finished())
    await task
    stop = asyncio.Event()
    await stop_inproc_scheduler(task, stop, grace=0.1)  # должно молча выйти
    assert task.done()
