# plan-app

AI-powered task-planning Telegram bot, Russian-first.

You send a voice message or text — the bot transcribes it (Whisper), splits it into separate intents, classifies each one by category / time horizon / priority, validates the result with a stronger model, and stores everything in a database. Reminders are scheduled and delivered back through Telegram. Morning and evening digests summarise the day.

- **Bot**: [@daylirobot](https://t.me/daylirobot) (id `8642044324`)
- **Production**: <https://plan-app-t6nx.onrender.com> (Render Free, in-process scheduler)
- **Owner**: [@Itosyro](https://github.com/Itosyro)

## Status

**Audit round 1 — closed (2026-07-26).** A 15-agent audit with adversarial
verification found 57 confirmed bugs; all 7 Critical and 27 of 29 Important
are fixed in `main` (PR #187). Full report: [`docs/audit/2026-07-26-audit.md`](docs/audit/2026-07-26-audit.md).

- `uv run pytest -q` → **630 passed**
- `uv run ruff format --check .` / `uv run ruff check .` / `uv run mypy app` — clean
- `webapp`: `npx tsc --noEmit` + `npm run build` — clean
- 19 Alembic migrations
- ~14 100 LOC in `app/`, ~14 200 LOC in `tests/` (53 test files), ~10 600 LOC in `webapp/src/`

The project now runs a **goal loop**: every ~5 hours a fresh-eyes audit round
re-examines the system, fixes what it finds, and merges autonomously (see
[`.claude/skills/audit-loop/SKILL.md`](.claude/skills/audit-loop/SKILL.md)).
Next milestone beyond the loop: PWA → Capacitor → offline (mobile app path,
see [`docs/plans/2026-07-26-audit-improvements.md`](docs/plans/2026-07-26-audit-improvements.md)).

## What works end-to-end

1. **Inbound** — text or voice in Telegram (webhook). Voice goes through Groq Whisper (`whisper-large-v3`). Replies/forwards are accepted as pipeline input too.
2. **AI pipeline** — Intent detector + Splitter (`openai/gpt-oss-20b`) → Time resolver (`dateparser` + `pymorphy3` + `razdel`, pure Python, user-timezone aware) → Classifier (`openai/gpt-oss-120b`) → Critic (same model, gated on confidence). All structured output via `instructor` in `Mode.TOOLS`. Model IDs live in `app/ai/models.py` and are env-overridable (`GROQ_MODEL_*`).
3. **Persist** — `Task` / `Note` / `AiRun` / `TaskEvent` rows (tasks support subtasks via `parent_id`); if the intent has a `due_at`, `Reminder` rows are scheduled at offsets from `UserSettings.default_reminder_offsets` (defaults: 60 min and 15 min before). Messages producing ≥2 items or anything low-confidence are flagged `needs_review` for the Mini-App «Входящие» tab.
4. **Reply** — Courier picks a confirmation phrase: 50/50 between `app/bot/courier_templates.py` and the light model. Source and tone are user-configurable via `/settings`.
5. **Background** — in-process scheduler ticks every 60 s: `tick_reminders` (sends pending reminders, skips/cancels ones whose task is already done, retries up to `MAX_REMINDER_ATTEMPTS=3` then marks `failed`); `tick_digests` (morning/evening digests, gate flipped after a successful send and committed per user); `purge_trash` (24 h retention).
6. **Commands** — `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`, `/settings`. Inline buttons on task cards: ✅ done / ✏️ change category / 🗑 delete / move to another horizon.
7. **Voice editing** — «отметь X», «перенеси X на пятницу», «напомни о X в 15:00», «переименуй…», category and note intents — all resolved against existing tasks, with undo snapshots.
8. **Mini App** — 5 tabs (Задачи / Заметки / Календарь / Входящие / Настройки) + boards (Excalidraw), kanban, drag-n-drop, search, trash and completed screens. Auth via Telegram `initData`.

## Stack

- **Python 3.12** (see `.python-version`)
- **aiogram 3** — Telegram bot (webhook with double-secret idempotency)
- **FastAPI** — single web service (bot webhook + `/api` REST + Mini-App static bundle at `/app`)
- **SQLModel + Alembic** — database layer (PostgreSQL on Supabase in prod, SQLite in tests)
- **Pydantic v2** — validation
- **groq-sdk + instructor** (`Mode.TOOLS`) — Groq LLM client with structured output
- **dateparser, pymorphy3, razdel** — Russian NLP
- **React 18 + Vite + Tailwind + dnd-kit + Excalidraw** — Telegram Mini App (`webapp/`)
- **uv** — package manager
- **ruff + mypy** — linter / formatter / type checker
- **pytest + pytest-asyncio + respx** — testing

## Layout

```
app/
  bot/        Telegram handlers (aiogram), routers, services, edit executor, courier templates, digest builders
  api/        FastAPI routes for the Mini App (/api/tasks, notes, boards, inbox, me, trash, …) + initData auth
  ai/         LLM pipeline (Intent / Splitter / Classifier / Critic / Courier) + Whisper + time resolver + model registry + prompts
  db/         SQLModel models + repositories + base.session_scope
  workers/    scheduler.py (tick_reminders / tick_digests / purge_trash) + runner.py (in-process loop) + keepalive
  shared/     config / logging / time / sentry / constants
webapp/       Telegram Mini App (React + Vite + Tailwind); built bundle is served at /app
tests/        pytest suite (630 tests, 53 files)
alembic/      database migrations (19)
memory/       user "stream of consciousness" archive (for future DSPy optimization)
docs/         project documentation (incl. docs/audit/ — audit rounds, docs/plans/ — plans)
.agents/      development skills (20 SKILL.md files, see CATALOG.md)
.claude/      project skills for Claude Code (gates, deploy-check, audit-loop)
```

## Running locally

```bash
# 1. Clone
git clone https://github.com/Itosyro/plan-app.git
cd plan-app

# 2. Install (uv creates .venv automatically)
uv sync

# 3. Verify (same gates as CI — or run the `/gates` skill)
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest -q   # → 630 passed

# 4. Mini App (optional — needed for the /app route and its two tests)
cd webapp && npm ci && npx tsc --noEmit && npm run build && cd ..

# 5. (Optional) start the dev server — needs secrets in .env
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, GROQ_API_KEYS, DATABASE_URL etc.
uv run uvicorn app.main:app --reload
```

Tests don't need any secrets — all Groq calls are mocked via `respx`.

## Documentation

Read in this order if you're new:

1. [`docs/HANDOFF.md`](docs/HANDOFF.md) — **the single file to give a new AI agent.** Its header carries the freshest delta; the rest is background.
2. [`docs/PROGRESS.md`](docs/PROGRESS.md) — chronological log of merged PRs, newest first.
3. [`docs/audit/`](docs/audit/) — audit rounds with every finding, its verdict and its fix.
4. [`docs/PLAN.md`](docs/PLAN.md) — what the bot does and why.
5. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data flow, schema.
6. [`docs/ROADMAP.md`](docs/ROADMAP.md) — phased implementation plan + current status.
7. [`docs/plans/`](docs/plans/) — per-wave plans (latest: the audit-loop wave + the mobile-app path).
8. [`docs/IDEAS.md`](docs/IDEAS.md) — future ideas, open questions.
9. [`.agents/skills/CATALOG.md`](.agents/skills/CATALOG.md) — index of the development skills.

## Contributing / development conventions

- **Docstrings in English**, comments in Russian for tricky bits ("why" not "what").
- **Never** use `Any`, `getattr`, `setattr` to dodge typing. See `.agents/skills/defensive-programming/SKILL.md`.
- **No `print()` in production** — use `app.shared.logging.get_logger`.
- **No inline prompts** — they live in `app/ai/prompts/<name>.md`.
- **Naive-UTC discipline** — every persisted timestamp is tz-naive and treated as UTC. Render to user's TZ only at display time via `app/shared/time.format_due_local()`.
- **Allow-list validation** — every user-editable setting is checked against an exhaustive frozenset, no arbitrary strings reach the DB.
- **No `parse_mode`** on user-controlled strings — task titles routinely contain `*`, `_`, `[` which break Telegram's Markdown parser.
