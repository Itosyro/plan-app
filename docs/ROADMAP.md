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
