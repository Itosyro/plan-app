# PROGRESS

Хронологический лог сделанного. Каждая запись = один PR.

Обновляй этот файл в каждом PR в самом конце, перед коммитом.

---

## 2026-05-08 — Phase 2.2b: DB models + persistence + pipeline integration

**Сделано:**
- `app/db/models.py` — 6 новых SQLModel-таблиц: `Category`, `Horizon`, `Task`, `Note`, `AiRun`, `TaskEvent`. Все с FK на `users`, индексами по `user_id`, `_utcnow` default.
- `alembic/versions/0002_phase_2_2_models.py` — миграция: создаёт 6 таблиц + индексы, downgrade дропает в обратном порядке.
- `app/bot/services.py` — 5 новых функций: `get_or_create_category`, `get_or_create_horizon`, `get_user_categories`, `persist_classification`, `log_ai_run`.
- `app/bot/routers/text.py` — полная цепочка: split → time_resolver → classify → persist → ответ с резюме. GroqKeyRouter — singleton (lazy init). Ответ юзеру: «Разобрал на N элемент(ов): 📌 задача / 📝 заметка: title [category]».
- `tests/test_persistence.py` — 7 тестов: category CRUD, horizon CRUD, user_categories, persist task + events, persist note, ai_run log, category reuse.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 47 passed (24 старых + 16 Phase 2.2a + 7 новых).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Critic — Phase 2.3.
- Whisper — Phase 2.3.
- `call_with_retry` — перенесён в Phase 2.3 (пока хватает одного ключа).

---

## 2026-05-08 — Phase 2.1: Splitter + AI infrastructure (PR #12)

**Сделано:**
- `app/ai/router.py` — `GroqKeyRouter`: round-robin пул API-ключей Groq с методами `advance()` и `async_client()`.
- `app/ai/schemas.py` — Pydantic-модели `IntentUnit` и `SplitterResult` для структурированного вывода LLM.
- `app/ai/splitter.py` — `split_message()`: вызывает `llama-3.1-8b-instant` через `instructor` (structured output, temperature 0.0). Сообщения < 2 символов пропускаются без вызова LLM.
- `app/ai/prompts/splitter.md` — системный промпт по структуре ROLE → TASK → CONSTRAINTS → OUTPUT → EXAMPLES. 3 few-shot примера на русском.
- `app/bot/routers/text.py` — интеграция: после сохранения в inbox splitter запускается в фоне (`asyncio.create_task`), результат логируется. Задачи пока не сохраняются (Phase 2.2).
- `tests/test_groq_router.py` — 5 тестов на ротацию ключей.
- `tests/test_splitter.py` — 5 тестов с мокнутым Groq через `respx`.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 24 passed (14 старых + 10 новых).
- PR ≤ 400 LOC (361 строк), одна тема.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Classifier, Critic, Whisper — Phase 2.2 / 2.3.
- Сохранение задач/заметок в БД — Phase 2.2 (нужны модели Task/Note).
- `call_with_retry` с retry/backoff — добавится в Phase 2.2 когда появится Classifier.

---

## 2026-05-08 — Phase 4: e2e-проверка живого бота (`@daylirobot`)

**Сделано:**
- Юзер прошёл онбординг в Telegram: `/start` → имя «Юсуф» → таймзона `Europe/Moscow` → бот ответил блоком дефолтов (08:00/21:00, `[60,15]`/`[1440,60]`, critic=`confidence@0.7`, courier=`mix`, `deadline_sunday`).
- Свободный текст («Так, сегодня написать… Олег…», «окей») и команда `/settings` корректно проваливаются в text-роутер и возвращают плейсхолдер «AI-разбор подключу в Phase 2».
- Сверка с Neon-БД (5 таблиц после миграции) показала ожидаемое состояние:
  - `users` — 1 строка (`telegram_id=2007532633`, `display_name='Юсуф'`, `tz='Europe/Moscow'`, `onboarded_at` заполнен).
  - `user_settings` — 1 строка (все дефолты совпадают с обещанным боту блоком).
  - `inbox_entries` — 3 строки (две произвольных реплики + `/settings`, все `kind='text'`, `telegram_message_id` заполнены).
  - `telegram_updates` — 7 строк, `update_id` идут подряд без разрывов и дубликатов; идемпотентность отрабатывает.
- Render-логи на момент проверки: `/healthz` отвечает 200 каждые 5 сек (Render-пинг), стартап и `setWebhook` прошли в lifespan.
- Workspace-«Cile Simme's workspace» подтверждён юзером как его собственный второй Render-аккаунт — никаких пересозданий сервиса не требуется.

**Подмечено в backlog (отдельные PR):**
- `/settings` сейчас проваливается в catch-all text-роутер (нет хендлера) — это запланированный Phase 3, фиксируем как известную «фичу до тех пор».
- В `telegram_updates.user_id` пишется `NULL` (по дизайну Phase 1 — webhook не делает lookup `User.id` по `telegram_id`). Не блокер; в Phase 2 (где появится сложная маршрутизация по юзерам) подтянем.
- Голосовых сообщений не тестировали — это Phase 2 (Whisper).

**Верификация:**
- Юзер-визуал — переписка в чате (`/start`, имя, tz, дефолты, два свободных текста, `/settings`).
- `SELECT count(*)` по 4 таблицам Phase 1 → ожидаемые числа.
- `SELECT update_id … ORDER BY update_id DESC` — последовательные ID, идемпотентность не сломана.

**Что после этого PR:**
- Решение по фазе 2 (AI-пайплайн на Groq + русский NLP) или точечные фиксы — за юзером.

---

## 2026-05-08 — Phase 4 (out-of-order): первый Render-деплой + живой webhook

**Сделано:**
- `render.yaml` переписан под текущий Python-стек (PR #8): один web-сервис `plan-app`, `runtime: python`, `region: frankfurt`, `plan: free`, `buildCommand: uv sync --frozen`, `startCommand: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /healthz`, `autoDeployTrigger: commit`. Старая (TS-эпохи, два Node-сервиса с prisma/npm и захардкоженным MINIAPP_URL на мёртвый домен) удалена.
- Сервис создан через Render REST API (`POST /v1/services`) на user-предоставленном `RENDER_API_KEY`: `srv-d7uohcf7f7vs73crmk3g`, dashboard `https://dashboard.render.com/web/srv-d7uohcf7f7vs73crmk3g`. Workspace — «Cile Simme's workspace» (`tea-d7tr6vugvqtc73bsjka0`); это тот же физический Render-аккаунт, что у юзера, просто с другим email-логином (зафиксировано как факт, не баг).
- Public URL — `https://plan-app-t6nx.onrender.com`. ENV-переменные проставлены через REST API: `ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12` + 5 секретных (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_BASE_URL`, `DATABASE_URL`, `GROQ_API_KEYS`). В git ничего из секретов не попало.
- Telegram webhook зарегистрирован: `getWebhookInfo` отдаёт `url=https://plan-app-t6nx.onrender.com/tg/<secret>`, `pending_update_count=0`, `ip_address=216.24.57.7`. `setWebhook(drop_pending_updates=True, secret_token=...)` срабатывает в lifespan FastAPI'я при старте.
- `/healthz` отвечает HTTP 200 за ~250 мс с прода (free-tier холодный старт ~3 мин, прогретый — мгновенно).
- Карта проекта (`.agents/skills/plan-app-internal/SKILL.md`): добавлен §15 «Live deploy (Render)» с ID-сервиса, URL, ownerId, копипастными API-командами для будущих сессий. Старый §14 переименован в §16, §13 — в §14.

**Верификация:**
- `curl https://plan-app-t6nx.onrender.com/healthz` → `{"status":"ok"}` HTTP 200.
- `curl https://api.telegram.org/bot<token>/getWebhookInfo` → URL заполнен, ошибок нет.
- Render Deploy → `live` статус через ~3.5 мин (build_in_progress 1.5 мин + update_in_progress 2 мин).
- Юзер-визуал: переписка с `@daylirobot` (PLAN) — отдельным шагом / скрином в чате.

**Не сделано (намеренно):**
- AI-пайплайн (Splitter / Classifier / Critic), голос/Whisper — Phase 2.
- Cron-воркер для напоминаний — Phase 4 (вторая часть).
- FSM на Postgres-storage (сейчас MemoryStorage) — Phase 4.
- Pooled connection-string Neon (сейчас direct) — потребуется только при росте нагрузки.

**Замечание по workspace:**
RENDER_API_KEY от юзера привязан к workspace «Cile Simme's workspace» (email `city.cile.simme@gmail.com`), а не к основной почте Юсуфа (`po.muhidinovusuf54@gmail.com`). Юзер подтверждает / опровергает в чате. Если это посторонний аккаунт — пересоздадим сервис в нужном workspace отдельным шагом.

---

## 2026-05-08 — Phase 1.5: GitHub Actions CI + driver hotfix

**Сделано:**
- `.github/workflows/ci.yml` — pipeline на каждый push в `main` и на каждый PR: чекаут → `astral-sh/setup-uv` (с кэшом по `uv.lock`) → `uv sync --frozen` → `ruff format --check` → `ruff check` → `pytest -q`. Concurrency: новая попытка отменяет предыдущую на той же ветке.
- БД-драйвер: бэквард-совместимая нормализация URL в `app/db/base.py` и `alembic/env.py` — голый `postgresql://` (вид Neon copy-paste) теперь автоматически становится `postgresql+psycopg://`. Это снимает требование вручную править connection-string и даёт использовать один драйвер (psycopg v3) и для async-движка приложения, и для синхронного раннера Alembic. SQLite URL получает суффикс `+aiosqlite`.
- `tests/test_smoke.py` — `monkeypatch`-фикстура `_clean_env`, чтобы тесты дефолтных настроек не падали на дев-машинах с уже экспортированными `TELEGRAM_BOT_TOKEN`/`DATABASE_URL`/`GROQ_API_KEYS`.
- Карта проекта (`.agents/skills/plan-app-internal/SKILL.md`): добавлены §11 «Merge-workflow» и §12 «PR tooling» — фиксируют, что мердж делает AI-агент через REST API + user-PAT, а не юзер через GitHub UI.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 14 passed.
- `uv run alembic upgrade head` против настоящей Neon-БД — 5 таблиц созданы.

**Не сделано (намеренно):**
- Никаких бизнес-изменений в коде бота / API.
- Render-деплой и e2e-проверка живого бота — отдельным шагом.

---

## 2026-05-08 — Phase 1: Minimal bot (webhook + DB + onboarding)

**Сделано:**
- Конфиг (`app/shared/config.py`): добавлено свойство `webhook_url`, `get_settings()` теперь кэшируется через `lru_cache`.
- Структурное логирование (`app/shared/logging.py`): `structlog` с JSON-рендером в проде и консольным — в dev. PII-правило: логи никогда не содержат `message.text`/transcripts.
- БД-слой (`app/db/`): четыре модели Phase 1 — `User`, `UserSettings`, `InboxEntry`, `TelegramUpdate`. Async engine + sessionmaker (`init_engine` / `get_sessionmaker` / `session_scope`). `BigInteger` для Telegram-ID, JSON для `default_reminder_offsets`.
- Alembic подключён к `SQLModel.metadata` и `DATABASE_URL` (online-мode конвертирует `+asyncpg`/`+aiosqlite` в синхронный драйвер). Первая миграция `0001_init` создаёт все четыре таблицы + индексы.
- Бот (`app/bot/`):
  - `routers/start.py` — `/start`, `/help`, FSM-онбординг (имя → IANA-tz → дефолты). Записывает `User`/`UserSettings` с дефолтами: `confidence` (0.7), 08:00/21:00, `[60,15]`/`[1440,60]`, `mix`, `deadline_sunday`.
  - `routers/text.py` — catch-all для текстов: пишет в `inbox_entries`, отвечает заглушкой «AI подключим в Phase 2».
  - Роутеры — фабрики (`create_router()`), чтобы каждое `build_dispatcher()` собирало свежий граф (aiogram запрещает повторное прикрепление одного `Router` к двум диспетчерам — это иначе ломает тесты).
  - FSM-storage = `MemoryStorage` (Phase 4 переключим на Postgres-storage).
- FastAPI (`app/main.py`): lifespan c `set_webhook(drop_pending_updates=True, secret_token=...)`, `POST /tg/<secret>` с двойной валидацией (path-secret + `X-Telegram-Bot-Api-Secret-Token`), идемпотентность по `update_id` через таблицу `telegram_updates`. `/healthz` сохранился.
- Тесты:
  - `tests/test_services.py` — unit-тесты сервисов (`get_or_create_user`, `complete_onboarding`, `is_valid_timezone`, идемпотентность, inbox).
  - `tests/test_webhook.py` — секьюрити (плохой path / плохой header) + идемпотентность POST-а; aiogram-сессия замокана через `BaseSession.make_request`.
  - `tests/conftest.py` — общие фикстуры (in-memory SQLite, `Settings`, TestClient).
- Dev-зависимости: добавлены `aiosqlite` (тестовая БД) и `respx` (на будущее, для Phase 2 Groq-моков).
- Ruff: глобально игнорим `RUF001/002/003` (постоянные false positives на кириллических глифах).

**Не сделано (намеренно):**
- AI-пайплайн (Splitter / Classifier / Critic), `GroqKeyRouter`, голос/Whisper — это Phase 2.
- Inline-кнопки, `/today`, `/week`, `/settings` — Phase 3.
- Cron-воркер для напоминаний — Phase 4.
- Деплой на Render и подключение Neon — отдельным шагом после ручной проверки бота локально.

---

## 2026-05-07 — Phase 0: Cleanup + Python skeleton

**Сделано:**
- Удалены остатки прошлой реализации: `Vault/`, `Projects/`, `.hermes-backup/`, `AGENTS.md`, `PROJECTS.md`, весь TypeScript (`src/`, `prisma/`, `public/`, `package.json`, `tsconfig.json`, старый `README.md`).
- TS-история сохранена в git до коммита `6cc851d` на `main`.
- Создан новый `README.md`.
- Создана `docs/` с PLAN / ARCHITECTURE / ROADMAP / PROGRESS / IDEAS.
- Создана `.agents/skills/` (placeholder с описанием для будущего наполнения).
- Создан Python-скелет: `pyproject.toml` (uv-совместимый), `.python-version`, `ruff.toml`, `Dockerfile`, `.dockerignore`, `.env.example`.
- Структура папок: `app/{bot,api,ai,db,workers,shared}/`, `tests/`, `alembic/versions/`, `memory/`.
- Smoke-тест в `tests/test_smoke.py`.
- `render.yaml` обновлён под Python, без авто-деплоя.
- Обновлён `.gitignore`.

**Не сделано (намеренно):**
- Никакой бизнес-логики, никаких хендлеров, никаких LLM-вызовов — это Phase 1+.

**Закрытые вопросы по дороге (юзер ответил):**
- «На этой неделе» = комбо A+B (дедлайн воскресенье 23:59 + переключатель в `/settings`).
- «Через 5 минут пойти бегать» = AI решает по контексту (вариант C).
- Дефолтное смещение напоминания: внутри дня — за 1ч + 15мин; через N дней — за 1д + 1ч.
- Critic = тумблер в `/settings` с дефолтом `confidence` (порог 0.7).
- Утренний дайджест — 08:00, вечерний — 21:00 (настраиваемо).
- Курьер = микс шаблонов и LLM (≥30 шаблонов, ≥5 на стиль; рандом 50/50 per-reply).
- Critic-модель = `qwen-qwq-32b` (reasoning), резервы — Llama 4 Scout/Maverick.

---
