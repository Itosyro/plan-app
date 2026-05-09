"""End-to-end Phase 4c tests — message → Task → Reminder → Digest.

Existing suites cover each component in isolation:

* ``test_e2e_pipeline.py`` — message → split → classify → persist (Task);
* ``test_reminders.py``    — persist_classification → Reminder rows;
* ``test_scheduler.py``    — Reminder tick → Telegram send;
* ``test_digest.py``       — digest builders + tick HH:MM matching.

The chain that ties all of them together — a user message becoming a Task,
that Task spawning a Reminder, the scheduler firing it, and the same Task
later showing up in the morning digest — was not covered. This file fills
that gap and pins three regressions that span the full chain:

1. ``status='done'`` tasks are excluded from the morning digest.
2. After ``MAX_REMINDER_ATTEMPTS`` failures a Reminder transitions to
   ``status='failed'`` and is permanently skipped on subsequent ticks.
3. The scheduler never sets ``parse_mode``: ``task.title`` is user-controlled
   and may contain ``*`` / ``_`` / ``[`` which Markdown would reject (400).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.schemas import ClassifierResult
from app.bot.digest import build_morning_digest, tick_digests
from app.bot.services import (
    complete_onboarding,
    get_or_create_user,
    persist_classification,
)
from app.db.models import Reminder, Task, User
from app.workers.scheduler import MAX_REMINDER_ATTEMPTS, tick_reminders

# ── helpers ──────────────────────────────────────────────────────────


class _RecordingBot:
    """Drop-in for ``aiogram.Bot`` that captures every send_message kwarg.

    Unlike the slim ``_FakeBot`` in ``test_scheduler.py`` we keep the *full*
    kwargs dict so tests can assert that ``parse_mode`` is never passed.
    """

    def __init__(
        self,
        *,
        fail: bool = False,
        fail_with: Exception | None = None,
    ) -> None:
        self.fail = fail
        self.fail_with = fail_with or RuntimeError("boom")
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        if self.fail:
            raise self.fail_with
        self.calls.append(kwargs)


def _classifier_result(
    *,
    title: str = "Купить хлеб",
    horizon: str = "today",
    is_task: bool = True,
    reminder_offsets: list[int] | None = None,
    confidence: float = 0.9,
) -> ClassifierResult:
    """Build a ClassifierResult that mirrors what the real classifier returns.

    ``confidence`` is high by default so the critic is skipped — the e2e
    chain tested here starts at ``persist_classification`` and downstream.
    """
    return ClassifierResult(
        category_name="Покупки",
        horizon=horizon,  # type: ignore[arg-type]
        priority="medium",
        is_task=is_task,
        confidence=confidence,
        title=title,
        reminder_offsets=reminder_offsets,
    )


async def _onboard_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    tz: str = "UTC",
    morning: str = "08:00",
    evening: str = "21:00",
) -> User:
    """Create + onboard a user with explicit digest slots.

    ``complete_onboarding`` stamps ``onboarded_at`` and creates the
    ``UserSettings`` row with documented defaults; we then tweak the digest
    HH:MM slots so each test pins them deterministically.
    """
    user, _ = await get_or_create_user(session, telegram_id=telegram_id)
    await session.flush()
    settings = await complete_onboarding(session, user, display_name=f"User-{telegram_id}", tz=tz)
    settings.morning_digest_at = morning
    settings.evening_digest_at = evening
    session.add(settings)
    await session.commit()
    return user


# ── 1. Full chain: classification → Task → Reminder fires → Digest ───


@pytest.mark.asyncio
async def test_full_chain_persist_then_reminder_then_morning_digest(
    session: AsyncSession,
) -> None:
    """Persist a classified task, tick the reminder, then read the digest.

    Acceptance:

    * Task created with the correct title.
    * Two ``Reminder`` rows scheduled at the default ``same_day`` offsets.
    * ``tick_reminders`` at the due moment marks both ``sent`` and the
      FakeBot received both messages addressed to the right ``chat_id``.
    * ``build_morning_digest`` afterwards still lists the (still-open) task.
    """
    user = await _onboard_user(session, telegram_id=4001, tz="UTC")
    assert user.id is not None

    # Use real "now" so persist_classification's internal utcnow_naive() check
    # treats both default offsets [60, 15] as future.
    now_utc = datetime.now(UTC).replace(microsecond=0)
    due_at = now_utc + timedelta(hours=4)

    cr = _classifier_result(title="Купить хлеб", horizon="today")
    row = await persist_classification(
        session,
        user_id=user.id,
        cr=cr,
        due_at=due_at,
        inbox_id=None,
    )
    await session.commit()

    assert isinstance(row, Task)
    rems = list(
        (await session.exec(select(Reminder).order_by(Reminder.fire_at))).all()  # type: ignore[union-attr]
    )
    assert len(rems) == 2  # default same_day = [60, 15]
    naive_due = due_at.astimezone(UTC).replace(tzinfo=None)
    assert (naive_due - rems[0].fire_at) == timedelta(minutes=60)
    assert (naive_due - rems[1].fire_at) == timedelta(minutes=15)
    assert all(r.task_id == row.id and r.status == "pending" for r in rems)

    # Both reminders should fire when "now" is the due moment.
    bot = _RecordingBot()
    result = await tick_reminders(bot, now=naive_due)

    assert result == {"sent": 2, "retry": 0, "failed": 0}
    assert len(bot.calls) == 2
    for call in bot.calls:
        assert call["chat_id"] == 4001
        assert "Купить хлеб" in call["text"]
        assert "parse_mode" not in call

    for r in rems:
        await session.refresh(r)
        assert r.status == "sent"
        assert r.sent_at is not None
        assert r.last_error is None

    # Task is still open — morning digest must include it.
    text = await build_morning_digest(session, user)
    assert "Сегодня:" in text
    assert "Купить хлеб" in text


# ── 2. tz isolation: only the user whose local HH:MM matches gets pinged ──


@pytest.mark.asyncio
async def test_morning_digest_tick_isolated_by_user_timezone(
    session: AsyncSession,
) -> None:
    """Two onboarded users in different time zones, identical morning slot.

    At 05:00 UTC:
    * ``Europe/Moscow`` (UTC+3 year-round) → 08:00 local → match.
    * ``America/New_York`` in May (EDT, UTC-4) → 01:00 local → no match.

    Only the Moscow user receives a digest.
    """
    await _onboard_user(session, telegram_id=4101, tz="Europe/Moscow", morning="08:00")
    await _onboard_user(session, telegram_id=4102, tz="America/New_York", morning="08:00")

    bot = _RecordingBot()
    result = await tick_digests(bot, now=datetime(2026, 5, 8, 5, 0, tzinfo=UTC))

    assert result == {"morning": 1, "evening": 0, "errors": 0}
    assert len(bot.calls) == 1
    assert bot.calls[0]["chat_id"] == 4101
    assert "Доброе утро" in bot.calls[0]["text"]
    assert "parse_mode" not in bot.calls[0]


# ── 3a. Edge case: status='done' is excluded from the morning digest ─


@pytest.mark.asyncio
async def test_morning_digest_excludes_tasks_completed_after_persist(
    session: AsyncSession,
) -> None:
    """Tasks that flip to ``status='done'`` after persist drop out of the digest.

    Mirrors the real flow where the user marks a task done via the inline
    ✅ button (``app/bot/routers/callbacks.py``). The new persist→done→digest
    chain is tested here; the standalone digest filter is already pinned in
    ``test_digest.py``.
    """
    user = await _onboard_user(session, telegram_id=4201, tz="UTC")
    assert user.id is not None

    done_row = await persist_classification(
        session,
        user_id=user.id,
        cr=_classifier_result(title="Закрытая задача", horizon="today"),
        due_at=None,
        inbox_id=None,
    )
    open_row = await persist_classification(
        session,
        user_id=user.id,
        cr=_classifier_result(title="Открытая задача", horizon="today"),
        due_at=None,
        inbox_id=None,
    )
    assert isinstance(done_row, Task) and isinstance(open_row, Task)

    done_row.status = "done"
    session.add(done_row)
    await session.commit()

    text = await build_morning_digest(session, user)
    assert "Открытая задача" in text
    assert "Закрытая задача" not in text


# ── 3b. Edge case: ``attempts >= MAX_REMINDER_ATTEMPTS`` → status='failed' ──


@pytest.mark.asyncio
async def test_reminder_marked_failed_after_max_attempts_then_skipped(
    session: AsyncSession,
) -> None:
    """A failing send is retried up to ``MAX_REMINDER_ATTEMPTS`` then quarantined.

    Once ``status='failed'`` the row must never be picked up by future ticks
    even if the bot recovers — otherwise we'd spam the user with a stale
    reminder days later.
    """
    user = await _onboard_user(session, telegram_id=4301, tz="UTC")
    assert user.id is not None

    now = datetime(2026, 5, 8, 12, 0)
    task = Task(user_id=user.id, title="Регрессия")
    session.add(task)
    await session.flush()
    assert task.id is not None

    rem = Reminder(
        user_id=user.id,
        task_id=task.id,
        fire_at=now - timedelta(minutes=1),
        status="pending",
        attempts=0,
    )
    session.add(rem)
    await session.commit()

    bot = _RecordingBot(fail=True, fail_with=RuntimeError("rate limited"))

    for attempt in range(1, MAX_REMINDER_ATTEMPTS + 1):
        result = await tick_reminders(bot, now=now)
        await session.refresh(rem)
        assert rem.attempts == attempt
        assert rem.last_error is not None
        if attempt < MAX_REMINDER_ATTEMPTS:
            assert rem.status == "pending"
            assert result == {"sent": 0, "retry": 1, "failed": 0}
        else:
            assert rem.status == "failed"
            assert result == {"sent": 0, "retry": 0, "failed": 1}

    # Recovery: even when the bot now succeeds, a failed reminder is dead.
    bot.fail = False
    bot.calls = []
    result = await tick_reminders(bot, now=now + timedelta(hours=1))
    assert result == {"sent": 0, "retry": 0, "failed": 0}
    assert bot.calls == []
    await session.refresh(rem)
    assert rem.status == "failed"


# ── 3c. Edge case: parse_mode regression for star-laden titles ───────


@pytest.mark.asyncio
async def test_reminder_send_uses_plain_text_no_markdown_parse_mode(
    session: AsyncSession,
) -> None:
    """Titles with Markdown control chars must not trigger Markdown parsing.

    See ``defensive-programming/SKILL.md`` C-2 and ``REVIEW-findings.md``:
    Telegram returns 400 if ``parse_mode='Markdown'`` is set on text whose
    ``*`` / ``_`` / ``[`` aren't balanced. The scheduler defends against
    this by sending plain text only.
    """
    user = await _onboard_user(session, telegram_id=4401, tz="UTC")
    assert user.id is not None

    now_utc = datetime.now(UTC).replace(microsecond=0)
    due_at = now_utc + timedelta(hours=4)

    title = "*звёзды* и [скобки]_и_подчёрки"
    await persist_classification(
        session,
        user_id=user.id,
        cr=_classifier_result(title=title, horizon="today"),
        due_at=due_at,
        inbox_id=None,
    )
    await session.commit()

    naive_due = due_at.astimezone(UTC).replace(tzinfo=None)
    bot = _RecordingBot()
    result = await tick_reminders(bot, now=naive_due)

    assert result["sent"] >= 1
    assert result["retry"] == 0
    assert result["failed"] == 0
    for call in bot.calls:
        # The two essential invariants for the regression.
        assert "parse_mode" not in call
        # Star + bracket survive verbatim → confirms no Markdown stripping.
        assert "*звёзды*" in call["text"]
        assert "[скобки]" in call["text"]
