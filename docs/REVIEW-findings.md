# Mega review — findings

**Date:** 2026-05-08
**Scope:** Full codebase review/stress-test before Phase 4c (e2e tests).
**Reviewer:** PR B (`devin/1778273769-mega-review-b`).

The repo is in good shape: clean separation of concerns (bot ↔ AI ↔
workers ↔ db ↔ shared), strict typing, structured logging with PII
discipline, idempotent webhook, and 172 passing tests after Phase 4a/b.
The issues below are real but localised.

Severity ladder:

* **Critical** — must-fix before next release; user-visible bug or
  inconsistency that can corrupt data.
* **Important** — should-fix; defends against minor data corruption,
  silent failures, or contract drift.
* **Minor** — nice-to-have; logged for follow-up.
* **Positive** — patterns to keep and reuse.

---

## Critical

### C-1. Inconsistent UTC handling between writers

`app/db/models.py::_utcnow` returns a tz-aware UTC datetime
(`datetime.now(UTC)`) while `app/bot/services.py::schedule_reminders`
and `app/workers/scheduler.py::tick_reminders` use the *naive*
`datetime.utcnow()`. The DB columns are tz-naive (`DateTime` without
`timezone=True`), so SQLAlchemy silently strips the tz on insert and
returns naive datetimes on read. This works today on SQLite, but on
Postgres with stricter drivers (or once we ever switch to
`timezone=True`) we get mismatched comparisons and surprise-fails. The
team has been bitten by this twice already (Phase 4a `_to_naive_utc`
helper exists for the same reason).

* **Fix:** add `app/shared/time.py::utcnow_naive()` and use it in every
  DB-write site (model defaults, `complete_onboarding`,
  `schedule_reminders`, `tick_reminders`).
* **Status:** fixed in this PR.

### C-2. `parse_mode="Markdown"` rendered with user-controlled titles

`app/bot/routers/commands.py` builds digests like:

```python
lines = [f"📋 *{title}*\n"]
for i, task in enumerate(tasks, 1):
    icon = ...
    lines.append(f"{i}. {icon} {task.title}{due_part}")
...
await message.answer("\n".join(lines), parse_mode="Markdown")
```

`task.title` is fully user-controlled (whatever the LLM extracted from
their message). If a title contains `*`, `_`, `[`, or `` ` ``, Telegram
returns `400 Bad Request: can't parse entities`. We already have a
regression test that forbids this combo in `callbacks.py`
(`test_callbacks.py::test_callback_edit_text_does_not_use_markdown_parse_mode`)
— but `commands.py` slipped through.

* **Fix:** drop `parse_mode="Markdown"` from `/today`, `/tomorrow`,
  `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`. The
  `*Title*` decorations are removed; emoji headers stay (📋 / 📝 / 🏷)
  for visual structure. Same fix already applied to callback handlers.
* **Status:** fixed in this PR.

---

## Important

### I-1. `getattr(settings, field, None)` in `app/bot/routers/settings.py`

`_setting_value` does `getattr(settings, field, None)` to dereference a
field name supplied by callback data. Dynamic attribute access bypasses
type-checking and the field-allow-list (`SETTING_LABELS`); a malformed
callback could otherwise read an arbitrary attribute. Also violates
project guidance: do NOT use `getattr` for known fields.

* **Fix:** explicit field mapping (`{"critic_mode": settings.critic_mode, ...}`).
* **Status:** fixed in this PR.

### I-2. `kind=type(update).__name__` is always `"Update"` in webhook log

`app/main.py::telegram_webhook` records the update kind for the
idempotency cache:

```python
kind = "message" if update.message else type(update).__name__
```

`update` is always an `aiogram.types.Update`, so `type(update).__name__`
is always `"Update"` — useless for diagnostics. Should detect
`callback_query`, `edited_message`, etc.

* **Fix:** branch on `update.callback_query`, `update.edited_message`,
  `update.inline_query`, etc.
* **Status:** fixed in this PR.

---

## Minor — logged for follow-up

### M-1. Webhook idempotency race window

If two webhook calls with the same `update_id` arrive within the same
session_scope, both `is_update_processed` checks return False, then the
second `record_update` flush hits a `UNIQUE` violation. Telegram retries
on a 5xx, so the user-visible impact is just one spurious log line, but
we should catch `IntegrityError` and short-circuit.

* **Action:** track in roadmap for Phase 5 hardening.

### M-2. `asyncio.create_task` without strong reference

`text.py` and `voice.py` create background tasks with
`asyncio.create_task(_background())`. Python's docs warn:

> Save a reference to the result of this function, to avoid a task
> disappearing mid-execution.

In practice the running loop holds an internal strong ref through
`Task.add_done_callback`, but a future refactor that drops that callback
would re-introduce the GC risk.

* **Action:** consider tracking pending tasks in a module-level `set`
  and discarding on completion. Roadmap, not urgent.

### M-3. `_utcnow` import sites still leak through historical models

After C-1's fix, `_utcnow` (tz-aware) lives in `app/db/models.py`. We
keep it but route it through `utcnow_naive()` for consistency.

### M-4. `text.py::_groq_router` is a process-wide mutable singleton

Tests don't currently exercise this corner, but if `Settings.groq_api_keys`
mutates between requests in a hot-reload scenario, the cached router is
stale. Acceptable for production (env immutable per process).

* **Action:** keep as-is; document.

### M-5. Render free tier idle spin-down vs in-process scheduler

Documented in `docs/RENDER.md` and `render.yaml`. Health-check pinger
recipe is included. No code change needed; mention here for posterity.

---

## Positive patterns to reuse

* **N+1 avoidance** — `get_categories_with_counts` does a single
  `LEFT OUTER JOIN ... GROUP BY` instead of a Python loop with extra
  queries. Pattern: `select(Category, func.count(Task.id).label("cnt"))`.
* **Exception isolation in scheduler loops** —
  `app/workers/runner.py::run_scheduler_loop` wraps each tick in its own
  try/except so one failing tick can't kill the whole loop. Pattern:
  `try: await tick(...) except Exception: logger.exception(...)`.
* **Graceful shutdown with grace period** —
  `app/workers/runner.py::stop_inproc_scheduler` uses
  `asyncio.Event` + `asyncio.wait_for` with a configurable grace.
* **PII discipline in logs** —
  `app/shared/logging.py` documents the rule, all log calls in routers
  and services consistently log identifiers + lengths, never raw text.
* **Idempotency guard on webhook** — `is_update_processed` +
  `record_update` block re-processing without locking the bot up on
  Telegram retries.
* **Strict HH:MM digest matcher** —
  `app/bot/digest.py::_matches_hhmm` requires exact equality so we don't
  send the same digest twice within a minute.
* **Defence-in-depth for callback data** —
  `app/bot/services.py::ALLOWED_SETTING_VALUES` rejects any value not
  pre-listed, even if a forged callback supplies it.
* **Wildcard escaping in LIKE** —
  `find_task_by_query` escapes `%` and `_` so user query strings can't
  match unintended rows.

---

## Test-suite health

* 172 passing tests across unit + e2e (`test_e2e_pipeline.py` exercises
  full pipeline with respx-mocked Groq).
* Existing regression tests directly cover the patterns above:
  `test_callback_edit_text_does_not_use_markdown_parse_mode`,
  `test_find_task_by_query_escapes_like_wildcards`,
  `test_update_user_settings_rejects_unknown_value`.
* Phase 4a/b suite (`test_runner.py`, `test_scheduler.py`,
  `test_reminders.py`) covers reminder lifecycle end-to-end at the
  service layer.

---

## Action items captured by this PR

* Fix C-1 (UTC unification): `app/shared/time.py::utcnow_naive` + 3 call sites.
* Fix C-2 (Markdown leak): `app/bot/routers/commands.py` — drop
  `parse_mode="Markdown"`, plain emoji headers.
* Fix I-1 (getattr): explicit field mapping in
  `app/bot/routers/settings.py::_setting_value`.
* Fix I-2 (webhook kind): branch on the populated update field in
  `app/main.py::telegram_webhook`.

Minor items (M-1..M-5) are documented for follow-up, no code change in
this PR.
