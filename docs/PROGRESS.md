# PROGRESS

Хронологический лог сделанного. Каждая запись = один PR.

Обновляй этот файл в каждом PR в самом конце, перед коммитом.

---

## 2026-05-08 — Phase 3c: /settings command with inline buttons (PR #29)

**Сделано:**
- `app/bot/routers/settings.py` — полный `/settings` роутер:
  - `cmd_settings` — показывает текущие настройки с кнопками редактирования.
  - `cb_settings_edit` — показывает варианты для конкретной настройки.
  - `cb_settings_set` — применяет выбранное значение.
  - `cb_settings_back` — возврат к обзору настроек.
  - 5 редактируемых настроек: critic_mode, morning_digest_at, evening_digest_at, response_style_source, week_due_semantic.
- `app/bot/services.py` — `update_user_settings()`: валидация поля + обновление.
- `app/bot/__init__.py` — регистрация settings_router.
- `app/bot/courier_templates.py` — `/settings` добавлен в HELP.
- `tests/test_settings.py` — 11 тестов (клавиатуры, форматтер, сервис).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 119 passed (108 + 11 новых).
- PR ~410 LOC.

---

## 2026-05-08 — Phase 3b: Inline buttons on task cards (PR #28)

**Сделано:**
- `app/bot/routers/callbacks.py` — callback-роутер для inline-кнопок:
  - `task:done:<id>` — отметить задачу выполненной (зачёркнутый текст).
  - `task:delete:<id>` — удалить задачу.
  - `task:pick_move:<id>` — показать клавиатуру выбора горизонта.
  - `task:move:<id>:<horizon>` — перенести задачу на выбранный горизонт.
  - `task:cancel:<id>` — отменить перенос, вернуть кнопки действий.
- `task_action_keyboard(task_id)` — 3 кнопки: ✅ Готово, 🔄 Перенести, 🗑 Удалить.
- `horizon_picker_keyboard(task_id)` — 6 горизонтов + кнопка «Назад».
- `app/bot/routers/commands.py` — view-команды теперь отправляют inline-кнопки под каждой задачей.
- `app/bot/__init__.py` — регистрация callbacks_router.
- `tests/test_callbacks.py` — 6 тестов (структура клавиатур, service-level операции).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 108 passed (102 + 6 новых).
- PR ~380 LOC.

---

## 2026-05-08 — Phase 3a: View commands (/today, /week, /notes, /categories) (PR #27)

**Сделано:**
- `app/bot/routers/commands.py` — 8 команд просмотра:
  - `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday` — задачи по горизонту.
  - `/notes` — последние 20 заметок.
  - `/categories` — категории с количеством активных задач.
- `app/bot/services.py` — 7 новых функций:
  - `get_tasks_by_horizon()`, `get_all_notes()`, `get_categories_with_counts()`.
  - `mark_task_done()`, `delete_task()`, `get_task_by_id()`.
- `_format_task_list()`, `_format_note_list()` — форматтеры с иконками приоритетов.
- `app/bot/__init__.py` — регистрация commands_router.
- `app/bot/courier_templates.py` — HELP обновлён со списком новых команд.
- `tests/test_commands.py` — 11 тестов (сервисы + форматтеры).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 102 passed (91 + 11 новых).
- PR ~550 LOC.

---

## 2026-05-08 — e2e Pipeline Tests (PR #25)

**Сделано:**
- `tests/test_e2e_pipeline.py` — 8 end-to-end тестов, проверяющих полный pipeline (reorder detect → split → time → classify → persist → courier reply) с мокнутыми LLM-вызовами и in-memory БД.
- Тест-кейсы:
  1. Одна задача: «утром пробежка» → 1 task Здоровье/today.
  2. Две задачи: «купить хлеб и молоко, записаться к врачу» → 2 tasks.
  3. Задача + заметка: «позвонить Олегу, книга про AI» → 1 task + 1 note.
  4. Рабочие дедлайны: «до пятницы отчёт, в 11 совещание» → 2 tasks Работа.
  5. Филлер: «ну так, окей» → 0 задач.
  6. Три элемента: «йога, ужин, идея про стартап» → 2 tasks + 1 note.
  7. Одна заметка: «мысль про архитектуру» → 1 note.
  8. Срочная задача: «срочно! позвонить в банк» → 1 high-priority task.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 91 passed (83 + 8 новых).
- PR ~500 LOC (только тесты).

---

## 2026-05-08 — Phase 2.3d: Reorder — detect and execute task rescheduling (PR #23)

**Сделано:**
- `app/ai/reorder.py` — `detect_reorder()`: определяет, является ли сообщение запросом на перенос задачи. LLM (`llama-3.1-8b-instant`) через `instructor` (JSON mode, temperature 0.0). Короткие сообщения (<3 символов) пропускаются без LLM.
- `app/ai/prompts/reorder.md` — системный промпт для детекции переноса: примеры фраз, формат вывода (`is_reorder`, `task_query`, `target_horizon`, `target_raw`).
- `app/ai/schemas.py` — `ReorderRequest` (is_reorder, task_query, target_horizon, target_raw).
- `app/bot/services.py` — `find_task_by_query()` (ILIKE-поиск по title, исключает done), `update_task_horizon()` (смена горизонта + TaskEvent kind=reordered).
- `app/bot/routers/text.py` — `_try_reorder()`: перед обычным pipeline проверяет reorder-интент. Если найден — ищет задачу и обновляет горизонт, отвечает «✅ Перенёс «X» → Y.». Если задача не найдена — сообщает об этом.
- `app/bot/routers/voice.py` — наследует reorder из `_run_pipeline()` text.py.
- `tests/test_reorder.py` — 9 тестов: schema (2), detect_reorder LLM mock (2), short text (1), find_task DB (3), update_task_horizon DB (1).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 83 passed (74 старых + 9 новых).
- PR ~470 LOC.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- e2e тесты — отдельный PR.
- due_at обновление при переносе — пока только horizon, без пересчёта даты.

---

## 2026-05-08 — Phase 2.3c: Courier — confirmation + summary replies (PR #21)

**Сделано:**
- `app/ai/courier.py` — модуль Courier:
  - `TEMPLATES` — 6 стилей × 6 фраз = 36 шаблонов подтверждений (neutral, formal_master, friendly, playful, terse, respectful).
  - `generate_courier_reply()` — выбирает шаблон или генерирует через LLM (`llama-3.1-8b-instant`) в зависимости от `mode` (mix/template_only/llm_only).
  - `build_summary()` — детерминированное резюме из `ClassifierResult[]` (📌 задача / 📝 заметка: title [category]).
  - `courier_respond()` — полный ответ: подтверждение + резюме.
  - `_pluralize()` — русское склонение «элемент/элемента/элементов».
- `app/ai/prompts/courier.md` — системный промпт для LLM-генерации подтверждений: описание 6 стилей, правила (русский, без markdown, без перечисления задач).
- `app/bot/routers/text.py` — заменён inline-reply на `courier_respond()`. Из UserSettings читается `response_style_source` → `courier_mode`. Удалена неиспользуемая `_pluralize_elements()`.
- `app/bot/routers/voice.py` — аналогичная интеграция: `courier_mode` и `courier_style` пробрасываются в `_run_pipeline()`.
- `tests/test_courier.py` — 11 тестов: шаблоны (2), build_summary (3), generate_courier_reply template_only (2), LLM mock (1), courier_respond full (3).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 74 passed (63 старых + 11 новых).
- PR ~400 LOC (418 строк).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Voice task reordering — Phase 2.3d.
- e2e тесты — после Phase 2.3d.

---

## 2026-05-08 — Phase 2.3b: Critic — conditional review of classifier output (PR #19)

**Сделано:**
- `app/ai/critic.py` — `critique_classification()` через `qwen-qwq-32b` (instructor, temperature=0.0), `should_run_critic()` (два режима: `confidence` / `always`), `apply_verdict()` (подмена результата при `approved=False`).
- `app/ai/prompts/critic.md` — системный промпт для критика: проверяет is_task, category_name, horizon, priority, title, reminder_offsets.
- `app/ai/schemas.py` — `CriticVerdict` (approved, reason, corrected ClassifierResult | None).
- `app/bot/services.py` — `get_user_settings()` для чтения critic_mode / confidence_threshold из `UserSettings`.
- `app/bot/routers/text.py` — интеграция критика в `_run_pipeline()`: после classify, до persist. Параметры `critic_mode` и `confidence_threshold` пробрасываются из UserSettings.
- `app/bot/routers/voice.py` — аналогичная передача critic-настроек из UserSettings в pipeline.
- `tests/test_critic.py` — 9 тестов: should_run_critic (4 кейса), apply_verdict (3 кейса), critique_classification с мокнутым Groq (2 кейса).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 63 passed.
- PR ~400 LOC (344 строк кода + 63 строк промпта).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Courier — Phase 2.3c.
- Voice reordering — Phase 2.3d.

---

## 2026-05-08 — Phase 2.3a: Whisper — голосовые сообщения (PR #18)

**Сделано:**
- `app/ai/whisper.py` — `transcribe_voice()`: whisper-large-v3 через Groq, language=ru, temperature=0.0, response_format=verbose_json. Логирование latency и key_id через structlog.
- `app/bot/routers/voice.py` — хендлер голосовых: проверка онбординга → скачивание файла → транскрипция → сохранение в inbox (kind=voice) → запуск text-pipeline в фоне (`asyncio.create_task`). Лимит 20 МБ.
- `app/bot/services.py` — `store_inbox_voice()` (kind="voice", transcript в raw_text).
- `app/bot/__init__.py` — регистрация voice-роутера.
- `tests/test_whisper.py` — 5 тестов с мокнутым Groq через respx.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 54 passed.
- PR 279 LOC.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Critic — Phase 2.3b.
- Courier — Phase 2.3c.

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
