# ROADMAP — фазы

Каждая фаза = отдельный PR. Маленькие PR, ревьюить и откатывать удобнее.

> **Status (на 2026-07-26, аудит-круг 1):** проект в режиме
> **goal-loop** — повторяющиеся круги аудита свежим взглядом каждые
> ~5 часов (скилл `.claude/skills/audit-loop`). Круг 1: 57
> подтверждённых багов, все критические исправлены, модели мигрированы
> на `openai/gpt-oss-20b/120b` (llama отключают в августе 2026),
> 630 тестов. Детали: `docs/audit/2026-07-26-audit.md` и верх
> `docs/PROGRESS.md`. Будущее мобильное приложение: PWA → Capacitor →
> offline (план в `docs/plans/2026-07-26-audit-improvements.md`).
>
> **Status (на 2026-05-28, после PR #106..#155):**
> Phase 0..7d + Voice/Text Edit (PR-I серия) + Reminder Management
> (PR-J серия) — **done и в проде**. Needs-Clarification UI (PR-K)
> **заменён** на «Входящие» (вариант Б, см. ниже) и его мёртвый код
> удалён (#149).
>
> **Свежая волна (#145–#155, 2026-05-27..28) — «Входящие» + голосовое
> редактирование + перф:**
> - **«Входящие» (вариант Б) — ✅ полностью закрыт.** Вместо in-chat
>   «создать? да/нет» задачи создаются сразу; если из сообщения вышло
>   ≥2 задач или что-то с низкой уверенностью, запись помечается
>   `needs_review` и попадает в пятую вкладку Mini-App «Входящие».
>   В карточке ревью: чекбоксы keep/drop + «Подтвердить» (#145/#146),
>   инлайн-правка названия (#150), правка категории/приоритета (#152),
>   ИИ-разбивка `[Разбить]` на 2–5 подзадач (#155, эндпоинт
>   `POST /api/tasks/{id}/split`). Выключатель `review_enabled` в
>   /settings (#153, миграция 0016). Эндпоинты `GET /api/inbox/pending`,
>   `POST /api/inbox/{id}/confirm`, миграция 0015.
> - **Категории голосом (#147)** — интенты `create_category` /
>   `rename_category` / `delete_category` («создай категорию X»,
>   «переименуй категорию X в Y», «удали категорию X»). Удаление
>   категории отвязывает её задачи/заметки (→ без категории).
> - **Заметки голосом (#148)** — интенты `rename_note` / `delete_note`
>   / `set_note_category`, различитель — слово «заметк-».
> - **Производительность пайплайна (#154)** — убран избыточный
>   `_try_reorder`, распараллелены per-unit `detect_intent` и цикл
>   критика, шорткат для одиночного сообщения. Одиночная задача:
>   5(+критик) → 3(+критик) sequential round-trip'ов; 3-юнит: ~8 → ~4.
>
> **Phase 7e — Polish — ✅ ЗАВЕРШЕНА** (см. `docs/plans/2026-05-25-phase7e-polish.md`):
> канбан=категории + рабочий DnD (#124), календарь Месяц/Неделя/Агенда (#132),
> экран «Выполненные» + `completed_at` (#126/#127), сегмент-контрол + bottom-sheet
> (#123), Настройки Mira-стиль (#125), aurora-фон + навбар Mira + `webapp/DESIGN.md`
> (#128/#129), поповер «Раскладка» вид/сорт/фильтр (#131/#137), security hardening
> по аудиту Jules — prompt-injection (#133), supply-chain pin (#134/#139),
> security-headers (#135), confirm-delete (#138), `SECURITY.md`. Не закрыт только
> **G5** (scheduler/keepalive вне web-процесса) — намеренно отложен, ждёт решения
> по хостингу.
>

> **Свежая волна (#106–#110, 2026-05-24):**
> - **#106 security hotfix** — INIT_DATA TTL 24h → 10min, JSON-escape
>   пользовательского ввода в classifier-промпте, `max_length` на
>   `ClassifierResult.title/category_name/first_step`.
> - **#107 FirstStep rewrite** — когда `concretize_tasks=True` и
>   classifier предложил `first_step`, при persist меняем местами:
>   `Task.title` = actionable рерайт, `Task.title_original` = оригинал.
>   Mini-App показывает 🎯 + оригинал курсивом. Миграция 0012.
> - **#108 Subtasks** — `Task.parent_id` self-FK (cascade), classifier
>   эмитит `subtasks: list[str]` (cap 5), дети наследуют категорию /
>   горизонт / приоритет. `GET /tasks/{id}` отдаёт `TaskDetailOut` с
>   гидрированными детьми, `GET /tasks` скрывает детей по умолчанию
>   (`include_subtasks=true` чтобы включить плоский режим). В UI —
>   чип «N/M» на карточке + чек-лист в детали. Миграция 0013.
> - **#109 BottomNav под Telegram** — `rounded-[28px]`, blur-2xl,
>   sliding capsule active-вкладки с iOS-spring easing, scale-110 на
>   active icon. Без новых зависимостей.
> - **#110 promt tuning** — classifier и critic теперь агрессивно
>   эмитят `first_step` / `subtasks` для composite-глаголов («создать»,
>   «организовать», «подготовить», «разобраться»). Новые примеры под
>   реальные пользовательские кейсы.
>
> Работает: голосовое/текстовое сообщение → задачи + заметки +
> напоминания (с автоматическим разбиением на подзадачи и подсказкой
> первого шага), утренний/вечерний дайджест (с pinned live-update),
> команды `/today /week /reminders ...`, callback-кнопки, /settings,
> **Mini-App** на `/app/` (lucide-icons + Telegram-style bottom nav +
> drag-n-drop + per-horizon counts + CloudStorage prefs + Settings
> page с PATCH /api/me + Trash / soft-delete + Notes tab + subtask
> checklist), **построчная** (streaming) выдача ответов бота, **emoji
> reactions**, **quote replies**, **онбординг через inline-клавиатуру**
> (12 CIS часовых поясов).
>
> **Voice/Text Edit Pipeline (PR-I серия):** голосом или текстом
> можно сказать «отмени звонок», «перенеси отчёт на пятницу»,
> «переименуй задачу X в Y», «приоритет высокий» — `edit_executor`
> через intent-detection дёргает соответствующий сервис. PR-I3 даёт
> анафоры (`LAST_TASK`) + multi-intent + disambiguation для multi-
> match. PR-I4 — undo через `TaskEditSnapshot` (inline `[Отменить]`,
> TTL 5 мин).
>
> **~~Needs-Clarification UI (PR-K)~~ → «Входящие» (вариант Б):**
> старый flow (при `confidence < 0.7` показывать inline
> `[Да, создать] / [Нет, отмена]`) **снят**. Теперь задачи создаются
> сразу, а проверка/чистка вынесена во вкладку Mini-App «Входящие»
> (#145/#146/#150). Мёртвый код PR-K удалён (#149), неиспользуемая
> колонка `Task.needs_clarification` дропнута миграцией 0017.
>
> **Reminder Management (PR-J):** `/reminders` + `/reminders all`
> + кнопка `[➡️ Ещё]` пагинация + голосовой `cancel_reminder` с
> локальными временами и склонением.
>
> **533 теста**, ruff/mypy clean, https://plan-app-t6nx.onrender.com .
>
> Все critical (C-1..C-6) и important (I-1..I-8) findings из
> `docs/REVIEW-2026-05-09-v2.md` — закрыты.
>
> **Прод-операция:**
> - Alembic migrations 0001..0017 накатаны (последние — 0015
>   `inbox_needs_review`, 0016 `review_enabled`, 0017
>   `drop_task_needs_clarification`).
> - Render `startCommand` авто-применяет `alembic upgrade head` на
>   каждом деплое.
> - Render env: `GROQ_API_KEYS` поддерживает comma-separated список
>   из 1+ ключей. Для ротации на 3 ключа нужно вручную обновить
>   на Render (юзер должен сделать).
>
> **Что осталось (см. секцию «Next Up» внизу для приоритетов):**
> - **Опциональная «свернуть/развернуть» subtask-tree в чате** — сам
>   Unicode-tree уже рендерится в `courier.py::render_subtask_tree`
>   после #108; можно добавить кнопку, чтобы пользователь сворачивал
>   длинные деревья. Низкий приоритет.
> - **Phase 7d** — ✅ в основном закрыта: детальный API с подзадачами
>   (#108), вкладка «Календарь» месячной сеткой (#116), drag-n-drop
>   задач по дням календаря (#117), канбан-доска по горизонтам (#118),
>   сохранение вида «Список/Доска» в prefs. Опционально осталось:
>   канбан по категориям. ✅ Недельный режим календаря и серверная
>   фильтрация по диапазону (`due_at_from`/`due_at_to`) — сделаны.
> - **Live-draft (Rumble-аналог)** — SSE/WebSocket стрим черновика
>   задачи по мере прохождения пайплайна. Следующая крупная веха.
> - **Rate limiting + API versioning** — из security-ревью, отложено
>   на отдельную hardening-волну.
> - ✅ ~~**Архивация старых HANDOFF**~~ — 20 файлов v1..v20 переехали в
>   `docs/archive/`; в `docs/` остался актуальный v21 + общий
>   `HANDOFF.md`.
> - **Phase 5.5** (FullCalendar) — полу-готовая ветка
>   `devin/*-phase5-5-calendar`.
> - **PR-H Critic refinement** — multi-stage critic, golden-set,
>   eval-метрика.
> - **PR-F OpenRouter fallback** — нужен OPENROUTER_API_KEY от юзера.
> - **LLM golden evals** — пересекается с PR-H, особенно важно после
>   prompt-tuning из #110.
> - **Voice Inbox card UX** — ✅ **полностью закрыт**: «Входящие» с
>   `[Подтвердить]` (#146), `[Исправить]` названия (#150), правкой
>   категории/приоритета (#152), выключателем в /settings (#153) и
>   ИИ-`[Разбить]` (#155).
> - ✅ ~~**`TaskEvent` для cancel-reminders**~~ — закрыто; и одиночный
>   `cancel_reminder`, и пакетный `cancel_task_reminders` пишут
>   `TaskEvent(kind="reminder_cancelled", payload_json={"reminder_id", "fire_at", "scope"})`.
> - ✅ ~~**Windows TZ-bug fix**~~ — закрыто; `utcnow_naive()` теперь
>   правильно навешивает UTC перед `.timestamp()` (см.
>   `app/shared/time.py`).
> - **Excel export/import** + table-classifier — отдельная фаза.
> - **Phase 8 (Graph view, Obsidian-style)** — future.
> - Phase 7 polish (наблюдаемость + эвалы) — частично (structlog ✓,
>   mypy strict ✓; DSPy / backup / Sentry / расширенный README ✗).
> - **Brand design / design tokens** — частично закрыто #109 (nav),
>   глобальные токены / тёмная тема — будущее.

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

## Phase 5 — Telegram mini-app 🟢 DONE (5.1-5.3) / 🟡 NEXT (5.4+)

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

**Что сделано (PR #64, #65 hotfix):**
- ✅ 5.1 Backend API — `/api/me`, `/api/tasks`, `/api/notes`,
  `/api/categories`, `/api/horizons`, `/api/inbox` с HMAC-валидацией
  initData (TTL 24 ч).
- ✅ 5.2 Каркас фронта — React 18 + Vite 5 + Tailwind 3 + TypeScript
  strict, mobile-first под Telegram theme (CSS vars).
- ✅ 5.3 Список с фильтрами — pill-табы горизонтов, фильтр по
  категории, карточки с done/move/delete, optimistic updates.
- ✅ Streaming-replies в боте: построчное `editMessageText` с
  rate-limit-aware retry-ами и `sendChatAction("typing")`.
- ✅ `MenuButtonWebApp` глобально через `setChatMenuButton` (Bot API
  10.0).

**Что осталось (Phase 5.4+, follow-up):**
- ✅ 5.4a Counts endpoint (`GET /api/tasks/counts`, PR #71) — один
  запрос возвращает счётчики по всем горизонтам; pill-табы Mini-App
  показывают `Сегодня (3) / Завтра (1) / Неделя (8)`.
- ✅ 5.4b Drag-n-drop reorder (PR #72) — `@dnd-kit/core@6.3`, long-
  press на карточке (250 мс) → drag → drop на pill горизонта →
  PATCH с optimistic update.
- 🟡 5.5 Календарный вид — **полу-готов**, ветка
  `devin/*-phase5-5-calendar` (FullCalendar + month/week views), не
  замерджена. Закончить **после** Phase 7c/7d (settings, task
  detail) — иначе календарь придётся ре-скинить под новый design
  language.
- ❌ 5.6 Карточка задачи — мигрировала в **Phase 7d** (см. ниже).

---

## Phase 6 — Bot API 10.0 polish 🟢 DONE

**Цель:** довести бот до состояния, использующего новинки Bot API
10.0 (8 мая 2026) для улучшения «человечности» взаимодействия.

Из 4 фич, заявленных пользователем (1, 2, 3, 6 из списка 10.0),
реализованы все четыре. Остальные (Stars / Donations / Business
Mode / Biometric auth) — **отложены явно, не приоритетные**.

**Что сделано:**
- ✅ **6.1 Reactions** (PR #66, merged) — `setMessageReaction`. 👀 при
  получении user message → 🎉 при успехе → 😢 при ошибке. Allow-list
  эмодзи + best-effort: ошибки Telegram never break the pipeline.
  Файл: `app/bot/reactions.py`, 7 unit-тестов.
- ✅ **6.2 Quote replies** (PR #67, merged) — `reply_parameters` +
  `quote` (Bot API 7.0+). Бот «прикрепляет» свой ответ к user
  message с tap-to-jump стрелкой; `safe_quote()` валидирует, что
  фрагмент действительно substring оригинала (Telegram возвращает
  `QUOTE_TEXT_INVALID` иначе). Файл: `app/bot/quote_replies.py`,
  7 unit-тестов.
- ✅ **6.3 Pinned «top today»** (PR #69, merged) — утренний дайджест
  пинится в чате, в течение дня live-обновляется через
  `editMessageText` при каждом mark-done (через inline-кнопку или
  Mini-App). Migration 0008 добавляет `pinned_morning_*` на
  `user_settings`. Файл: `app/bot/pinned_today.py`, 7 unit-тестов.
- ✅ **6.4 CloudStorage** (PR #68, merged) — Mini-App UI prefs
  (`last_horizon`, `last_category`) персистятся через
  `WebApp.CloudStorage` (Bot API 6.9+) с откатом на `localStorage`.
  Синкается между Telegram-клиентами одного юзера. Файл:
  `webapp/src/lib/storage.ts`.

**Что НЕ делаем (по решению пользователя):**
- ❌ Stars / Telegram Payments — отложено в будущее.
- ❌ Business Mode — отложено в будущее.
- ❌ Biometric auth в Mini-App — отложено в будущее.
- ❌ HapticFeedback расширенный (extra точечные вибрации) — низкий
  ROI, текущий уровень достаточный.

---

## Phase 7 — Redesign + Polish, наблюдаемость, эвалы 🟡 PARTIAL

**Цель:** редизайн UI Mini-App (под референсы пользователя) +
довести до состояния «не стыдно показать».

### Phase 7a — Bot onboarding redesign ✅ DONE (PR #73)

- Inline-клавиатура из 12 популярных CIS часовых поясов
  (Москва / Минск / Киев / Калининград / Ереван / Тбилиси /
  Алма-Ата / Ташкент / Бишкек / Екатеринбург / Новосибирск /
  Владивосток) + кнопка «Указать другой ✏️» для свободного ввода.
- Тексты `/start` переписаны коротко, без неловких placeholder'ов.
- Re-onboarding shortcut: если у юзера уже есть `display_name`,
  тап по новой кнопке часового пояса меняет `user.tz` и
  пропускает повторный запрос имени.
- Файлы: `app/bot/onboarding.py` (новый), `app/bot/routers/start.py`,
  `app/bot/courier_templates.py`. +10 unit-тестов.

### Phase 7b — Mini-App design polish ✅ DONE (PR #74)

- `lucide-react` icons — `Sun` / `Sunrise` / `CalendarDays` /
  `Sunset` для горизонтов; `Check` / `Clock` / `Flag` / `Move` /
  `Trash2` в карточке задачи; `ListTodo` / `CalendarDays` /
  `Settings` в bottom nav.
- Capsule bottom nav (`webapp/src/components/BottomNav.tsx`) —
  3 таба (Задачи / Календарь / Настройки), активный таб с
  лейблом, неактивные icon-only.
- Полированные task-card (rounded-2xl, активный фон вместо
  border, priority flag только для high/low).
- Полированные horizon pills (leading icon + active solid dark).
- Header упрощён до `План` + `display_name` справа.
- Палитра НЕ изменена — оставлена белая Telegram-theme через
  CSS-переменные.
- Bundle: 193 → 202 KB raw / 62 → 65.6 KB gzip (+~4 KB gzip).

### Phase 7c — Settings page в Mini-App ✅ DONE (PR #78)

- `webapp/src/components/SettingsPage.tsx` заменяет `ComingSoon`.
- Секции «✦ Основные», «🗒 Поведение», «⚪ Лимиты» с toggle-rows.
- `PATCH /api/me` — обновление display_name, tz, digest times,
  courier style, week_due_semantic, critic_mode.
- TZ picker — native Mini-App picker (BottomSheetSelect) с списком
  IANA-зон.

### Phase 7d — Task detail + inline edit ❌ TODO

- Тап на карточку задачи → modal/sheet с детальной информацией.
- Tabs «Задача / Информация» (как в screenshot 03 reference).
- Cards: «Проект» (категория, кликабельная), «Дата» (due_at +
  picker), «Заметки» (description, multiline).
- Кнопка «🗑 Удалить задачу» внизу.
- **Inline edit:** двойной тап на title → input → Enter сохраняет
  через `PATCH /api/tasks/:id`, Esc откатывает.
- TaskEvent-история (когда создана, когда меняли horizon, когда
  done) — список в нижней части modal.

### Phase 7-misc — Polish, наблюдаемость, эвалы 🟡 PARTIAL

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

## Phase 8 — Voice/Text Edit Pipeline ✅ DONE (PR-I серия + PR-J + PR-K)

**Цель:** дать юзеру управлять задачами голосом или текстом без
заходов в Mini-App — «отмени звонок», «перенеси отчёт на пятницу»,
«готово молоко».

**Реализовано:**

### Phase 8a (PR-I1) — complete / delete / reopen
- `app/ai/intent.py::detect_intent()` — отдельный AI-шаг до
  classifier'а, ловит edit-интенты.
- `app/bot/edit_executor.py::execute_edit()` — диспатч на сервис.
- Multi-match disambiguation через inline-клавиатуру.

### Phase 8b (PR-I2) — rename / set_due / set_priority / set_category / reorder_time
- Расширенная схема `EditIntent` с полями `new_title`, `new_due`,
  `new_priority`, `new_category`, etc.

### Phase 8c (PR-I3) — context + multi-intent
- `LAST_TASK` анафоры (TTL 60с) — «удали её» применяется к
  последней упомянутой задаче.
- Multi-intent: `split_message` → каждый unit отдельно через
  `detect_intent` → edit-интенты сразу, create-интенты в обычный
  classify-pipeline.
- `list_done` read-only intent.

### Phase 8d (PR-I4) — undo
- `TaskEditSnapshot` таблица (миграция 0011) + inline `[Отменить]`
  кнопка с TTL 5 мин. Восстанавливает `old_value` любого поля.

### Phase 8e (PR-K) — needs_clarification UI
- При `confidence < 0.7` — не персистим сразу. Inline
  `[Да, создать] / [Нет, отмена]` с TTL 5 мин (in-memory).

### Phase 8f (PR-J) — Reminder Management
- `/reminders` + `/reminders all` + пагинация.
- `cancel_reminder` голосом — с локальными временами и
  склонением (PR #104).
- Inline-cancel кнопки.

**Откатано / отложено:**
- ❌ Slash-команды `/add /done /del /move /postpone` (Phase 8b в
  PROGRESS под PR #82) — реализованы и потом удалены, потому что
  voice/text intent пайплайн делает то же самое более естественно.
  Парсер `parse_horizon` и константа `HORIZON_ALIASES` остались
  в истории git, но не в текущем коде.

---

## Phase 9 — Graph view (Obsidian-style) ❌ FUTURE

**Цель:** визуализация связей между задачами и категориями в виде
графа узлов и рёбер, как в Obsidian. По запросу пользователя:
«рак, система, граф... обсидиана знаешь, да... связанные графы».

**Идея:**
- Каждая категория = большой узел в центре своего кластера.
- Каждая задача = малый узел, связанный с категорией.
- Подкатегории / parent-child задачи = вложенность.
- Тап по узлу → раскрывает связанные узлы, остальное угасает.

**Что нужно:**
- `react-force-graph-2d` или `cytoscape.js` (force-directed layout).
- API: `GET /api/graph` → `{nodes: [...], edges: [...]}`.
- Mobile-friendly: zoom + pan через pinch/drag, не блокировать
  скролл фоновой страницы.
- Возможно — добавить новый таб в `BottomNav` («Граф») рядом с
  «Задачи / Календарь / Настройки».

**Почему НЕ сейчас:**
- Сложность реализации (force-directed на mobile тормозит,
  нужен throttling + worker).
- Bundle size: cytoscape.js ~200 KB gzip — это +50% к текущему.
- ROI спорный пока юзер не использует категории/связи активно.

---

## Параллельные треки

- **Скиллы и best practices** — пополняем `.agents/skills/` по мере находок;
- **`docs/PROGRESS.md`** — обновляем после каждого PR;
- **`memory/`** — копим транскрипты для DSPy.

---

## Next Up — приоритеты на 2026-05-26

Расстановка после прохода по PROGRESS / handoff v20 / предложений от ревьюера.
Каждый пункт — потенциально отдельный PR ≤ 400 LOC.

> **Phase 7e (polish) полностью смержена в `main`** (#123–#139, см. шапку и
> `docs/plans/2026-05-25-phase7e-polish.md`). Ниже — обновлённый список:
> сделанные пункты вычеркнуты, открытые сохранены.

### P0 — гигиена и долги
1. ✅ ~~**Windows TZ-bug fix**~~ — закрыто, см. `app/shared/time.py`.
2. ✅ ~~**`TaskEvent` для cancel-reminders**~~ — закрыто, аудит-события
   эмитятся в обоих путях отмены.
   Audit-история reminder-изменений.

### P1 — продуктовое
3. ✅ ~~**Voice Inbox card UX**~~ (вкладка «Входящие», вариант Б) —
   полностью закрыт:
   - ✅ Слайс 1 — бэкенд `needs_review` + эндпоинты pending/confirm (#145).
   - ✅ Слайс 2 — фронт-вкладка с чекбоксами keep/drop + «Подтвердить» (#146).
   - ✅ Слайс 3 — инлайн-`[Исправить]` названия задачи (#150).
   - ✅ Слайс 4 — правка категории/приоритета (#152) + выключатель ревью
     `review_enabled` в /settings (#153, миграция 0016).
   - ✅ Слайс 5 — ИИ-`[Разбить]` задачи на подзадачи (#155, эндпоинт
     `POST /api/tasks/{id}/split`).
   - Опционально на потом: ревью заметок во вкладке.
4. ✅ ~~**Phase 7d — Task detail + inline edit** в Mini-App~~ — закрыто.
5. **Phase 5.5 — FullCalendar view** — **частично перекрыто** новым календарём
   Месяц/Неделя/Агенда из Phase 7e (#132). Полу-готовая ветка
   `devin/*-phase5-5-calendar` (FullCalendar) более не приоритетна; оставшийся
   возможный долг — серверная фильтрация по диапазону, если понадобится.

### P2 — AI-качество
6. **PR-H Critic refinement** — multi-stage critic, чёткие пороги
   confidence, prompt с chain-of-thought.
7. **LLM golden evals** — 50 русских фраз в `tests/golden/ru/*.json`,
   метрика % правильных category/horizon/priority. Пересекается с P2.6.
8. **PR-F OpenRouter fallback** — нужен `OPENROUTER_API_KEY` от юзера.

### P3 — observability / ops
9. **Sentry/Logfire** на free tier — error tracking в проде.
10. **Backup БД** — nightly `pg_dump → S3/R2/B2`.
11. **Расширенный README** — скриншоты, GIF, deployment guide.
12. **DSPy** — автоподбор промптов на основе golden-set (после P2.7).

### P4 — отложено / future
- **Excel export/import** + table-classifier.
- **Graph view (Phase 9)** — Obsidian-style визуализация связей.
- ✅ ~~**Brand design / design tokens**~~ — закрыто в Phase 7e
  (`webapp/DESIGN.md` + дизайн-система, #128/#129).
- **Minor M-1..M-9** из v2-ревью — чистка, не критично.
