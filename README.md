# plan-app

AI-powered task planning bot for Telegram (Russian-first).

You send voice or text — the bot transcribes it (Whisper), splits into separate intents, classifies them by category / time horizon / priority, validates the result with a stronger model, and stores everything in a database. Reminders are scheduled and delivered back through Telegram.

## Status

This repository is being rebuilt from scratch in Python. The original TypeScript implementation has been removed; its history is preserved in git (last TS commit: `6cc851d`).

Current phase: **Phase 0 — cleanup and Python scaffolding** (this PR).

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full plan.

## Stack

- Python 3.12
- aiogram 3 — Telegram bot (webhook)
- FastAPI — single web service (bot webhook + REST API + mini-app static files)
- SQLModel + Alembic — database layer (PostgreSQL via Neon)
- Pydantic v2 — validation
- groq-sdk + instructor — Groq LLM client with structured output
- dateparser, pymorphy3, razdel — Russian NLP
- uv — package manager
- ruff — linter / formatter
- pytest — testing

## Layout

```
app/
  bot/        Telegram handlers (aiogram)
  api/        FastAPI routes for the mini-app
  ai/         LLM pipeline (Splitter → Classifier → Critic) + Groq key router
  db/         SQLModel models + repositories
  workers/    Cron worker (reminders, daily digests)
  shared/     Config, logging, common helpers
tests/        pytest suite
alembic/      database migrations
memory/       user "stream of consciousness" archive (for future DSPy optimization)
docs/         project documentation (plan, architecture, roadmap, progress, ideas)
.agents/      development skills and best-practice references
```

## Running locally (placeholder)

The app is not runnable yet — Phase 0 only puts the scaffolding in place. Phase 1 will add the working webhook bot. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Documentation

- [`docs/PLAN.md`](docs/PLAN.md) — what the bot does and why
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data flow, schema
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — phased implementation plan
- [`docs/PROGRESS.md`](docs/PROGRESS.md) — what is done, what is in flight
- [`docs/IDEAS.md`](docs/IDEAS.md) — future ideas, open questions
