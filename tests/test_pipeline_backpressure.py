"""Tests for the pipeline backpressure semaphores (R-NEW-I-8).

The real ``run_pipeline`` ends with a courier call to Groq; mocking
the entire chain just to verify the semaphore is overkill. Instead
these tests verify the semaphores at the helper level and exercise
the wrapper using a stand-in inner pipeline so we can deterministically
check ordering and concurrency.
"""

from __future__ import annotations

import asyncio

import pytest

from app.bot.routers import _pipeline as pipeline_module
from app.bot.routers._pipeline import (
    GLOBAL_PIPELINE_LIMIT,
    PER_USER_PIPELINE_LIMIT,
    _get_global_pipeline_semaphore,
    _get_user_pipeline_semaphore,
    reset_pipeline_semaphores_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_semaphores() -> None:
    """Each test gets a fresh semaphore registry (loops are per-test)."""
    reset_pipeline_semaphores_for_tests()
    yield
    reset_pipeline_semaphores_for_tests()


def test_per_user_pipeline_limit_is_one() -> None:
    """Default per-user limit is 1 (strict serialisation). If somebody
    raises this without thinking through the UX implications, the
    test fails so they have to update the docstring too.
    """
    assert PER_USER_PIPELINE_LIMIT == 1


def test_global_pipeline_limit_has_headroom() -> None:
    """Global cap must be > per-user cap so a single user can't
    monopolise the worker. R-NEW-I-8.
    """
    assert GLOBAL_PIPELINE_LIMIT >= PER_USER_PIPELINE_LIMIT
    assert GLOBAL_PIPELINE_LIMIT >= 4


@pytest.mark.asyncio
async def test_user_semaphore_is_per_user_not_global() -> None:
    """Two different user_ids must get *different* semaphore objects
    so one user's flood can't block another.
    """
    sem_a = await _get_user_pipeline_semaphore(101)
    sem_b = await _get_user_pipeline_semaphore(102)
    assert sem_a is not sem_b

    # Same user → cached.
    sem_a_again = await _get_user_pipeline_semaphore(101)
    assert sem_a is sem_a_again


@pytest.mark.asyncio
async def test_global_semaphore_is_shared() -> None:
    """All users share one global semaphore."""
    g1 = _get_global_pipeline_semaphore()
    g2 = _get_global_pipeline_semaphore()
    assert g1 is g2


@pytest.mark.asyncio
async def test_per_user_serialises_concurrent_pipelines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent ``run_pipeline`` calls for the *same* user must
    execute one-after-the-other, not in parallel. Headline R-NEW-I-8
    regression: a user spam-tapping voice messages should never
    have two pipelines competing for Groq quota at the same instant.
    """
    in_flight = 0
    max_in_flight = 0
    order: list[str] = []

    async def fake_inner(
        groq_router: object,
        text: str,
        tg_user_id: int,
        user_id: int,
        user_tz: str,
        inbox_id: int | None,
        **_kwargs: object,
    ) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        order.append(f"start-{text}")
        # Yield enough times for the other coroutine to reach the
        # semaphore acquire and observe contention.
        await asyncio.sleep(0.01)
        order.append(f"end-{text}")
        in_flight -= 1
        return f"reply-{text}"

    monkeypatch.setattr(pipeline_module, "_run_pipeline_inner", fake_inner)

    coros = [
        pipeline_module.run_pipeline(
            None,  # type: ignore[arg-type]
            f"msg{i}",
            tg_user_id=500,
            user_id=500,
            user_tz="UTC",
            inbox_id=None,
        )
        for i in range(3)
    ]
    replies = await asyncio.gather(*coros)

    assert replies == ["reply-msg0", "reply-msg1", "reply-msg2"]
    assert max_in_flight == 1, (
        f"per-user limit was breached: {max_in_flight} in flight; order={order}"
    )
    # Strict interleaving: every start is immediately followed by its end.
    assert order == [
        "start-msg0",
        "end-msg0",
        "start-msg1",
        "end-msg1",
        "start-msg2",
        "end-msg2",
    ]


@pytest.mark.asyncio
async def test_global_caps_total_concurrency_across_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GLOBAL_PIPELINE_LIMIT + 4`` distinct users firing
    simultaneously must never run more than ``GLOBAL_PIPELINE_LIMIT``
    in parallel. R-NEW-I-8.
    """
    in_flight = 0
    max_in_flight = 0
    enter_event = asyncio.Event()

    async def fake_inner(
        groq_router: object,
        text: str,
        tg_user_id: int,
        user_id: int,
        user_tz: str,
        inbox_id: int | None,
        **_kwargs: object,
    ) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        # Hold the slot until the test signals to release.
        await enter_event.wait()
        in_flight -= 1
        return text

    monkeypatch.setattr(pipeline_module, "_run_pipeline_inner", fake_inner)

    n = GLOBAL_PIPELINE_LIMIT + 4
    coros = [
        pipeline_module.run_pipeline(
            None,  # type: ignore[arg-type]
            f"u{i}",
            tg_user_id=600 + i,
            user_id=600 + i,
            user_tz="UTC",
            inbox_id=None,
        )
        for i in range(n)
    ]
    task = asyncio.gather(*coros)
    # Let the first batch hit the inner; semaphore admits up to LIMIT.
    for _ in range(20):
        await asyncio.sleep(0)
    assert in_flight == GLOBAL_PIPELINE_LIMIT, (
        f"expected {GLOBAL_PIPELINE_LIMIT} in flight, got {in_flight}"
    )
    enter_event.set()
    await task
    assert max_in_flight == GLOBAL_PIPELINE_LIMIT


@pytest.mark.asyncio
async def test_different_users_run_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different users with concurrent pipelines must NOT
    serialise on each other (per-user sem is per-user).
    """
    started = asyncio.Event()
    in_flight = 0
    max_in_flight = 0

    async def fake_inner(
        groq_router: object,
        text: str,
        tg_user_id: int,
        user_id: int,
        user_tz: str,
        inbox_id: int | None,
        **_kwargs: object,
    ) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        started.set()
        await asyncio.sleep(0.02)
        in_flight -= 1
        return text

    monkeypatch.setattr(pipeline_module, "_run_pipeline_inner", fake_inner)

    coros = [
        pipeline_module.run_pipeline(
            None,  # type: ignore[arg-type]
            "x",
            tg_user_id=u,
            user_id=u,
            user_tz="UTC",
            inbox_id=None,
        )
        for u in (701, 702)
    ]
    await asyncio.gather(*coros)
    assert max_in_flight == 2
