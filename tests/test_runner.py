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


@pytest.fixture(autouse=True)
def _stub_side_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the ticks that would touch the DB / Telegram.

    ``purge_trash`` and ``maybe_send_auto_backup`` run in the same loop;
    without an engine they'd raise into the loop's ``except`` on every
    iteration and drown the real assertions in noise. Tests that care
    about them override these stubs.
    """

    async def _no_trash(**_: Any) -> dict[str, int]:
        return {"tasks": 0, "notes": 0}

    async def _no_backup(_: Any) -> bool:
        return False

    monkeypatch.setattr(runner_mod, "purge_trash", _no_trash)
    monkeypatch.setattr(runner_mod, "maybe_send_auto_backup", _no_backup)


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
async def test_loop_purges_trash_and_offers_auto_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both side ticks are actually wired into the loop.

    ``purge_trash`` used to exist only in the standalone worker entry
    point, which nothing runs — the documented 24-hour trash retention
    therefore never happened. ``maybe_send_auto_backup`` is the weekly
    server-swap insurance. A fix that isn't called is not a fix.
    """
    seen: list[str] = []

    async def fake_tick(_: Any) -> dict[str, int]:
        return {}

    async def fake_purge(**_: Any) -> dict[str, int]:
        seen.append("trash")
        return {"tasks": 0, "notes": 0}

    async def fake_backup(_: Any) -> bool:
        seen.append("backup")
        return False

    monkeypatch.setattr(runner_mod, "tick_reminders", fake_tick)
    monkeypatch.setattr(runner_mod, "tick_digests", fake_tick)
    monkeypatch.setattr(runner_mod, "purge_trash", fake_purge)
    monkeypatch.setattr(runner_mod, "maybe_send_auto_backup", fake_backup)

    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(_FakeBot(), stop, interval=0.05))
    await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert "trash" in seen and "backup" in seen


@pytest.mark.asyncio
async def test_backup_failure_does_not_stop_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken auto-backup must not take reminders down with it."""
    counter = {"reminders": 0}

    async def count_reminders(_: Any) -> dict[str, int]:
        counter["reminders"] += 1
        return {}

    async def boom_backup(_: Any) -> bool:
        raise RuntimeError("telegram is down")

    monkeypatch.setattr(runner_mod, "tick_reminders", count_reminders)
    monkeypatch.setattr(runner_mod, "tick_digests", lambda _: _empty())
    monkeypatch.setattr(runner_mod, "maybe_send_auto_backup", boom_backup)

    stop = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(_FakeBot(), stop, interval=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert counter["reminders"] >= 2


async def _empty() -> dict[str, int]:
    return {}


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
