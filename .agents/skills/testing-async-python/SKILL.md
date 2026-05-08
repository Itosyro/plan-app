---
name: testing-async-python
description: Use when adding or fixing tests in plan-app. Covers pytest-asyncio fixtures, in-memory SQLite, respx for Groq mocks, fake clocks, and the patterns the existing 172-test suite already uses.
---

# Testing async Python in plan-app

`tests/` already has 172 tests passing. Before writing a new test, **find the closest existing one and copy its shape**. This skill documents the shapes worth copying.

---

## 1. Stack

| Tool | Why |
|---|---|
| `pytest` + `pytest-asyncio` | Async test functions (`async def test_…`). |
| In-memory SQLite via `sqlmodel` | Isolated per-test DB, no Postgres needed. |
| `respx` | Mock the Groq HTTP layer. |
| `freezegun` (optional) | Pin "now" — usually we just pass `now=datetime(...)` into the function under test. |

We **never** call live Groq from tests. CI must stay deterministic.

---

## 2. Async test boilerplate

`pyproject.toml` sets `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed.

```python
import pytest
from sqlmodel import select
from app.db.models import Task

async def test_creates_task(session):
    task = Task(user_id=1, title="x", horizon="today")
    session.add(task)
    await session.commit()

    found = (await session.exec(select(Task))).one()
    assert found.title == "x"
```

Fixtures (`session`, `bot`, etc.) are defined in `tests/conftest.py` — read it first.

---

## 3. Pinning the clock — pass `now=` instead of monkeypatching

The scheduler / digest functions accept `now: datetime | None`. In tests, **pass it in**; don't monkeypatch `datetime`.

```python
async def test_tick_fires_due_reminder(session):
    fixed = datetime(2026, 5, 8, 10, 0)
    reminder = Reminder(..., scheduled_for=fixed - timedelta(minutes=1))
    session.add(reminder); await session.commit()

    await tick_reminders(session, bot=fake_bot, now=fixed)

    refreshed = (await session.exec(select(Reminder))).one()
    assert refreshed.status == "sent"
```

Tests in `tests/test_scheduler.py`, `test_digest.py` follow exactly this shape.

---

## 4. Mocking Groq with `respx`

```python
import httpx, respx

@respx.mock
async def test_classifier_handles_429(session):
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "rate"}}),
            httpx.Response(200, json={"choices": [{"message": {"content": "{...}"}}]}),
        ]
    )
    result = await classify(...)
    assert route.call_count == 2
```

Never let a test hit `api.groq.com` — `respx.mock` is the contract.

---

## 5. Telegram bot mocks

`tests/conftest.py` exposes a `FakeBot` that records `.send_message(...)` calls. Use it:

```python
async def test_digest_sends_only_at_HH_MM(session, fake_bot):
    await tick_digests(session, fake_bot, now=datetime(2026, 5, 8, 9, 0))
    assert fake_bot.sent == []  # user's morning_digest_at is 08:00, not 09:00
```

We don't spin up an aiogram dispatcher in unit tests — too heavy. Test the **service** directly, mock the bot.

---

## 6. SQLite quirks vs Postgres

SQLite is fine for 95% of tests. Watch out for:

- **JSON column ordering** — SQLite preserves insert order, Postgres does not. Don't assert on key order.
- **Naive vs aware datetime** — SQLite stores both as TEXT, Postgres rejects mismatch. Use `app/shared/time.py::utcnow_naive()`.
- **Case sensitivity** — SQLite default `LIKE` is case-insensitive, Postgres is sensitive. Use `.ilike(...)` everywhere.
- **`NOWAIT` / `FOR UPDATE`** — no-ops on SQLite. If you need row-locking semantics tested, mock the query.

---

## 7. What NOT to test

- **aiogram routers themselves** — too much wiring, low value. Test the service the router calls.
- **Live Groq** — never. Mock.
- **Render / Postgres** — not in unit tests. Phase 4c will add e2e for that.

---

## 8. Patterns you'll find in the existing suite

| Pattern | Example file |
|---|---|
| Persist + read-back | `tests/test_persist.py` |
| Scheduler tick with frozen `now` | `tests/test_scheduler.py` |
| Digest matching HH:MM in user's tz | `tests/test_digest.py` |
| Callback-data round-trip | `tests/test_callbacks.py` |
| Russian-date preprocessing | `tests/test_russian_dates.py` |
| In-process scheduler runner | `tests/test_runner.py` |

---

## 9. Verification before push

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
```

All three must be clean. If a test is flaky, fix it — don't `pytest --reruns`.

---

## 10. Common pitfalls

- **`AsyncSession` not committed before `select`** — your read sees stale data. Always `await session.commit()` (or `flush()`) before assertions.
- **Forgetting `await` on `session.exec(...)`** — pytest will raise `RuntimeWarning: coroutine was never awaited`, treat as error.
- **Using `datetime.utcnow()`** — deprecated; use `utcnow_naive()`. See `defensive-programming/SKILL.md::3`.
- **Asserting on logged strings** — log format may change. Assert on side-effects (DB row, `fake_bot.sent`), not log lines.

---

## Source

Distilled from the existing `tests/` suite + plan-app conventions. No external code copied.
