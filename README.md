# plan-app

AI-powered task-planning Telegram bot, Russian-first.

You send a voice message or text — the bot transcribes it (Whisper), splits it into separate intents, classifies each one by category / time horizon / priority, validates the result with a stronger model, and stores everything in a database. Reminders are scheduled and delivered back through Telegram. Morning and evening digests summarise the day.

- **Bot**: [@daylirobot](https://t.me/daylirobot) (id `8642044324`)
- **Production**: <https://plan-app-t6nx.onrender.com> (Render Free, in-process scheduler)
- **Owner**: [@Itosyro](https://github.com/Itosyro)

## Status

**Phase 4c — closed (2026-05-09).** All three Critical findings from the 2026-05-09 super-review are fixed and in `main` (PR #43, commit `5702605`).

- `uv run pytest -q` → **197 passed**
- `uv run ruff format --check .` — clean
- `uv run ruff check .` — clean
- 5 Alembic migrations
- ~4400 LOC in `app/`, ~4400 LOC in `tests/`, 23 test files

Next up: either the 7 Important findings (`docs/REVIEW-2026-05-09.md`) as one PR, or **Phase 5 — Telegram Mini App** (React + Vite + Tailwind front-end on top of a JSON-API).

## What works end-to-end

1. **Inbound** — text or voice in Telegram (webhook). Voice goes through Groq Whisper (`whisper-large-v3`).
2. **AI pipeline** — Splitter (`llama-3.1-8b-instant`) → Time resolver (`dateparser` + `pymorphy3` + `razdel`, pure Python) → Classifier (`llama-3.3-70b-versatile`) → Critic (`qwen-qwq-32b`, gated on confidence).
3. **Persist** — `Task` / `Note` / `AiRun` / `TaskEvent` rows; if the intent has a `due_at`, two `Reminder` rows scheduled at offsets from `UserSettings.reminder_offsets_same_day` (defaults: 60 min and 15 min before).
4. **Reply** — Courier picks a confirmation phrase: 50/50 between `app/ai/courier.py::TEMPLATES` and `llama-3.1-8b-instant`. Source and tone are user-configurable via `/settings`.
5. **Background** — in-process scheduler ticks every 60 s: `tick_reminders` (sends pending reminders, retries up to `MAX_REMINDER_ATTEMPTS=3` then marks `failed`); `tick_digests` (morning/evening digests with idempotency guard so a sub-minute interval can't double-fire).
6. **Commands** — `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`, `/settings`. Inline buttons on task cards: ✅ done / ✏️ change category / 🗑 delete / move to another horizon.

## Stack

- **Python 3.12** (see `.python-version`)
- **aiogram 3** — Telegram bot (webhook with double-secret idempotency)
- **FastAPI** — single web service (bot webhook + future REST API + future mini-app static files)
- **SQLModel + Alembic** — database layer (PostgreSQL on Neon in prod, SQLite in tests)
- **Pydantic v2** — validation
- **groq-sdk + instructor** — Groq LLM client with structured output
- **dateparser, pymorphy3, razdel** — Russian NLP
- **uv** — package manager
- **ruff** — linter / formatter
- **pytest + pytest-asyncio + respx** — testing

## Layout

```
app/
  bot/        Telegram handlers (aiogram), routers, services, courier templates, digest builders
  api/        FastAPI routes for the future mini-app (placeholder)
  ai/         LLM pipeline (Splitter / Classifier / Critic / Courier) + Whisper + Reorder + GroqKeyRouter + prompts
  db/         SQLModel models + repositories + base.session_scope
  workers/    scheduler.py (tick_reminders / tick_digests) + runner.py (in-process loop)
  shared/     config / logging / time / constants
tests/        pytest suite (197 tests)
alembic/      database migrations (5)
memory/       user "stream of consciousness" archive (for future DSPy optimization)
docs/         project documentation
.agents/      development skills (16 SKILL.md files)
```

## Running locally

```bash
# 1. Clone
git clone https://github.com/Itosyro/plan-app.git
cd plan-app

# 2. Install (uv creates .venv automatically)
uv sync

# 3. Verify
uv run ruff format --check .
uv run ruff check .
uv run pytest -q   # → 197 passed

# 4. (Optional) start the dev server — needs secrets in .env
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, GROQ_API_KEYS, DATABASE_URL etc.
uv run uvicorn app.main:app --reload
```

Tests don't need any secrets — all Groq calls are mocked via `respx`.

## Documentation

Read in this order if you're new:

1. [`docs/HANDOFF-2026-05-09.md`](docs/HANDOFF-2026-05-09.md) — **the single file to give a new AI agent.** Covers everything below in one place.
2. [`docs/PLAN.md`](docs/PLAN.md) — what the bot does and why.
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data flow, schema.
4. [`docs/ROADMAP.md`](docs/ROADMAP.md) — phased implementation plan.
5. [`docs/PROGRESS.md`](docs/PROGRESS.md) — chronological log of merged PRs.
6. [`docs/REVIEW-2026-05-09.md`](docs/REVIEW-2026-05-09.md) — most recent code review (22 findings).
7. [`docs/REVIEW-findings.md`](docs/REVIEW-findings.md) — earlier review (Phase 4 mega-review, all C/I closed).
8. [`docs/IDEAS.md`](docs/IDEAS.md) — future ideas, open questions.
9. [`.agents/skills/CATALOG.md`](.agents/skills/CATALOG.md) — index of 16 development skills.

## Contributing / development conventions

- **Docstrings in English**, comments in Russian for tricky bits ("why" not "what").
- **Never** use `Any`, `getattr`, `setattr` to dodge typing. See `.agents/skills/defensive-programming/SKILL.md`.
- **No `print()` in production** — use `app.shared.logging.get_logger`.
- **No inline prompts** — they live in `app/ai/prompts/<name>.md`.
- **Naive-UTC discipline** — every persisted timestamp is tz-naive and treated as UTC. Render to user's TZ only at display time via `app/shared/time.format_due_local()`.
- **Allow-list validation** — every user-editable setting is checked against an exhaustive frozenset, no arbitrary strings reach the DB.
- **No `parse_mode`** on user-controlled strings — task titles routinely contain `*`, `_`, `[` which break Telegram's Markdown parser.
