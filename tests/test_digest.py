"""Tests for Phase 4b digest builders + tick (`app/bot/digest.py`)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bot.digest import (
    _matches_hhmm,
    _user_local_now,
    build_evening_digest,
    build_morning_digest,
    tick_digests,
)
from app.bot.services import (
    complete_onboarding,
    get_or_create_horizon,
    get_or_create_user,
)
from app.db.models import Task, TaskEvent, UserSettings


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.pin_calls: list[tuple[int, int]] = []
        self._next_message_id = 1000

    async def send_message(self, *, chat_id: int, text: str, **_: Any) -> SimpleNamespace:
        self.calls.append((chat_id, text))
        msg_id = self._next_message_id
        self._next_message_id += 1
        return SimpleNamespace(message_id=msg_id)

    async def pin_chat_message(self, *, chat_id: int, message_id: int, **_: Any) -> bool:
        self.pin_calls.append((chat_id, message_id))
        return True


# ── Helpers ─────────────────────────────────────────────────────────


def test_matches_hhmm_exact() -> None:
    dt = datetime(2026, 5, 8, 8, 0)
    assert _matches_hhmm(dt, "08:00") is True
    assert _matches_hhmm(dt, "08:01") is False
    assert _matches_hhmm(dt, "07:00") is False


def test_matches_hhmm_invalid() -> None:
    dt = datetime(2026, 5, 8, 8, 0)
    assert _matches_hhmm(dt, None) is False
    assert _matches_hhmm(dt, "") is False
    assert _matches_hhmm(dt, "08-00") is False
    assert _matches_hhmm(dt, "8:00") is False  # need zero-padding
    assert _matches_hhmm(dt, "ab:cd") is False


def test_user_local_now_respects_tz() -> None:
    utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)  # 08:00 MSK
    local = _user_local_now("Europe/Moscow", utc)
    assert local.hour == 8 and local.minute == 0


def test_user_local_now_unknown_tz_falls_back_to_utc() -> None:
    utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    local = _user_local_now("Bogus/Zone", utc)
    assert local.hour == 5 and local.tzinfo is not None


def test_user_local_now_handles_naive_input() -> None:
    naive = datetime(2026, 5, 8, 5, 0)  # treat as UTC
    local = _user_local_now("Europe/Moscow", naive)
    assert local.hour == 8


# ── build_morning_digest ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_morning_digest_empty(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1100)
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Доброе утро" in text
    assert "не запланировано" in text


@pytest.mark.asyncio
async def test_morning_digest_lists_today(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1101)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    session.add(
        Task(
            user_id=user.id,
            horizon_id=today.id,
            title="Купить хлеб",
            priority="high",
            due_at=datetime(2026, 5, 8, 9, 0),
        ),
    )
    session.add(
        Task(user_id=user.id, horizon_id=today.id, title="Йога", priority="low"),
    )
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Сегодня:" in text
    assert "🔴 Купить хлеб — в 09:00" in text
    assert "🟢 Йога" in text


@pytest.mark.asyncio
async def test_morning_digest_skips_done_tasks(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1102)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    session.add(
        Task(user_id=user.id, horizon_id=today.id, title="Done", status="done"),
    )
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Open"))
    await session.commit()

    text = await build_morning_digest(session, user)

    assert "Open" in text
    assert "Done" not in text


# ── build_evening_digest ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evening_digest_combines_today_and_tomorrow(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1103)
    await session.commit()
    assert user.id is not None

    today = await get_or_create_horizon(session, user.id, "today")
    tomorrow = await get_or_create_horizon(session, user.id, "tomorrow")
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Доделать отчёт"))
    session.add(Task(user_id=user.id, horizon_id=tomorrow.id, title="Совещание"))
    await session.commit()

    text = await build_evening_digest(session, user)

    assert "Подводим итоги" in text
    assert "Осталось на сегодня:" in text
    assert "Доделать отчёт" in text
    assert "Завтра:" in text
    assert "Совещание" in text


@pytest.mark.asyncio
async def test_evening_digest_celebrates_empty_today(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1104)
    await session.commit()

    text = await build_evening_digest(session, user)

    assert "Сегодня всё закрыто" in text


# ── PR-G: richer sections (overdue / week / completed_today) ─────────


@pytest.mark.asyncio
async def test_morning_digest_includes_overdue(session: AsyncSession) -> None:
    """Tasks with due_at before today's user-local start show up under Просрочено."""
    user, _ = await get_or_create_user(session, telegram_id=1120)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    today = await get_or_create_horizon(session, user.id, "today")
    week = await get_or_create_horizon(session, user.id, "week")
    # Now = 2026-05-08 08:00 MSK (== 05:00 UTC).
    now_utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    # Yesterday 14:00 MSK = 2026-05-07 11:00 UTC.
    session.add(
        Task(
            user_id=user.id,
            horizon_id=week.id,
            title="Просроченный отчёт",
            priority="high",
            due_at=datetime(2026, 5, 7, 11, 0),
        ),
    )
    # Open today task — should appear under Сегодня, not overdue.
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Свежая задача"))
    # Done task with overdue due_at — must NOT appear.
    session.add(
        Task(
            user_id=user.id,
            horizon_id=week.id,
            title="Уже сделано",
            status="done",
            due_at=datetime(2026, 5, 6, 9, 0),
        ),
    )
    await session.commit()

    text = await build_morning_digest(session, user, now_utc=now_utc)

    assert "Просрочено:" in text
    assert "Просроченный отчёт" in text
    assert "07.05" in text  # date marker
    assert "Уже сделано" not in text


@pytest.mark.asyncio
async def test_morning_digest_includes_urgent_week(session: AsyncSession) -> None:
    """Tasks with due_at within the next 7 days appear under Горячие дедлайны."""
    user, _ = await get_or_create_user(session, telegram_id=1121)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    week = await get_or_create_horizon(session, user.id, "week")
    today_h = await get_or_create_horizon(session, user.id, "today")
    now_utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)  # 08:00 MSK
    # In 3 days (within the 7-day window).
    session.add(
        Task(
            user_id=user.id,
            horizon_id=week.id,
            title="Совещание со звуковиком",
            priority="medium",
            due_at=datetime(2026, 5, 11, 12, 0),
        ),
    )
    # 10 days out — outside the window, must NOT appear.
    session.add(
        Task(
            user_id=user.id,
            horizon_id=week.id,
            title="Поездка в горы",
            due_at=datetime(2026, 5, 18, 9, 0),
        ),
    )
    # Today-bucket task — already in "Сегодня", should NOT be duplicated.
    session.add(
        Task(
            user_id=user.id,
            horizon_id=today_h.id,
            title="Подарок маме",
            due_at=datetime(2026, 5, 8, 18, 0),
        ),
    )
    await session.commit()

    text = await build_morning_digest(session, user, now_utc=now_utc)

    assert "Горячие дедлайны на неделе:" in text
    assert "Совещание со звуковиком" in text
    assert "11.05" in text
    assert "Поездка в горы" not in text
    # Today task appears under Сегодня, not under the week section.
    assert text.count("Подарок маме") == 1


@pytest.mark.asyncio
async def test_morning_digest_limits_overdue_to_top_five(
    session: AsyncSession,
) -> None:
    """OVERDUE_LIMIT enforced: 7 overdue tasks → 5 oldest-first listed."""
    user, _ = await get_or_create_user(session, telegram_id=1122)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    week = await get_or_create_horizon(session, user.id, "week")
    now_utc = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    for day in [1, 2, 3, 4, 5, 6, 7]:
        session.add(
            Task(
                user_id=user.id,
                horizon_id=week.id,
                title=f"old-{day}",
                due_at=datetime(2026, 5, day, 9, 0),
            ),
        )
    await session.commit()

    text = await build_morning_digest(session, user, now_utc=now_utc)

    # 5 oldest (1..5) listed; 6, 7 truncated.
    assert "old-1" in text
    assert "old-2" in text
    assert "old-3" in text
    assert "old-4" in text
    assert "old-5" in text
    assert "old-6" not in text
    assert "old-7" not in text


@pytest.mark.asyncio
async def test_evening_digest_includes_completed_today(session: AsyncSession) -> None:
    """Tasks marked done today (via TaskEvent kind=completed) appear under Закрыто."""
    user, _ = await get_or_create_user(session, telegram_id=1123)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    today = await get_or_create_horizon(session, user.id, "today")
    now_utc = datetime(2026, 5, 8, 18, 0, tzinfo=UTC)  # 21:00 MSK — evening
    # Completed earlier today.
    done_task = Task(
        user_id=user.id,
        horizon_id=today.id,
        title="Купить хлеб",
        status="done",
    )
    session.add(done_task)
    await session.flush()
    assert done_task.id is not None
    # Event timestamp within today's MSK window: 14:00 MSK = 11:00 UTC.
    event = TaskEvent(
        task_id=done_task.id,
        kind="completed",
        payload_json={"source": "test"},
    )
    event.created_at = datetime(2026, 5, 8, 11, 0)
    session.add(event)
    # Completed YESTERDAY — must NOT appear.
    yesterday_task = Task(
        user_id=user.id,
        horizon_id=today.id,
        title="Сходить в спортзал",
        status="done",
    )
    session.add(yesterday_task)
    await session.flush()
    assert yesterday_task.id is not None
    old_event = TaskEvent(task_id=yesterday_task.id, kind="completed")
    old_event.created_at = datetime(2026, 5, 7, 18, 0)
    session.add(old_event)
    # Still-open task.
    session.add(Task(user_id=user.id, horizon_id=today.id, title="Помыть посуду"))
    await session.commit()

    text = await build_evening_digest(session, user, now_utc=now_utc)

    assert "Закрыто сегодня — 1 ✅" in text
    assert "Купить хлеб" in text
    assert "Сходить в спортзал" not in text
    assert "Осталось на сегодня:" in text
    assert "Помыть посуду" in text


@pytest.mark.asyncio
async def test_evening_digest_dedupes_reopened_task(session: AsyncSession) -> None:
    """A task completed → reopened → completed today shows up once, not twice."""
    user, _ = await get_or_create_user(session, telegram_id=1124)
    user.tz = "Europe/Moscow"
    session.add(user)
    await session.commit()
    assert user.id is not None
    today = await get_or_create_horizon(session, user.id, "today")
    now_utc = datetime(2026, 5, 8, 18, 0, tzinfo=UTC)
    task = Task(user_id=user.id, horizon_id=today.id, title="Доделать слайды", status="done")
    session.add(task)
    await session.flush()
    assert task.id is not None
    # Two completed events on the same day.
    for hh in (10, 16):
        ev = TaskEvent(task_id=task.id, kind="completed")
        ev.created_at = datetime(2026, 5, 8, hh - 3, 0)  # convert MSK → UTC
        session.add(ev)
    await session.commit()

    text = await build_evening_digest(session, user, now_utc=now_utc)

    assert text.count("Доделать слайды") == 1
    assert "Закрыто сегодня — 1 ✅" in text


@pytest.mark.asyncio
async def test_evening_digest_skips_completed_for_other_user(
    session: AsyncSession,
) -> None:
    """Completed tasks of one user must not leak into another's digest."""
    user_a, _ = await get_or_create_user(session, telegram_id=1125)
    user_b, _ = await get_or_create_user(session, telegram_id=1126)
    user_a.tz = "Europe/Moscow"
    user_b.tz = "Europe/Moscow"
    session.add_all([user_a, user_b])
    await session.commit()
    assert user_a.id is not None and user_b.id is not None
    today_a = await get_or_create_horizon(session, user_a.id, "today")
    task = Task(user_id=user_a.id, horizon_id=today_a.id, title="A's task", status="done")
    session.add(task)
    await session.flush()
    assert task.id is not None
    ev = TaskEvent(task_id=task.id, kind="completed")
    ev.created_at = datetime(2026, 5, 8, 11, 0)
    session.add(ev)
    await session.commit()

    now_utc = datetime(2026, 5, 8, 18, 0, tzinfo=UTC)
    text_b = await build_evening_digest(session, user_b, now_utc=now_utc)

    assert "A's task" not in text_b
    assert "Сегодня всё закрыто" in text_b


# ── tick_digests ────────────────────────────────────────────────────


async def _onboard(
    session: AsyncSession,
    *,
    telegram_id: int,
    tz: str,
    morning: str = "08:00",
    evening: str = "21:00",
    onboarded_at: datetime | None = None,
) -> None:
    """Helper: create user, run onboarding, then tweak digest slots.

    ``onboarded_at`` defaults to a value ~10 days before any of the
    fixed ``now`` timestamps used in the tests below, so the day-1
    catch-up suppression introduced for R-NEW-I-4 doesn't fire and
    the existing tests keep their semantics. Pass an explicit value
    when verifying the day-1 behaviour itself.
    """
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.flush()
    await complete_onboarding(session, user, display_name="Tester", tz=tz)
    # Override the wall-clock onboarded_at with a deterministic past
    # value so tests can use fixed ``now`` parameters in tick_digests
    # without colliding with the day-1 fresh-user safeguard.
    user.onboarded_at = onboarded_at or datetime(2026, 4, 28, 0, 0)
    session.add(user)
    settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).first()
    assert settings is not None
    settings.morning_digest_at = morning
    settings.evening_digest_at = evening
    session.add(settings)
    await session.commit()


@pytest.mark.asyncio
async def test_tick_digests_sends_morning_at_local_match(session: AsyncSession) -> None:
    await _onboard(session, telegram_id=1105, tz="Europe/Moscow")

    bot = _FakeBot()
    # 05:00 UTC == 08:00 MSK → morning slot.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 0, tzinfo=UTC))

    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1
    chat_id, text = bot.calls[0]
    assert chat_id == 1105
    assert "Доброе утро" in text


@pytest.mark.asyncio
async def test_tick_digests_skips_before_scheduled(session: AsyncSession) -> None:
    """Before the scheduled HH:MM, no digest fires. The catch-up window
    is forward-only: ``local_now >= scheduled_time``.
    """
    await _onboard(session, telegram_id=1106, tz="Europe/Moscow")

    bot = _FakeBot()
    # 04:30 UTC == 07:30 MSK — before the 08:00 scheduled time.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 4, 30, tzinfo=UTC))

    assert result == {"morning": 0, "evening": 0, "errors": 0}
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_digests_catches_up_after_drift(session: AsyncSession) -> None:
    """Regression for R-NEW-I-4: a tick that arrives 90 s after the
    scheduled minute (cold-start, GC pause, slow earlier tick) must
    still deliver the digest. The strict-minute predecessor would
    silently drop it for the rest of the day.
    """
    await _onboard(session, telegram_id=1113, tz="Europe/Moscow")

    bot = _FakeBot()
    # 05:01:30 UTC == 08:01:30 MSK — 90 seconds past the scheduled 08:00.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 1, 30, tzinfo=UTC))

    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_tick_digests_catches_up_after_long_outage(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-I-4: even hours-late, the digest fires —
    once per day. Render free-tier cold-starts can take several minutes
    for the worker to spin back up; the digest should still land that
    day rather than being lost forever.
    """
    await _onboard(session, telegram_id=1114, tz="Europe/Moscow")

    bot = _FakeBot()
    # 06:30 UTC == 09:30 MSK — 90 minutes past the 08:00 scheduled time.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 6, 30, tzinfo=UTC))

    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_should_fire_digest_helper() -> None:
    """Direct unit tests on the catch-up predicate."""
    from datetime import date as _date

    from app.bot.digest import _should_fire_digest

    today = _date(2026, 5, 8)
    yesterday = _date(2026, 5, 7)

    # Before scheduled — no fire.
    assert _should_fire_digest(datetime(2026, 5, 8, 7, 30), "08:00", None) is False
    # Exactly at scheduled — fire.
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "08:00", None) is True
    # 90 seconds past — fire (catch-up).
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 1, 30), "08:00", None) is True
    # 90 minutes past — fire (catch-up).
    assert _should_fire_digest(datetime(2026, 5, 8, 9, 30), "08:00", None) is True
    # Already fired today — skip.
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 1, 30), "08:00", today) is False
    # Already fired *yesterday* — fire today.
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "08:00", yesterday) is True
    # Malformed / missing config — no fire.
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), None, None) is False
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "", None) is False
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "8:00", None) is False
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "ab:cd", None) is False
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "25:00", None) is False
    assert _should_fire_digest(datetime(2026, 5, 8, 8, 0), "08:60", None) is False

    # Day-1 safeguard — onboarded after today's scheduled slot:
    # would have fired (catch-up) but the safeguard skips today.
    onboarded_after = datetime(2026, 5, 8, 17, 0)
    assert (
        _should_fire_digest(
            datetime(2026, 5, 8, 21, 0),
            "08:00",
            None,
            onboarded_local=onboarded_after,
        )
        is False
    )
    # Onboarded *before* today's scheduled slot — fires normally.
    onboarded_before = datetime(2026, 5, 8, 7, 0)
    assert (
        _should_fire_digest(
            datetime(2026, 5, 8, 21, 0),
            "08:00",
            None,
            onboarded_local=onboarded_before,
        )
        is True
    )


@pytest.mark.asyncio
async def test_tick_digests_skips_first_day_for_late_onboarding(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-I-4 day-1 UX: a user who finishes
    onboarding at 17:00 local with morning_digest_at=08:00 must NOT
    receive a "good morning" message that same evening, even though
    the catch-up rule would otherwise trigger it.
    """
    # Onboarded at 14:00 UTC == 17:00 MSK on day 1.
    onboarded_utc = datetime(2026, 5, 8, 14, 0)
    await _onboard(
        session,
        telegram_id=1115,
        tz="Europe/Moscow",
        onboarded_at=onboarded_utc,
    )

    bot = _FakeBot()
    # Tick 4 hours later, 21:00 MSK on the same day.
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 18, 0, tzinfo=UTC))

    # The 08:00 morning digest is suppressed (onboarded after the slot);
    # the 21:00 evening digest fires (onboarded before the slot).
    assert result == {"morning": 0, "evening": 1, "errors": 0}
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_tick_digests_fires_first_day_when_onboarded_early(
    session: AsyncSession,
) -> None:
    """Regression for R-NEW-I-4 day-1 UX: a user who finishes
    onboarding at 06:00 local (before the 08:00 morning slot) must
    still receive that day's morning digest at 08:00.
    """
    # Onboarded at 03:00 UTC == 06:00 MSK on day 1.
    onboarded_utc = datetime(2026, 5, 8, 3, 0)
    await _onboard(
        session,
        telegram_id=1116,
        tz="Europe/Moscow",
        onboarded_at=onboarded_utc,
    )

    bot = _FakeBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 0, tzinfo=UTC))
    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_tick_digests_skips_unonboarded(session: AsyncSession) -> None:
    user, _ = await get_or_create_user(session, telegram_id=1107)
    await session.commit()
    assert user.id is not None and user.onboarded_at is None

    settings = UserSettings(user_id=user.id, morning_digest_at="08:00", evening_digest_at="21:00")
    session.add(settings)
    await session.commit()

    bot = _FakeBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 8, 0, tzinfo=UTC))

    assert result == {"morning": 0, "evening": 0, "errors": 0}
    assert bot.calls == []


@pytest.mark.asyncio
async def test_tick_digests_isolates_one_failing_user(session: AsyncSession) -> None:
    """A failing send for user A shouldn't stop user B from getting their digest."""

    class _PickyBot(_FakeBot):
        async def send_message(  # type: ignore[override]
            self, *, chat_id: int, text: str, **kw: Any
        ) -> SimpleNamespace:
            if chat_id == 1108:
                raise RuntimeError("rate limited")
            return await super().send_message(chat_id=chat_id, text=text, **kw)

    for tg_id in (1108, 1109):
        await _onboard(session, telegram_id=tg_id, tz="UTC")

    bot = _PickyBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 8, 0, tzinfo=UTC))

    # 1109 receives, 1108 errors.
    assert result["morning"] == 1
    assert result["errors"] == 1
    assert any(c[0] == 1109 for c in bot.calls)
    assert all(c[0] != 1108 for c in bot.calls)


# ── C-3 regression: idempotency guard against double-send ────────────


@pytest.mark.asyncio
async def test_tick_digests_skips_second_call_in_same_minute(
    session: AsyncSession,
) -> None:
    """C-3: two ticks at the same ``now`` must send exactly one digest.

    Pre-2026-05-09 ``tick_digests`` had no idempotency guard, so a
    scheduler running at < 60 s interval would fire the morning digest
    once per tick during the matching HH:MM window. Now we record the
    user-local date in ``last_morning_digest_on`` and skip if equal.
    """
    await _onboard(session, telegram_id=1110, tz="Europe/Moscow")

    bot = _FakeBot()
    now = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)  # 08:00 MSK

    first = await tick_digests(bot, now=now)
    assert first == {"morning": 1, "evening": 0, "errors": 0}

    # Second tick at the same wall-clock time → must skip.
    second = await tick_digests(bot, now=now)
    assert second == {"morning": 0, "evening": 0, "errors": 0}

    # Bot received exactly one message.
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_tick_digests_skips_repeat_within_same_minute_evening(
    session: AsyncSession,
) -> None:
    """C-3 companion: same guard applies to the evening digest.

    Pre-arms ``last_morning_digest_on`` to today so the catch-up
    rule doesn't also fire the morning digest at 21:00 (a separate
    feature added for R-NEW-I-4).
    """
    from datetime import date as _date

    from app.db.models import User

    await _onboard(session, telegram_id=1111, tz="Europe/Moscow")
    user = (await session.exec(select(User).where(User.telegram_id == 1111))).first()
    assert user is not None and user.id is not None
    settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).first()
    assert settings is not None
    settings.last_morning_digest_on = _date(2026, 5, 8)
    session.add(settings)
    await session.commit()

    bot = _FakeBot()
    now = datetime(2026, 5, 8, 18, 0, tzinfo=UTC)  # 21:00 MSK

    first = await tick_digests(bot, now=now)
    assert first == {"morning": 0, "evening": 1, "errors": 0}

    second = await tick_digests(bot, now=now)
    assert second == {"morning": 0, "evening": 0, "errors": 0}

    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_tick_digests_resends_on_next_day(session: AsyncSession) -> None:
    """C-3 companion: gate is keyed by *date*, so tomorrow's tick fires.

    A second tick the next day at the same HH:MM in the user's local tz
    must deliver again.
    """
    await _onboard(session, telegram_id=1112, tz="Europe/Moscow")

    bot = _FakeBot()
    day1 = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    day2 = datetime(2026, 5, 9, 5, 0, tzinfo=UTC)

    first = await tick_digests(bot, now=day1)
    second = await tick_digests(bot, now=day1)
    third = await tick_digests(bot, now=day2)

    assert first == {"morning": 1, "evening": 0, "errors": 0}
    assert second == {"morning": 0, "evening": 0, "errors": 0}
    assert third == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 2  # day1 + day2, but not the duplicate at day1


@pytest.mark.asyncio
async def test_tick_digests_persists_gate_to_db(session: AsyncSession) -> None:
    """C-3 companion: the gate flip survives a fresh ``session_scope``.

    ``tick_digests`` opens its own session; this test verifies the
    column was actually committed by re-reading via the test's session.
    """
    from app.db.models import User

    await _onboard(session, telegram_id=1113, tz="Europe/Moscow")

    bot = _FakeBot()
    now = datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    await tick_digests(bot, now=now)

    user = (await session.exec(select(User).where(User.telegram_id == 1113))).first()
    assert user is not None and user.id is not None
    settings = (
        await session.exec(select(UserSettings).where(UserSettings.user_id == user.id))
    ).first()
    assert settings is not None
    # 08:00 MSK on 2026-05-08 in MSK is local date 2026-05-08.
    assert settings.last_morning_digest_on == datetime(2026, 5, 8).date()
    # Evening untouched.
    assert settings.last_evening_digest_on is None
