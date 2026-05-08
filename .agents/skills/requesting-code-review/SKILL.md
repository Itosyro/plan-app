---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements. Adapted from obra/superpowers (Apache-2.0).
---

# Requesting Code Review

Dispatch a focused code-reviewer pass (subagent or fresh chat) to catch issues before they cascade. The reviewer gets precisely crafted context for evaluation — never your session's history. This keeps the reviewer focused on the work product, not your thought process, and preserves your own context for continued work.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing a major feature
- Before merging to `main`

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing a complex bug

## How to Request

**1. Get git SHAs:**

```bash
BASE_SHA=$(git rev-parse origin/main)
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch the reviewer using the template at `code-reviewer.md`.** Required placeholders:

- `{WHAT_WAS_IMPLEMENTED}` — what you just built
- `{PLAN_OR_REQUIREMENTS}` — what it should do
- `{BASE_SHA}` — starting commit
- `{HEAD_SHA}` — ending commit
- `{DESCRIPTION}` — brief summary

**3. Act on feedback by severity:**

- **Critical** — fix immediately, block merge
- **Important** — fix before proceeding
- **Minor** — note for later
- **Pushback** — argue back if reviewer is wrong, with reasoning

## Plan-app conventions

Pair this skill with `.agents/skills/code-review/SKILL.md` (the project-specific 30-point checklist) and `.agents/skills/writing-prs/SKILL.md`. The reviewer should:

- Verify any model change has an Alembic migration.
- Check that LLM prompts live in `app/ai/prompts/<name>.md` (not inline strings).
- Run `uv run ruff format . && uv run ruff check . && uv run pytest -q` and report results.
- Cross-check against the relevant phase in `docs/ROADMAP.md` — no scope creep.

## Source

Adapted from [obra/superpowers `skills/requesting-code-review/SKILL.md`](https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md) (Apache-2.0). Plan-app conventions added at the bottom.
