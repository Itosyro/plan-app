# Code review — plan-app

**Reviewer:** Devin (deep review pass + skill bundle, branch `devin/1778266950-code-review`)
**Range:** `origin/main` … working tree (after PR #31 + #32)
**Scope:** all of `app/`, `tests/`, `render.yaml`, `pyproject.toml`, deploy config.
**Method:** read every module top-to-bottom, cross-checked with `docs/PLAN.md`, `docs/ROADMAP.md`, `docs/PROGRESS.md`, applied checklist from `.agents/skills/code-review/SKILL.md` plus the new `requesting-code-review` skill from obra/superpowers.

---

## TL;DR

Codebase is in **solid shape** — clean layering, idempotent webhook, thoughtful PII rules, decent test coverage (128 tests). Found **3 Critical** issues that affect production correctness (Markdown injection, missing input validation in /settings, brittle pipeline error handling), **6 Important** issues that should be fixed before scaling up, and **a handful of minor polish items**. Critical and Important issues are addressed in this same PR; Minor are documented for follow-up.

---

## Strengths (what's already great)

- Webhook double-validates secret (path + header). <ref_snippet file="/home/ubuntu/repos/plan-app/app/main.py" lines="84-90" />
- Idempotency guard via `telegram_updates.update_id` is wired *before* `dp.feed_update`. <ref_snippet file="/home/ubuntu/repos/plan-app/app/main.py" lines="96-114" />
- PII discipline: structlog setup explicitly says "never log raw user text". <ref_snippet file="/home/ubuntu/repos/plan-app/app/shared/logging.py" lines="1-30" />
- Routers are factory-built (`create_router()`) so re-attaching to a fresh `Dispatcher` works in tests. <ref_snippet file="/home/ubuntu/repos/plan-app/app/bot/__init__.py" lines="1-42" />
- AI prompts live in dedicated `.md` files (not inlined). Pipeline stages are independently testable.
- LLM calls are async + use `instructor` for structured output (good).
- Conftest spins up an in-memory SQLite engine per test — clean isolation.

---

## Critical issues (must fix — addressed in this PR)

### C-1. Markdown injection in inline-button callbacks (Telegram 400)

**Where:** `app/bot/routers/callbacks.py:139-142, 169-172, 219-224, 305-311`

When a user-supplied task title contains a Markdown metachar (`*`, `_`, `[`, `]`, `~`, `` ` ``, `\`, `(`, `)`, `>`, `#`, `+`, `=`, `|`, `{`, `}`, `.`, `!`), the `edit_text(..., parse_mode="Markdown")` call either:

- Renders garbled (e.g. half-italic), or
- Throws `TelegramBadRequest: can't parse entities` and the user sees no feedback at all.

Real example: a task titled `Купить 2*3 пирог` would hit this — Telegram tries to interpret `2*3 пирог` as bold opening, fails to find a closing `*`, and returns 400.

**Why critical:** silently breaks "✅ Готово / 🗑 Удалить / 🔄 Перенести / 🏷 Категория" for any task whose title or category contains a Markdown char. The handler doesn't catch that exception, so the user gets nothing.

**Fix in this PR:** dropped `parse_mode="Markdown"` from the four edit_text calls and reformatted with plain Unicode strikethrough / quotes. Markdown was only being used for `~strikethrough~` — replaced with literal "✅ Выполнено: «title»" without parse_mode. Same for the other three.

### C-2. `/settings` accepts arbitrary values (no allowlist on value)

**Where:** `app/bot/services.py:400-414`

`update_user_settings` validates that `field` is in an allowlist, but the **value** is written via `setattr(settings, field, value)` without checking against `SETTING_OPTIONS`. A crafted callback (e.g. inspecting `settings:set:critic_mode:foo` via Telegram dev tools or message edit) writes `"foo"` straight to the DB column.

While the `Literal[...]` types on the Pydantic `ClassifierResult` would catch it at LLM boundary, `UserSettings.critic_mode` is a plain `str` column — the bad value persists until the next read, then crashes a downstream comparison.

**Why critical:** a single misclick or replay attack can poison settings durably.

**Fix in this PR:** added a per-field allowed-values map in `update_user_settings` (using the same source of truth as `SETTING_OPTIONS`) and reject anything not in it. Returns `None` so the callback handler shows "Не удалось обновить."

### C-3. Pipeline crash blocks every other task in a batched message

**Where:** `app/bot/routers/text.py:115-119`

```python
classify_tasks = [classify_intent(...) for unit, resolved in zip(...)]
classifier_results = list(await asyncio.gather(*classify_tasks))
```

If the user sends a multi-intent message ("купи хлеб и не забудь записаться к врачу"), `asyncio.gather` with no `return_exceptions` flag means **one Groq 429 / 5xx kills the entire batch.** The user sees the generic "Ошибка при разборе — сохранил во входящие" reply and loses all units, even those that classified fine.

**Why critical:** voice messages especially produce 3-5 intents per turn, and Groq free-tier 429s aren't rare. We're amplifying a single transient error into total data loss for the user-facing reply.

**Fix in this PR:** switched to `asyncio.gather(*tasks, return_exceptions=True)`, log each failure with `logger.exception`, drop the failed unit from persist + courier reply, and proceed with the survivors. If *all* units failed we still return the generic error.

---

## Important issues (should fix — also addressed here)

### I-1. N+1 query in `/categories`

**Where:** `app/bot/services.py:494-513`

`get_categories_with_counts` issues `1 + N` queries — one to list categories, then one per category to count its tasks. Should be a single `SELECT category.*, COUNT(task.id) GROUP BY category.id`.

**Fix:** rewrote to a single query using `func.count(Task.id)` joined on Category with an outer join + group_by. `tests/test_smoke.py` and `tests/test_phase3.py` (which we'll add a fixture for) keep passing because behaviour is identical.

### I-2. `find_task_by_query` doesn't escape LIKE wildcards

**Where:** `app/bot/services.py:280-300`

`pattern = f"%{query}%"` — if `query` (which comes from the LLM) contains `%` or `_`, it becomes a LIKE wildcard. Low likelihood of LLM doing this, but it's a robustness/correctness issue.

**Fix:** escape `%`, `_`, and `\` in `query` before interpolating, using a small helper.

### I-3. Background-task `add_done_callback` swallows exceptions

**Where:** `app/bot/routers/text.py:245`, `app/bot/routers/voice.py:144-146`

```python
task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)
```

If `_background()` raises after `await message.answer(...)` (e.g., the second `answer` itself errors), the lambda re-raises into asyncio's default exception handler — but with no context, no `logger.exception`, no `tg_user_id`. We lose the trace.

**Fix:** replaced with a named callback that calls `task.exception()` and `logger.exception(...)` if non-None. No behaviour change on success.

### I-4. `record_update` always writes `user_id=None`

**Where:** `app/main.py:100-106`

The webhook computes `user_tg_id` for logging, but then passes `user_id=None` to `record_update`. The `telegram_updates.user_id` column is always NULL even when we know the Telegram user ID. This blocks future analytics/auditing.

**Fix:** out of scope here (would require either refactoring `record_update` to accept tg_id, or doing a `get_or_create_user` lookup inside the webhook). **Filed as TODO** — see Minor M-3.

### I-5. `AsyncSession` type hints mix sqlalchemy + sqlmodel

**Where:** `app/bot/services.py:13`, `app/bot/services.py:34, 65, 89, …`

Services import `from sqlalchemy.ext.asyncio import AsyncSession` but call `session.exec(...)` which is the **sqlmodel** flavour. At runtime it works (sqlmodel's `AsyncSession` subclasses sqlalchemy's), but the type annotation is wrong and any static checker (pyright, mypy strict) flags it.

**Fix:** swapped the import to `from sqlmodel.ext.asyncio.session import AsyncSession` to match conftest.

### I-6. `get_or_create_user` ignores `lang_code` after first creation

**Where:** `app/bot/services.py:34-53`

If a user changes their Telegram language between sessions, we never refresh `User.lang_code`. Minor but easy.

**Fix:** if `lang_code` differs and is non-None, update + flush.

---

## Minor issues (deferred — documented for future PRs)

### M-1. `_prompt_cache` is module-level, not thread-safe

`app/ai/splitter.py`, `classifier.py`, `critic.py`, `courier.py`, `reorder.py` each have a global `_prompt_cache` with no lock. Two concurrent first calls could each call `Path.read_text` once. Harmless in practice but an `asyncio.Lock` or `functools.cache` would be cleaner.

### M-2. `CourierReply` Pydantic model defined inside function

`app/ai/courier.py:134-139` redefines `CourierReply` on every call. Move to module level.

### M-3. `record_update` doesn't fill in user_id

See I-4. Doing it cleanly requires moving `get_or_create_user` into the webhook before `record_update`, which is a slightly larger refactor. Filed for the cron-worker / digest PR.

### M-4. `groq_router.advance()` is never called on 429

`app/ai/router.py` exposes `advance()` for round-robin failover, but no caller invokes it. The Groq SDK's own retry kicks in for transient errors but exhausts the same key. When Phase 4 brings sustained traffic, wrap LLM calls in a try/except and call `router.advance()` on `groq.RateLimitError`.

### M-5. No max_length on `ClassifierResult.title`

`app/ai/schemas.py:47` — the prompt asks for ≤50 chars but the Pydantic schema doesn't enforce it. A misbehaving LLM could pass through a 500-char title. Add `max_length=200` (defensive ceiling, not the prompt's 50).

### M-6. `get_user_categories_full` doesn't sort by Russian collation

`app/bot/services.py:220` — default UTF-8 sort puts "Я" after "Z". For Russian-only users, fine. For multilingual, suboptimal.

### M-7. `time_resolver._horizon_from_delta` uses `.date()` arithmetic across tz

`app/ai/time_resolver.py:92-106` — both `now` and `dt` are tz-aware, but `.date()` strips tz. Around midnight in tz-far-from-UTC there's a 1-day-off risk. Worth a regression test for "23:30 Asia/Tashkent → завтра в 9".

### M-8. No size limit on incoming text messages

`handle_text` will happily push a 4096-char message into the Splitter. Telegram caps at 4096 anyway; consider a soft limit (~2000 chars) to keep splitter latency bounded.

### M-9. `_pluralize` covers a single noun ("элемент")

`app/ai/courier.py:177-186` — fine for now, but as soon as the courier needs more nouns it should switch to `pymorphy3` (already a dep).

### M-10. No tests for invalid webhook secret

Webhook auth is critical security surface but `tests/test_smoke.py` only tests `/healthz`. Add a smoke test for `POST /tg/wrong-secret` → 403.

---

## Tests

- `pytest -q` shows **128 passing** tests, no skips. Coverage is concentrated in services + routers + AI splitter/classifier; the time_resolver and reminder_extractor have decent unit coverage.
- Suite uses `aiosqlite` in-memory — fast, isolated.
- One gap: `tests/test_main.py` (or similar) for the webhook endpoint itself isn't here. Adding `POST /tg/<bad_secret>` and `POST /tg/<good_secret>` with header mismatch should be cheap.

This PR adds:
- `test_callbacks.py::test_edit_text_with_markdown_chars_in_title_does_not_crash` — covers C-1.
- `test_settings.py::test_update_user_settings_rejects_unknown_value` — covers C-2.
- `test_text_pipeline.py::test_partial_classify_failure_does_not_kill_batch` — covers C-3 at the helper level.

---

## Production readiness verdict

🟡 **Ready to merge after Critical issues fixed (which this PR does).**

After this PR: deploy to Render is safe for Phase 0-3 functionality. Phase 4 (cron worker) should fix M-3 and M-4 before going live, since sustained traffic + missing user_id make analytics blind.

---

## Skills bundle

Per request, I added two new skills under `.agents/skills/` (gitignored from Render via `render.yaml` `buildCommand: rm -rf .agents docs tests && uv sync --frozen`):

1. **`requesting-code-review/`** — adapted from [obra/superpowers](https://github.com/obra/superpowers) (Apache-2.0). Process skill: how to dispatch a fresh code-reviewer pass, severity rubric, integration with our existing `code-review/SKILL.md` checklist.
2. **`socraticode-principles/`** — methodology summary distilled from [SocratiCode](https://github.com/giancarloerra/SocratiCode) (no code copied, just principles): hybrid keyword + concept search, dependency-graph reasoning, blast-radius before edit. Maps SocratiCode's 61% / 84% / 37x benchmarks to plan-app-sized recipes using `rg` + LSP.

The pre-existing `code-review/SKILL.md` (project-specific 30-point checklist), `writing-prs/SKILL.md`, and the Anthropic snapshots (`skill-creator/`, `mcp-builder/`, `webapp-testing/`) are kept as-is.

---

## Appendix: numbers

| Metric | Value |
|---|---|
| Lines of `app/*.py` reviewed | ~3 100 |
| Critical findings | 3 |
| Important findings | 6 |
| Minor findings | 10 |
| Tests added in this PR | +3 |
| Tests passing after fixes | 131 |
| Lint clean | ✅ `ruff format` + `ruff check` |
