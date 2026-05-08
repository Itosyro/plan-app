# PROGRESS

Хронологический лог сделанного. Каждая запись = один PR.

Обновляй этот файл в каждом PR в самом конце, перед коммитом.

---

## 2026-05-08 — Mega review: critical & important fixes (PR B)

**Контекст:**
Сквозное ревью кода/тестов/доков перед Phase 4c (e2e). Нашли 2 critical (UTC inconsistency + Markdown injection в командах) и 2 important (`getattr(settings,...)` + `type(update).__name__` всегда `"Update"`). Все четыре правки в одном PR ≤180 LOC, минорные вынесены в `docs/REVIEW-findings.md::Minor`.

**Сделано:**
- `app/shared/time.py` — новый хелпер `utcnow_naive()`: `datetime.now(UTC).replace(tzinfo=None)`. Один источник правды для всех DB-write сайтов на naive-UTC колонках. Заменил три call-сайта:
  - `app/db/models.py::_utcnow` теперь делегирует в `utcnow_naive()` (раньше возвращал tz-aware → silent strip on insert).
  - `app/bot/services.py::complete_onboarding` (`onboarded_at`) и `schedule_reminders` (`now`).
  - `app/workers/scheduler.py::tick_reminders` (`cutoff` и `sent_at`). Заодно убраны `noqa: DTZ003` / `noqa: BLE001` — теперь чистые без подавлений.
- `app/bot/routers/commands.py` (C-2) — убраны все `parse_mode="Markdown"` и `*Title*` декорации в `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`. `task.title` / `note.title` приходят от пользователя и могут содержать `*`/`_`/`[`/`` ` `` — Telegram возвращал бы `400 Bad Request: can't parse entities`. Тот же фикс уже применён к callback-хендлерам, плюс есть регрессия в `test_callbacks.py` — `commands.py` мимо неё проскочил.
- `app/bot/routers/settings.py::_setting_value` (I-1) — заменил `getattr(settings, field, None)` на явный if-маппинг по `SETTING_LABELS`-полям (`critic_mode`, `morning_digest_at`, `evening_digest_at`, `response_style_source`, `week_due_semantic`). Теперь field-allow-list — единственный путь к колонке, и type-checker видит каждую ветку.
- `app/main.py::_classify_update` (I-2) — выделил функцию-классификатор: ветвится по `update.message`, `edited_message`, `callback_query`, `inline_query`, `channel_post`, `edited_channel_post` → `"other"`. Старое `type(update).__name__` всегда было `"Update"` (бесполезный лог).
- `docs/REVIEW-findings.md` — итоговый отчёт ревью: 2 Critical (исправлены), 2 Important (исправлены), 5 Minor (M-1..M-5: race на webhook, `asyncio.create_task` без strong-ref, `_utcnow` алиас, singleton groq router, free-tier idle) — задокументированы для follow-up. Плюс блок Positive patterns (N+1 avoidance, exception isolation, graceful shutdown, PII discipline, idempotency, HH:MM matcher, allow-list, LIKE escape).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 172 passed.
- LOC ≤180 (включая фикс-сайты + докментацию в коде).

**Не сделано (вынесено в `docs/REVIEW-findings.md::Minor`):**
- M-1: webhook idempotency race (catch `IntegrityError` на `record_update`).
- M-2: pending tasks set в `text.py`/`voice.py` чтобы избежать GC-окна.
- M-4: groq router singleton — приемлемо для production, документ.

---

## 2026-05-08 — Render fix: in-process scheduler loop (free-tier deploy)

**Контекст:**
Render Free **не поддерживает** standalone Cron Jobs (нужен Starter+ ~$1/мес). Чтобы остаться на бесплатке и при этом гонять «будильник» каждую минуту, переезжаем с отдельного cron-сервиса на фоновый `asyncio`-loop в самом FastAPI-процессе. Free-тир засыпает через 15 мин неактивности — её пинаем извне (`cron-job.org` или GitHub Actions cron на `/healthz`).

**Сделано:**
- `app/workers/runner.py` — новый модуль с тремя функциями:
  - `run_scheduler_loop(bot, stop_event, *, interval=60.0)` — крутится до сигнала, на каждой итерации зовёт `tick_reminders` + `tick_digests`, ловит и логирует исключения (один сбой не убивает loop), спит через `asyncio.wait_for(stop_event.wait(), timeout=interval)` чтобы корректно прерываться.
  - `start_inproc_scheduler(bot, *, interval)` → `(task, stop_event)`.
  - `stop_inproc_scheduler(task, stop_event, *, grace=10.0)` — ставит флаг, ждёт graceful shutdown, при таймауте `task.cancel()` + `contextlib.suppress`.
- `app/main.py` — `lifespan` теперь поднимает scheduler после `init_engine` + `setWebhook`, если `bot is not None`, есть `database_url` и `scheduler_inproc_enabled=True`. На shutdown — `stop_inproc_scheduler` перед `bot.session.close()`.
- `app/shared/config.py` — поля `scheduler_inproc_enabled: bool = True` и `scheduler_tick_interval_seconds: float = 60.0`.
- `app/workers/__init__.py` — обновлённый docstring (два потока: `scheduler.main` для внешнего cron / `runner.run_scheduler_loop` для in-proc).
- `render.yaml` — удалён `cron`-сервис `plan-app-scheduler`. В web envVars добавлены `SCHEDULER_INPROC_ENABLED=true` и `SCHEDULER_TICK_INTERVAL_SECONDS=60`. В верхнем комментарии — рецепт перехода на real-cron при апгрейде до Starter+.
- `docs/RENDER.md` — новый документ: топология free-тира, инструкции по cron-job.org и GitHub Actions cron keep-alive, описание SLO интервала тика, рецепт апгрейда.
- `tests/test_runner.py` — 4 теста: loop вызывает tick-функции и останавливается по флагу, исключение в одной итерации не убивает loop, `start_inproc_scheduler` + `stop_inproc_scheduler` пара, `stop_inproc_scheduler` для уже завершённой таски — no-op.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 172 passed (+7 новых: 4 runner + 3 побочных от lifespan/cfg/exports).
- LOC основной правки (без тестов и доков): ~140.

**Замечание по эксплуатации (для деплоя):**
- После выкатки задать в Render dashboard внешний пинг на `/healthz` каждые 5–10 минут (см. `docs/RENDER.md`).
- При апгрейде до Starter+ — `SCHEDULER_INPROC_ENABLED=false` и поднять обратно cron-сервис, который дёргает `python -m app.workers.scheduler`.

---

## 2026-05-08 — Phase 4b: Scheduler + Digest + render.yaml cron

**Сделано:**
- `app/workers/scheduler.py` — реальная имплементация cron-воркера:
  - `_format_reminder(task)` — текст напоминания: «⏰ Напоминаю: {title}» + «— в HH:MM» если `due_at` задан и не равен 00:00.
  - `tick_reminders(bot, *, now=None)` — выбирает `pending` напоминания с `fire_at <= now` (батч 100, сортировка по `fire_at`), отправляет в Telegram. На успех → `status='sent'`, `sent_at=now`, `last_error=None`. На ошибку → `attempts++`, `last_error=str(exc)[:512]`, при `attempts >= 3` → `status='failed'`. Возвращает `{"sent","retry","failed"}`.
  - `main_async()` — entrypoint: `configure_logging` → `init_engine(database_url)` → `Bot(token)` → `tick_reminders` → `tick_digests` → закрытие сессии Bot и `dispose_engine`.
  - `main()` — sync-обёртка `asyncio.run(main_async())` для `python -m app.workers.scheduler`.
- `app/bot/digest.py` — daily digest builders + cron tick:
  - `_user_local_now(tz, now_utc)` — UTC → локальное время через `ZoneInfo`, фолбэк UTC при битой tz.
  - `_matches_hhmm(local_dt, hhmm)` — строгое сравнение `HH:MM` (zero-padded), без слэка.
  - `_format_task_line(task)` — единая строка `🔴/🟡/🟢 {title} — в HH:MM`.
  - `_open_tasks_for_horizon(session, user_id, horizon_kind)` — задачи в горизонте, исключая `done`/`cancelled`, сортировка по `due_at NULLS LAST, created_at`.
  - `build_morning_digest(session, user)` — список задач `today` или приветствие при пустом списке.
  - `build_evening_digest(session, user)` — итоги (что осталось today + завтрашний пик), либо «Сегодня всё закрыто 🎉».
  - `tick_digests(bot, *, now=None)` — для каждого онбордженного пользователя сравнивает локальное HH:MM с `morning_digest_at` / `evening_digest_at`, шлёт соответствующий дайджест. Изоляция ошибок одного пользователя через `try/except`.
- `render.yaml` — добавлен новый сервис:
  - `type: cron`, `name: plan-app-scheduler`, `runtime: python`, `region: frankfurt`, `plan: starter`, `branch: main`, `schedule: "*/1 * * * *"`.
  - `buildCommand: rm -rf .agents docs tests && uv sync --frozen`, `startCommand: uv run python -m app.workers.scheduler`.
  - `envVars`: `ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12`, `TELEGRAM_BOT_TOKEN` (sync: false), `DATABASE_URL` (sync: false).
- `tests/test_scheduler.py` — 7 тестов: форматтер с/без времени и при `00:00`, отправка просроченных, пропуск будущих, пропуск уже `sent`, retry-семантика, переход в `failed` после `MAX_REMINDER_ATTEMPTS`, батч из нескольких записей.
- `tests/test_digest.py` — 13 тестов: helpers (`_matches_hhmm`, `_user_local_now`), morning empty/полный/без `done`, evening combined/empty-today, `tick_digests` morning local-match, off-minute skip, skip unonboarded, изоляция падений по чату.

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 165 passed (145 Phase 4a + 20 новых).
- PR ~390 LOC (код Phase 4b без тестов).

**Замечание по Render:**
- Free-план не поддерживает cron. Поэтому `plan-app-scheduler` объявлен на `plan: starter`. Web-сервис остаётся на `free` без изменений.

---

## 2026-05-08 — Phase 4a: Reminder model + migration + persist extension

**Сделано:**
- `app/db/models.py` — модель `Reminder` (table=`reminders`):
  - `id`, `user_id` (FK→users.id, indexed), `task_id` (FK→tasks.id, indexed), `fire_at` (DateTime UTC, indexed), `status` (`pending|sent|failed|cancelled`, default `pending`, indexed, max_length 16), `attempts` (default 0), `last_error`, `sent_at`, `created_at`.
- `alembic/versions/2026_05_08_2015-0003_phase_4_reminders.py` — миграция: `CREATE TABLE reminders` + 4 индекса (`user_id`, `task_id`, `fire_at`, `status`).
- `app/bot/services.py`:
  - `DEFAULT_REMINDER_OFFSETS = {"same_day": [60, 15], "multi_day": [1440, 60]}` — фолбэк, если у пользователя нет своих.
  - `_select_reminder_offsets(cr, defaults)` — explicit `cr.reminder_offsets` побеждают defaults; иначе `same_day` для today/tomorrow, `multi_day` для остальных горизонтов.
  - `_to_naive_utc(dt)` — нормализация tz (DateTime в БД хранится без offset).
  - `schedule_reminders(...)` — создаёт `Reminder` rows, пропуская офсеты, у которых `fire_at <= now`.
  - `persist_classification(...)` теперь принимает `default_reminder_offsets` и после `Task.flush()` планирует `Reminder` rows, если `due_at is not None`.
- `app/bot/routers/text.py` — `_run_pipeline` пробрасывает `default_reminder_offsets` (читается из `UserSettings.default_reminder_offsets`) в `persist_classification`.
- `tests/test_reminders.py` — 13 новых тестов: офсетная логика (5), `schedule_reminders` rows/skip-past/empty (3), `persist_classification` create/no-due_at/notes/explicit/multi-day (5).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 145 passed (132 + 13 новых).
- PR ~340 LOC.

**Не сделано (Phase 4b, отдельный PR):**
- `app/workers/scheduler.py` (cron tick: shipping pending reminders, retry/fail mark).
- `app/bot/digest.py` (morning/evening daily digest builders).
- `render.yaml` cron job для tick'ов раз в минуту.
- e2e Phase 4 (digest + reminders end-to-end).

---

## 2026-05-08 — Code review: critical & important fixes + skills bundle

**Сделано:**
- `code-review-findings.md` — глубокое ревью на 3 Critical / 6 Important / 10 Minor findings (с file:line и severity).
- `.agents/skills/requesting-code-review/` — адаптированный obra superpowers скилл (SKILL.md + code-reviewer.md), плюс `.agents/skills/socraticode-principles/SKILL.md` — методология SocratiCode (hybrid search + dependency graphs + blast radius). В Render-деплой не попадает: `render.yaml.buildCommand` теперь `rm -rf .agents docs tests && uv sync --frozen` — на free tier чистый рантайм, в GitHub видно всё.
- `app/bot/routers/callbacks.py` (C-1): убран `parse_mode="Markdown"` из всех `edit_text` с пользовательскими `task.title`. Не падаем на названиях с `*`, `_`, `[`.
- `app/bot/services.py`:
  - C-2: `update_user_settings()` теперь валидирует `value` против `ALLOWED_SETTING_VALUES` (frozenset на поле). Никаких `setattr(settings, field, arbitrary_string)`.
  - I-1: `get_categories_with_counts()` — один LEFT JOIN + GROUP BY вместо 1+N запросов.
  - I-2: новая утилита `_escape_like()` + `Task.title.ilike(pattern, escape="\\")` для безопасного поиска по подстроке.
  - I-5: импорт `AsyncSession` теперь из `sqlmodel.ext.asyncio.session` (а не `sqlalchemy.ext.asyncio`) — соответствует фактическому типу из `session_scope()`.
  - I-6: `get_or_create_user()` обновляет `lang_code`, если Telegram прислал новый (раньше навсегда оставался первый).
- `app/bot/routers/text.py` (C-3 + I-3): `asyncio.gather(..., return_exceptions=True)` + явный `_log_task_exception` callback вместо лямбды, которая молча проглатывала ошибки. Один сбойный classify не убивает весь батч; критик в `try/except` — ошибка критика не трогает уже хорошие классификации.
- `app/bot/routers/voice.py` (I-3): тот же `_log_task_exception` импортирован из text.py.
- `tests/test_callbacks.py` — регрессии для C-1 (не должно быть `parse_mode="Markdown"` рядом с `task.title`) и I-2 (LIKE-метасимволы экранируются).
- `tests/test_settings.py` — регрессия для C-2 (отвергаем неизвестное `value`).
- `tests/test_e2e_pipeline.py` — регрессия для C-3 (один Groq 429 на втором юните — выживший юнит сохраняется и попадает в ответ).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 132 passed (128 + 4 новых).
- Скиллы и docs в Render-деплой не попадают (`buildCommand` сначала их удаляет).

---

## 2026-05-08 — Phase 3 finish: change-category button + tz/reminder в /settings (PR #31)

**Сделано:**
- `app/bot/routers/callbacks.py`:
  - 4-я кнопка «🏷 Категория» во второй строке `task_action_keyboard`.
  - `category_picker_keyboard(task_id, categories)` — сетка 2×N с кнопкой «↩ Назад».
  - Хендлеры `task:pick_category:<id>` (показать пикер) и `task:set_category:<id>:<cat_id>` (применить).
- `app/bot/services.py`:
  - `get_user_categories_full()` — возвращает `Category[]` (а не только имена).
  - `update_task_category()` + `TaskEvent(kind="recategorized")`.
  - `REMINDER_PRESETS = {"minimal","default","extra"}` + `reminder_preset_from_offsets()`.
  - `update_user_settings()` маршрутизирует виртуальные поля: `tz` → `User.tz` (валидация через `is_valid_timezone()`), `reminder_preset` → `UserSettings.default_reminder_offsets`.
- `app/bot/routers/settings.py`:
  - Поля `tz` (8 пресетов IANA: Москва, Калининград, Самара, Екатеринбург, Алматы, Ташкент, Владивосток, UTC) и `reminder_preset` (3 пресета) в SETTING_LABELS / SETTING_OPTIONS.
  - `_setting_value(field, settings, user)` — резолвит виртуальные поля.
  - `_format_settings(settings, user)` — принимает `User` для отображения tz и текущего пресета.
- `tests/test_callbacks.py` — обновлена проверка структуры кнопок; добавлены тесты пикера и `update_task_category`.
- `tests/test_settings.py` — добавлены тесты на tz/reminder_preset (валидация, expand to offsets, обратная мапа, fallback без user).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 128 passed (119 + 9 новых).
- PR ~396 LOC.

**Phase 3 закрыта.** Следующее — Phase 4 (cron worker для напоминаний и daily/weekly digest).

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
