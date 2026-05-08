---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior in plan-app, before proposing fixes. Adapted from obra/superpowers (MIT) with plan-app specifics.
---

# Systematic Debugging

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

---

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

---

## When to Use

Use for ANY technical issue:
- Test failure (`pytest -q` red)
- Bug in prod (Render logs)
- Unexpected behavior (bot reply weird, scheduler skipping)
- Performance problem (cold start > 3 min, latency spike)
- CI failure (ruff / pytest in GH Actions)

**Especially when:**
- Under time pressure ("just one quick fix")
- Already tried 1+ fixes
- Don't fully understand the issue

---

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read errors carefully.** Stack trace top to bottom — exact file/line/code. Don't skim.
2. **Reproduce consistently.** Exact steps. Every time? If not → gather more data, don't guess.
3. **Check recent changes.** `git log --oneline -10`, `git diff HEAD~3` — what changed?
4. **Trace data flow** through layers. plan-app has: `Telegram → /tg/<secret> → dispatcher → router → service → DB | AI → DB`. Add temporary `logger.info(...)` at each boundary, run once, read evidence, then form hypothesis.
5. **Check assumptions about clocks/tz.** Many plan-app bugs hide here — DB columns are naive-UTC (see `app/shared/time.py`). If you see weird dates, write a tiny script to print `now()` from each layer.

### Phase 2: Pattern Analysis

1. **Find a working example** of the same pattern in the repo. `rg -n "<symbol>"` first, `lsp_tool goto_references` second.
2. **Compare working vs broken.** List every difference. Don't dismiss "that can't matter".
3. **Read the related skill** in `.agents/skills/` — most plan-app gotchas are documented (`aiogram-3`, `groq-tips`, `russian-nlp`).

### Phase 3: Hypothesis & Test

1. State hypothesis explicitly: *"X is the root cause because Y"*. Write it in the PR description or comment.
2. Make the **smallest** possible change that proves or disproves it.
3. Run the failing test → see green → only then continue.
4. Hypothesis wrong? Form a new one. **Don't pile fixes on top.**

### Phase 4: Fix

1. **Add a failing test that reproduces the bug.** plan-app uses `pytest -q` + `pytest-asyncio` + `respx` (see `.agents/skills/testing-async-python/SKILL.md`).
2. Implement minimal fix.
3. Verify: failing test passes, existing tests stay green, `uv run ruff format . && uv run ruff check .` clean.
4. **If 3+ fixes failed in a row:** STOP. The architecture is wrong, not the implementation. Discuss with your partner before fix #4.

---

## Red Flags — STOP and follow the process

- "Quick fix for now, investigate later"
- "Just try X and see if it works"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- Proposing fix without tracing data flow
- Each new fix reveals a new problem in a different place → architectural issue

---

## plan-app specifics

| Symptom | First place to look |
|---|---|
| Telegram returns 400 / "can't parse entities" | `parse_mode="Markdown"` on user-controlled string. Drop it (see `docs/REVIEW-findings.md::C-2`). |
| `datetime` comparison fails on Postgres but works on SQLite | naive vs tz-aware. Use `app/shared/time.py::utcnow_naive()` everywhere (see `docs/REVIEW-findings.md::C-1`). |
| Reminder fires twice / never | `Reminder.status` transitions in `app/workers/scheduler.py::tick_reminders` — check WHERE clause matches `pending` before update. |
| Webhook 502 on Render | Free tier idle spin-down — first request takes ~3 min cold start. See `docs/RENDER.md`. |
| `dateparser` returns "today" for "во вторник" | Check `PREFER_DATES_FROM=future` + post-process to bump weekday. See `russian-nlp/SKILL.md::1`. |
| Groq 429 in tests | You hit live API. Mock with `respx` — see `groq-tips/SKILL.md::8`. |
| Update logged as `kind=Update` | Use `_classify_update` in `app/main.py`. `type(update).__name__` is always `"Update"`. |

---

## Source

Adapted from [obra/superpowers `skills/systematic-debugging`](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) (MIT). plan-app specifics added at the bottom — they reflect real findings from `docs/REVIEW-findings.md`.
