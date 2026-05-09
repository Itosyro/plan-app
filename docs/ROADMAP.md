# ROADMAP — фазы

Каждая фаза = отдельный PR. Маленькие PR, ревьюить и откатывать удобнее.

> **Status (на 2026-05-09):**
> Phase 0..4 — **done и в проде**. Работает: голосовое/текстовое
> сообщение → задачи + заметки + напоминания, утренний/вечерний
> дайджест, команды `/today /week /...`, callback-кнопки, /settings.
> 243 теста, ruff/mypy clean, https://plan-app-t6nx.onrender.com .
>
> Все critical (C-1..C-6) и important (I-1..I-8) findings из
> `docs/REVIEW-2026-05-09-v2.md` — закрыты.
>
> Что осталось:
> - Phase 5 (Mini App) — **не начат**.
> - Phase 6 (Polish) — **частично** (structlog ✓, mypy strict ✓; golden-evals/DSPy/backup ✗).
> - Minor M-1..M-9 из v2-ревью — открыты.

---

## Phase 0 — Cleanup + Python skeleton ✅ DONE

**Цель:** убрать всё лишнее, поставить пустой Python-каркас, который:
- проходит `ruff check` и `pytest`,
- читается и понятно куда что класть.

**Содержимое:**
- удалены `Vault/`, `Projects/`, `.hermes-backup/`, `AGENTS.md`, `PROJECTS.md`, весь TS-код;
- новый `README.md`;
- `docs/` (PLAN, ARCHITECTURE, ROADMAP, PROGRESS, IDEAS);
- `.agents/skills/` — папка для скиллов и best-practice референсов;
- `pyproject.toml` (uv-совместимый), `.python-version`, `ruff.toml`, `Dockerfile`;
- `app/{bot,api,ai,db,workers,shared}/` со скелетами;
- `tests/` со smoke-тестом;
- `alembic/` (без миграций пока);
- `memory/` с README;
- `render.yaml` обновлён под Python (но без авто-деплоя).

**Не делаем:** никакой бизнес-логики, никаких реальных хендлеров, никакого LLM-кода.

**Критерий готовности:**
- `uv sync` ставит зависимости.
- `uv run ruff check` — чисто.
- `uv run pytest` — smoke-тест проходит.
- `docker build .` — собирается.

---

## Phase 1 — Минимальный бот (webhook + БД) ✅ DONE

**Цель:** бот в Telegram отвечает на `/start`, принимает текст, сохраняет его в `inbox_entries`. **Без AI.**

**Содержимое:**
- `app/main.py` — FastAPI приложение с webhook-эндпоинтом `/tg/<secret>`;
- aiogram Dispatcher, хендлеры `/start`, `/help`, текст;
- SQLModel: `User`, `InboxEntry`, `TelegramUpdate`;
- Alembic: первая миграция;
- `app/shared/config.py` (Pydantic Settings);
- регистрация webhook на старте через lifespan;
- идемпотентность по `update_id`;
- Dockerfile проверен;
- деплой на Render Free + Neon;
- `/start` спрашивает часовой пояс и сохраняет.

**Критерий готовности:**
- бот реально работает в Telegram;
- сообщения видны в Postgres;
- e2e тест с моком Telegram-update проходит.

---

## Phase 2 — AI-пайплайн (Splitter + Classifier + Critic + Time Resolver) ✅ DONE

**Цель:** голосовое/текстовое сообщение превращается в задачи и заметки.

Делается тремя подPR'ами ≤ 400 LOC.

### Phase 2.1 — Splitter + AI infrastructure ✔ (PR #12, смерджен 2026-05-08)

**Содержимое:**
- `app/ai/router.py` — `GroqKeyRouter` (round-robin по ключам Groq, `advance()`, `async_client()`);
- `app/ai/schemas.py` — Pydantic-модели `IntentUnit`, `SplitterResult`;
- `app/ai/splitter.py` — `split_message()` через `llama-3.1-8b-instant` + `instructor` (temperature 0.0);
- `app/ai/prompts/splitter.md` — системный промпт (3 few-shot примера на русском);
- интеграция в text-роутер: splitter в фоне (`asyncio.create_task`), результат логируется;
- 10 новых тестов (5 GroqKeyRouter + 5 Splitter с моком Groq через `respx`).

### Phase 2.2 — Classifier + русский NLP (следующая)

**Содержимое:**
- `app/ai/classifier.py` — `llama-3.3-70b-versatile`, авто-создание категорий;
- `app/ai/time_resolver.py` — `dateparser` + русский препроцессор, чистый Python (pymorphy3 / razdel удалены в M-1 как unused);
- ~~`app/ai/reminder_extractor.py`~~ — удалён в I-5 (superseded time_resolver + classifier);
- SQLModel: `Category`, `Horizon`, `Task`, `Note`, `AiRun`, `TaskEvent`;
- Alembic: миграция;
- бот сохраняет задачи и отвечает детерминированным резюме.

### Phase 2.3 — Critic + Whisper + Courier

**Содержимое:**
- `app/ai/critic.py` — `qwen-qwq-32b`, режим `confidence` по умолчанию;
- транскрибация через Groq Whisper (`whisper-large-v3`);
- `app/ai/courier.py` — шаблоны + LLM (50/50);
- перестановка задач голосом (минимальная: «перенеси Х на Y»);
- e2e тесты на 5–10 типовых русских фраз.

**Критерий готовности (Phase 2 целиком):**
- голос «утром пробежка, в 11 совещание, до пятницы отчёт, обед через час напомни» → 4 задачи + 1 напоминание;
- юзер задал перестановку → задача обновлена.

---

## Phase 3 — Категории, горизонты, ручное редактирование ✅ DONE (кроме экспорта в xlsx)

**Цель:** юзер может управлять структурой через бот.

**Содержимое:**
- команды бота: `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`;
- инлайн-кнопки на карточке задачи: «выполнено», «перенести», «удалить», «изменить категорию»;
- настройки `/settings`: критик режим, дефолтное напоминание, утренний/вечерний дайджест, часовой пояс, стиль ответа;
- API эндпоинты для будущего mini-app (но без UI пока);
- импорт/экспорт в `.xlsx` через `openpyxl`.

---

## Phase 4 — Напоминания и дайджесты (in-process scheduler) ✅ DONE

**Цель:** бот сам присылает что нужно когда нужно.

> ⚠️ **Отклонение от плана:** изначально планировался отдельный
> Render Cron Job. Реально Render Free такого не даёт, поэтому
> сделали **in-process scheduler** в том же web-сервисе
> (`app/workers/runner.py` + `app/workers/scheduler.py`,
> `start_inproc_scheduler` поднимается из FastAPI lifespan).
> Внешний пинговалка `cron-job.org → /healthz` каждые 5 минут
> держит free-instance тёплым, чтобы scheduler не засыпал.

**Содержимое (что реально лежит в коде):**
- `app/workers/runner.py` — `run_scheduler_loop` запускает tick'и
  каждые 60 секунд внутри web-процесса;
- `app/workers/scheduler.py` — `tick_reminders()`: claim-pattern
  (pending → processing → sent/failed) + per-row commit, защита
  от crash mid-batch;
- `app/bot/digest.py` — `tick_digests()`: catch-up семантика
  (`local_now >= scheduled_time` + `last_*_digest_on != today`),
  day-1 safeguard для свежих юзеров;
- `Reminder.attempts` + `MAX_REMINDER_ATTEMPTS = 3` — встроенные
  retry'и через состояние (без отдельной таблицы processing_jobs).

---

## Phase 5 — Telegram mini-app 🟡 NOT STARTED

**Цель:** красивый веб-UI внутри Telegram.

> Можно начинать. Бот стабилен, БД устаканена, API-эндпоинтов пока
> 0 — `app/api/__init__.py` пустой. Mini-app — это самостоятельный
> большой кусок (≥ 5 PR), который можно дробить на подэтапы:
> 5.1 backend API, 5.2 каркас фронта, 5.3 список+фильтры,
> 5.4 канбан + drag-n-drop, 5.5 календарь.

**Содержимое:**
- **5.1 Backend API.** REST под `/api/*`, auth через Telegram
  `initData` (HMAC-валидация), эндпоинты:
  - `GET /api/me` — текущий юзер + настройки;
  - `GET /api/tasks?horizon=...&category=...` — список;
  - `PATCH /api/tasks/:id` — изменить horizon / status / category;
  - `DELETE /api/tasks/:id`;
  - `GET /api/notes`, `GET /api/categories`, `GET /api/inbox/:id`
    (для просмотра оригинального транскрипта).
- **5.2 Каркас фронта.** React + Vite + Tailwind в `webapp/`,
  собирается в статику, отдаётся `StaticFiles` из FastAPI на
  `/app/*`. WebApp init script + theme подхват из Telegram.
- **5.3 Список с фильтрами.** Простой grid задач, фильтры по
  горизонту/категории, кнопки done/move/delete (вызывают API).
- **5.4 Канбан + drag-n-drop.** dnd-kit, колонки = горизонты,
  drag меняет horizon_id через PATCH.
- **5.5 Календарный вид.** FullCalendar (или fullcalendar/react),
  события по `due_at`, drag по сетке двигает `due_at`.
- **5.6 Карточка задачи.** Модалка/sheet с описанием, оригиналом
  inbox_entry (текст или voice player для голоса), TaskEvent-историей.

**Критерий готовности:** юзер может пользоваться ботом ИЛИ mini-app
полностью equivalent'но; всё что есть в mini-app — отражается в боте
и наоборот.

---

## Phase 6 — Polish, наблюдаемость, эвалы 🟡 PARTIAL

**Цель:** довести до состояния «не стыдно показать».

**Что уже есть:**
- ✅ structlog с JSON-логами (`app/shared/logging.py`);
- ✅ mypy strict — проходит на всём коде (`uv run mypy`);
- ✅ ruff format + ruff check в CI;
- ✅ idempotency на webhook'ах + claim-pattern на reminders.

**Что осталось:**
- ❌ **LLM-эвалы:** golden-set из 50 русских фраз
  (`tests/golden/ru/*.json`), прогон через пайплайн, сравнение с
  эталоном. Метрика: % правильных category/horizon/priority.
- ❌ **DSPy** — автоподбор промптов на основе golden-set.
- ❌ **Backup БД.** Neon free даёт PITR на 7 дней. Дополнительно
  стоит сделать nightly `pg_dump → S3/R2/B2` (cron-job.org →
  endpoint в нашем web-сервисе который дампит и шлёт в bucket).
- ❌ **Sentry/Logfire** — на free tier бесплатно, но требует SDK
  + DSN в ENV. Пока не подключено.
- ❌ **Расширенный README.** Сейчас README.md есть, но без
  скриншотов, GIF демо, deployment guide.
- ❌ **pre-commit hooks** — намеренно не делаем (сильно тормозит
  работу AI-агентов и нет в репо `.pre-commit-config.yaml`).
- ❌ **Закрытие Minor M-1..M-9** из v2-ревью — мелкие гигиенические
  фиксы, см. `docs/REVIEW-2026-05-09-v2.md`.

---

## Параллельные треки

- **Скиллы и best practices** — пополняем `.agents/skills/` по мере находок;
- **`docs/PROGRESS.md`** — обновляем после каждого PR;
- **`memory/`** — копим транскрипты для DSPy.
