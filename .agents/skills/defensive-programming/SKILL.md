---
name: defensive-programming
description: Use when adding code that touches user input, database writes, or runtime configuration. Captures the patterns that came out of the plan-app mega-review (allow-lists, no getattr, naive-UTC, parse_mode discipline).
---

# Defensive Programming — plan-app patterns

Most of the bugs found in `docs/REVIEW-findings.md` weren't logic errors — they were missing guards. This skill is the short list of guards we expect on every PR.

---

## 1. Allow-list at every external boundary

Every value coming from outside the process (Telegram callback, HTTP body, env var, LLM output) **must** pass through an allow-list before it touches anything important.

```python
# Bad — getattr bypasses the type-checker AND the allow-list
value = getattr(settings, field, None)

# Good — explicit mapping; type-checker proves every branch
if field == "morning_digest_at":
    return settings.morning_digest_at
if field == "critic_mode":
    return settings.critic_mode
return "—"
```

See `app/bot/routers/settings.py::_setting_value` and `docs/REVIEW-findings.md::I-1`.

**Heuristic:** if you find yourself reaching for `getattr` / `setattr` / `Any`, that's a bug, not a shortcut.

---

## 2. Never ship `parse_mode="Markdown"` over user-controlled content

Telegram's Markdown parser is strict and will **400 Bad Request** if a user-controlled string contains `*`, `_`, `[`, `` ` ``. `task.title` and `note.title` are user-controlled.

```python
# Bad — task.title may contain Markdown-active chars
await message.answer(f"*{title}*\n• {task.title}", parse_mode="Markdown")

# Good — plain text + emoji decoration
await message.answer(f"📋 {title}\n• {task.title}")
```

See `app/bot/routers/commands.py` (post-fix) and `docs/REVIEW-findings.md::C-2`.

**Heuristic:** if the string contains user input, `parse_mode` is forbidden by default.

---

## 3. Single naive-UTC clock for DB writes

All `DateTime` columns in plan-app are tz-naive. Writing tz-aware values silently strips the tz on insert, which leads to mismatched comparisons later.

```python
from app.shared.time import utcnow_naive

reminder.sent_at = utcnow_naive()      # always naive UTC
cutoff = utcnow_naive()
```

Never use `datetime.utcnow()` (deprecated) or `datetime.now(UTC)` (tz-aware) directly in writers. See `app/shared/time.py` and `docs/REVIEW-findings.md::C-1`.

---

## 4. Idempotency on every webhook handler

Telegram retries on non-200, so handlers must be idempotent.

```python
# app/main.py
existing = await record_update(session, update.update_id)
if not existing:
    return {"status": "duplicate"}    # already processed
```

Same pattern lives in callback handlers (`/cb`) — guard before mutating state. Future enhancement: catch `IntegrityError` from a unique constraint as a second line of defence (see `docs/REVIEW-findings.md::M-1`).

---

## 5. Escape `LIKE` wildcards on user-supplied search terms

Postgres / SQLite `LIKE` treats `%` and `_` as wildcards. Forgetting to escape them leaks the schema implicitly.

```python
# app/bot/services.py
def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

stmt = select(Task).where(Task.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
```

See `docs/REVIEW-findings.md::Positive patterns`.

---

## 6. Strict callback-data parsing

`callback_data` is ≤ 64 bytes and arbitrary — never `eval` it, never trust the integer suffix.

```python
parts = callback.data.split(":")
if len(parts) != 3 or parts[0] != "task":
    await callback.answer("bad payload"); return
try:
    task_id = int(parts[2])
except ValueError:
    await callback.answer("bad id"); return
```

`F.data.startswith(...)` is **not** a substitute for explicit parsing — it only routes.

---

## 7. Strict HH:MM matching for digest schedules

```python
def _matches_hhmm(now_local: datetime, hhmm: str) -> bool:
    return now_local.strftime("%H:%M") == hhmm
```

Don't use `now.hour == h and now.minute == m` — drifts when scheduler tick is late. See `app/bot/digest.py::_matches_hhmm`.

---

## 8. Exception isolation in long-running loops

The scheduler tick must keep ticking even if one user blows up.

```python
# app/workers/scheduler.py::tick_reminders (simplified)
for reminder in due:
    try:
        await _send_one(reminder)
    except Exception:
        logger.exception("reminder failed", extra={"reminder_id": reminder.id})
        # don't re-raise — next reminder gets a chance
```

Never let a single bad row kill the whole minute's worth of work.

---

## 9. PII discipline in logs

Never log message text, voice contents, or AI raw responses with user content. Allowed: `user_id`, lengths, model name, latency, token counts.

```python
# Bad
logger.info("user message: %s", message.text)
# Good
logger.info("msg", extra={"user_id": uid, "len": len(message.text or "")})
```

See `.agents/skills/aiogram-3/SKILL.md::8` and `groq-tips/SKILL.md::6`.

---

## 10. Type-checker is your second pair of eyes

If a change disables type-checking (`# type: ignore`, `Any`, `cast(...)`), document **why** in a code comment **and** the PR description. The default answer to "do I need this" is "no".

---

## Checklist for any PR that touches user-facing code

- [ ] No `parse_mode="Markdown"` over `task.title` / `note.title` / category names
- [ ] No `getattr` on a Pydantic / SQLModel instance with user-supplied field
- [ ] All DB writes use `utcnow_naive()` (or a function that calls it)
- [ ] Every webhook / callback has an idempotency guard
- [ ] User search terms escape `LIKE` wildcards
- [ ] `callback_data` is parsed with explicit length check + `int()` try/except
- [ ] Scheduler-loop exceptions are caught + logged + swallowed
- [ ] Logs have no PII (no `message.text`, no raw LLM input)

---

## Source

Distilled from `docs/REVIEW-findings.md` and the Phase 4 mega-review fixes (PR #37). Each rule has a concrete failure case in the repo's history.
