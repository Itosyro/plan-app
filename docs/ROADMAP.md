# ROADMAP — фазы

Каждая фаза = отдельный PR. Маленькие PR, ревьюить и откатывать удобнее.

---

## Phase 0 — Cleanup + Python skeleton (этот PR)

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

## Phase 1 — Минимальный бот (webhook + БД)

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

## Phase 2 — AI-пайплайн (Splitter + Classifier + Critic + Time Resolver)

**Цель:** голосовое/текстовое сообщение превращается в задачи и заметки.

**Содержимое:**
- `app/ai/router.py` — GroqKeyRouter (3 ключа, round-robin, fallback);
- `app/ai/splitter.py` — `llama-3.1-8b-instant`, выход через `instructor`;
- `app/ai/classifier.py` — `llama-3.3-70b-versatile`, авто-создание категорий;
- `app/ai/critic.py` — режим `confidence` по умолчанию;
- `app/ai/time_resolver.py` — `dateparser` + `pymorphy3` + `razdel`, чистый Python;
- `app/ai/reminder_extractor.py` — извлечение «через 43 минуты»;
- транскрибация через Groq Whisper (`whisper-large-v3`);
- SQLModel: `Category`, `Horizon`, `Task`, `Note`, `AiRun`, `TaskEvent`;
- Alembic: миграция;
- бот отвечает «курьерским» сообщением с резюме;
- перестановка задач голосом (минимальная: «перенеси Х на Y»);
- e2e тесты на 5–10 типовых русских фраз.

**Критерий готовности:**
- голос «утром пробежка, в 11 совещание, до пятницы отчёт, обед через час напомни» → 4 задачи + 1 напоминание;
- юзер задал перестановку → задача обновлена.

---

## Phase 3 — Категории, горизонты, ручное редактирование

**Цель:** юзер может управлять структурой через бот.

**Содержимое:**
- команды бота: `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`;
- инлайн-кнопки на карточке задачи: «выполнено», «перенести», «удалить», «изменить категорию»;
- настройки `/settings`: критик режим, дефолтное напоминание, утренний/вечерний дайджест, часовой пояс, стиль ответа;
- API эндпоинты для будущего mini-app (но без UI пока);
- импорт/экспорт в `.xlsx` через `openpyxl`.

---

## Phase 4 — Напоминания и дайджесты (cron worker)

**Цель:** бот сам присылает что нужно когда нужно.

**Содержимое:**
- отдельный сервис `app/workers/scheduler.py` — Render cron job, раз в минуту;
- читает `reminders` где `fire_at <= now()` и отправляет через Telegram Bot API;
- утренний и вечерний дайджесты по расписанию из `UserSettings`;
- ретраи через `processing_jobs`;
- метрики latency / ошибок.

---

## Phase 5 — Telegram mini-app

**Цель:** красивый веб-UI внутри Telegram.

**Содержимое:**
- React + Vite + Tailwind (отдельная папка `webapp/`);
- собирается в статику и отдаётся из FastAPI;
- три вкладки: Канбан / Календарь / Список;
- drag-n-drop задач между горизонтами и категориями;
- карточка задачи: содержимое;
- детали задачи: оригинальный транскрипт + история событий;
- авторизация через Telegram `initData`;
- темизация под Telegram theme.

---

## Phase 6 — Polish, наблюдаемость, эвалы

**Цель:** довести до состояния «не стыдно показать».

**Содержимое:**
- логирование (structlog), метрики;
- LLM-эвалы: golden-set из 50 русских фраз, прогон через пайплайн, сравнение с эталоном;
- DSPy: попытка автоподбора промптов;
- backup БД (cron, дамп в внешний bucket);
- pre-commit hooks (ruff, mypy);
- mypy strict в core-модулях;
- расширенный README.

---

## Параллельные треки

- **Скиллы и best practices** — пополняем `.agents/skills/` по мере находок;
- **`docs/PROGRESS.md`** — обновляем после каждого PR;
- **`memory/`** — копим транскрипты для DSPy.
