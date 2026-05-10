# ROADMAP — фазы

Каждая фаза = отдельный PR. Маленькие PR, ревьюить и откатывать удобнее.

> **Status (на 2026-05-10, после PR #78 + #79):**
> Phase 0..7c — **done и в проде**. Работает: голосовое/текстовое
> сообщение → задачи + заметки + напоминания, утренний/вечерний
> дайджест (с pinned live-update), команды `/today /week /...`,
> callback-кнопки, /settings, **Mini-App** на `/app/` в стиле
> Todoist (lucide-icons + capsule bottom nav + drag-n-drop +
> per-horizon counts + CloudStorage prefs **+ настоящая Settings
> страница** с PATCH /api/me и picker'ом часовых поясов),
> **построчная** (streaming) выдача ответов бота, **emoji
> reactions** как ack/result-индикаторы, **quote replies**
> (`reply_parameters` + `quote`), **онбординг через inline-
> клавиатуру** (12 популярных CIS-часовых поясов + «Указать другой»).
> **323 теста**, ruff/mypy clean, https://plan-app-t6nx.onrender.com .
>
> Все critical (C-1..C-6) и important (I-1..I-8) findings из
> `docs/REVIEW-2026-05-09-v2.md` — закрыты. Плюс закрыты три
> reminder-бага (см. PR #79 в PROGRESS.md): `в 12` без минут теперь
> парсится, `is_reminder` пробрасывается в pipeline, `offset=0`
> валиден.
>
> **Прод-операция:**
> - Alembic migrations 0001..0008 накатаны на Neon.
> - Render `startCommand` авто-применяет `alembic upgrade head` на
>   каждом деплое.
> - Render env: `GROQ_API_KEYS` поддерживает comma-separated список
>   из 1+ ключей. Для ротации на 3 ключа нужно вручную обновить
>   на Render (юзер должен сделать).
>
> Что осталось:
> - **Phase 8** (voice/text-команды на удаление/перенос/изменение
>   задач) — **next priority**, юзер просил. Нужен action-classifier
>   + context-tracker + service-binding.
> - **Slash-команды** (`/add`, `/done`, `/move`, `/del`) — короткий
>   PR на ~150 LOC.
> - **Excel export/import** + table-classifier — отдельная фаза.
> - **Phase 7d** (Task detail + inline edit modal) — после 7c.
> - **Phase 5.5** (FullCalendar) — есть полу-готовая ветка
>   `devin/*-phase5-5-calendar`.
> - Phase 7 polish (наблюдаемость + эвалы) — **частично**
>   (structlog ✓, mypy strict ✓; golden-evals/DSPy/backup/Sentry ✗).
> - **Brand design / design tokens** — ждём go-ahead от юзера, пока
>   белая палитра.
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

### Phase 7c — Settings page в Mini-App ❌ TODO (next session)

- Заменить `ComingSoon` placeholder на реальный экран настроек.
- Секции по референсам: «✦ Основные», «🗒 Поведение», «⚪ Лимиты».
- Toggle-rows с leading-icon (`Bell` / `Sun` / `MessageSquare`/...).
- Связать с существующим `/api/me` + новым `PATCH /api/settings`
  (нужно добавить эндпоинт; bot-аналог `/settings` уже есть).
- Поля: tz (с тем же inline-keyboard-вызовом из бота? или
  Mini-App-native picker), morning/evening digest at, response
  style, courier template style, week_due_semantic, critic_mode.

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

## Phase 8 — Graph view (Obsidian-style) ❌ FUTURE

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
