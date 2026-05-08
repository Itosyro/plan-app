# HANDOFF — единый документ для передачи проекта другой нейронке

> Этот файл — **единственное**, что нужно прочитать, чтобы войти в курс дела. Всё остальное (`PLAN.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `IDEAS.md`) — детализация.
>
> Если ты — нейронка, открывшая репо впервые: прочти этот файл, потом [`docs/README.md`](README.md), потом [`.agents/skills/CATALOG.md`](../.agents/skills/CATALOG.md), потом [`.agents/skills/plan-app-internal/SKILL.md`](../.agents/skills/plan-app-internal/SKILL.md). Этого хватит, чтобы начать.

---

## 0. Кратко

**Что строим:** Telegram-бот, который превращает голос/текст («поток мыслей» юзера) в структурированный план — задачи, заметки, напоминания. Под капотом — несколько LLM в цепочке «черновик → проверка», русский NLP, Postgres.

**Для кого:** один пользователь сейчас, архитектурно — на 100+ юзеров.

**Стек:** Python 3.12, aiogram 3 (бот), FastAPI (HTTP+webhook+Mini App), SQLModel + Alembic, Pydantic v2, Groq API (LLM + Whisper), `instructor` (структурный output), `dateparser`+`pymorphy3`+`razdel` (русский NLP), uv (пакеты), ruff (линт+формат), pytest, Docker. Деплой: Render Free + Neon Postgres. Доставка апдейтов — **webhook**, не polling.

**Где сейчас (2026-05-08):** Phase 0, 0.5, 1, 1.5, **out-of-order Phase 4** (деплой + e2e живого бота) и **Phase 2.1** (Splitter + AI infrastructure) **смерджены в main**. Бот живой на https://plan-app-t6nx.onrender.com под именем **@daylirobot** (PLAN). Splitter разбивает текст на атомарные намерения через `llama-3.1-8b-instant` + `instructor`, результат логируется (задачи пока не сохраняются — Phase 2.2). Дальше — **Phase 2.2** (Classifier + русский NLP + сохранение задач в БД).

**Главное правило:** маленькие PR пофазно. Никаких мегаPR. Размер PR ≤ 400 LOC.

**Кто мерджит:** Юзер (Юсуф) **не делает merge** — это работа AI-агента через GitHub REST API после `ruff format/check + pytest` зелёных и явного «давай мерджи» от юзера. Закреплено в `.agents/skills/plan-app-internal/SKILL.md` §11.

---

## 1. История разговора (что уже решено с юзером)

### 1.1. Язык реализации
**Python.** Юзер изначально писал на TS, но переехали на Python потому что:
- упор в нейронки и в перспективе локальные LLM;
- зрелее экосистема для AI: `instructor`, `DSPy`, `langgraph`, `litellm`;
- русский NLP — `dateparser`, `pymorphy3`, `razdel` сильно лучше JS-аналогов;
- юзер по времени не ограничен.

### 1.2. Multi-LLM пайплайн (3 ключа Groq)
- Splitter (быстрая 8B) → Classifier (умная) → опц. Critic (reasoning).
- Critic запускается «по уверенности» (confidence < 0.7) по умолчанию.
- 3 ключа Groq для **отказоустойчивости**, не для производительности — для одного юзера хватит и одного, но 3 = надёжность + headroom.
- `GroqKeyRouter` — простой round-robin с fallback в самом приложении (~50 строк), без отдельного сервиса.

### 1.3. Модели Groq

| Шаг | Модель | Почему |
|---|---|---|
| Splitter | `llama-3.1-8b-instant` | очень быстрая, задача простая (разбиение) |
| Classifier | `llama-3.3-70b-versatile` | основной мозг, понимает контекст |
| Critic | `qwen-qwq-32b` (reasoning) | специально натаскана думать пошагово |
| Whisper | `whisper-large-v3` | максимальная точность, не turbo |
| Courier-LLM (~50% ответов) | `llama-3.1-8b-instant` | короткая фраза, мало токенов |

**Резерв** на A/B в Phase 2: `llama-4-scout-17b-16e-instruct`, `llama-4-maverick-17b-128e-instruct`, `gemma2-9b-it`, `whisper-large-v3-turbo`.

### 1.4. Категории и горизонты
- У каждого юзера **свои** категории и горизонты.
- AI **сам создаёт** новые на лету, если ничего не подошло.
- Стартового списка нет — пустой, заполняется по мере использования.
- AI сам предлагает `keywords` / `prompt_hint`, юзер может править в `/settings` или в Mini App.

### 1.5. Горизонты
Дефолтные slug'и: `today` / `tomorrow` / `week` / `month` / `year` / `someday`. AI может создать кастомный (например, `quarter`).

### 1.6. Семантика «на этой неделе»
- **Дефолт:** дедлайн = воскресенье 23:59 текущей ISO-недели.
- В `/settings` можно переключить на «метка без срока» (`due_at = null`, `horizon = week`).
- Юзер для конкретной задачи может переопределить.

### 1.7. «Через 5 минут пойти бегать» — задача или напоминание?
**AI решает по контексту** (вариант C):
- если глагол явно действие — задача + напоминание;
- если «напомни …» — только напоминание.

### 1.8. Дефолтные напоминания
- Задача в течение **сегодня** → напоминание за **1 час** + **15 минут**.
- Задача через **N дней** → напоминание за **1 день** + **1 час**.
- Без `due_at` → напоминаний нет.
- Хранится в `UserSettings.default_reminder_offsets` (JSON).
- Всё настраивается в `/settings`.

### 1.9. Critic-режим
- `paranoid` — всегда (дороже на ~30%).
- `confidence` (**дефолт**) — только если `Classifier.confidence < 0.7`.
- `off` — выключен (для отладки).
- Тумблер в `/settings`.

### 1.10. Дайджесты
- Утренний — **08:00**, вечерний — **21:00** (по умолчанию, настраивается).
- Утром: задачи на сегодня + просроченное вчера + горящие дедлайны недели.
- Вечером: что закрыто, что осталось.

### 1.11. Стиль ответа бота — «курьер»
Каждый ответ = подтверждение + резюме сделанного.

**Подтверждение** выбирается **рандомно per-reply**:
- ~50% — из шаблонов (≥30 фраз, ≥5 на каждый стиль; стили: `neutral`, `formal_master` («мой господин»), `friendly`, `playful`, `terse`, `respectful`);
- ~50% — генерируется через `llama-3.1-8b-instant` («дай 1 фразу подтверждения в стиле X на русском, ≤8 слов»).

В `/settings` юзер может зафиксировать `template_only` / `llm_only` / `mix` (дефолт `mix`).

**Резюме сделанного** — всегда **детерминированно** из персистнутых записей (без LLM).

### 1.12. Onboarding
При первом `/start`:
1. «Как тебя зовут?»
2. «Часовой пояс?» (`/timezone Europe/Moscow` или геолокация)
3. Показать дефолты (08:00 утренний, 21:00 вечерний, напоминания 1ч+15мин, Critic «по уверенности», курьер «микс», неделя = воскресенье 23:59)
4. «Всё это меняется в `/settings`».
5. Создать строку в `user_settings`.

### 1.13. Telegram Mini App (Phase 5)
- React + Vite + Tailwind (отдельная папка `webapp/`).
- 3 вкладки: Канбан / Календарь / Список.
- Drag-n-drop между горизонтами и категориями.
- На карточке — содержимое задачи; в деталях — оригинальный транскрипт.
- Авторизация через Telegram `initData`.
- Темизация под Telegram theme.

### 1.14. Деплой
- Render Free (1 web + 1 cron).
- Neon Postgres (free tier, не умирает в отличие от Render Postgres free).
- Webhook, не polling.
- `render.yaml` есть, `autoDeploy: false` — пока не пушим в облако.

### 1.15. Стиль кода
- Docstrings — **на английском** (industry standard).
- Комментарии — **на русском в сложных местах**.
- Никаких `Any`, `getattr`, `setattr` для обхода типизации.
- Никаких `print()` — структурированный лог через `app/shared/logging.py` (будет в Phase 1).
- Импорты — все наверху файла, никаких inline-импортов.
- Никаких inline-промптов в коде — все промпты в `app/ai/prompts/<name>.md`.

### 1.16. Чистка репо (сделано в Phase 0)
Юзер разрешил снести:
- весь TS (`src/`, `prisma/`, `public/`, `package.json`, `tsconfig.json`)
- мусор от Hermes-бэкапа (`Vault/`, `Projects/`, `.hermes-backup/`, `AGENTS.md`, `PROJECTS.md`)
- старый `README.md`
- `smartkeyrouter` идею (заменили простым роутером в `app/ai/`)

---

## 2. Стек и где что лежит

```
plan-app/
├── README.md                    проект в двух абзацах
├── pyproject.toml               зависимости + конфиг uv
├── uv.lock                      lock-файл (коммитим)
├── ruff.toml                    линт + формат
├── .python-version              3.12
├── .env.example                 шаблон env
├── .gitignore
├── .dockerignore
├── Dockerfile                   многостадийная сборка
├── render.yaml                  Render: 1 web + 1 cron, autoDeploy: false
├── alembic.ini                  alembic конфиг
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                 миграции (.gitkeep пока)
├── app/
│   ├── main.py                  FastAPI app + lifespan + webhook регистрация
│   ├── shared/
│   │   ├── config.py            Pydantic Settings (env)
│   │   └── logging.py           (Phase 1) structlog
│   ├── bot/                     aiogram handlers (Phase 1+)
│   ├── api/                     FastAPI routes для Mini App (Phase 3+)
│   ├── ai/                      AI-пайплайн (Phase 2)
│   │   ├── router.py            GroqKeyRouter (3 ключа)
│   │   ├── splitter.py
│   │   ├── classifier.py
│   │   ├── critic.py
│   │   ├── time_resolver.py     dateparser + pymorphy3 + razdel
│   │   ├── reminder_extractor.py
│   │   ├── courier.py           шаблоны + LLM выбор стиля
│   │   └── prompts/<name>.md    отдельные файлы промптов
│   ├── db/                      SQLModel модели + репозитории
│   └── workers/
│       └── scheduler.py         cron (Phase 4)
├── tests/                       pytest + pytest-asyncio
├── memory/                      сырые потоки мыслей юзера для DSPy
├── docs/
│   ├── README.md                как пользоваться docs/
│   ├── PLAN.md                  что строим (продукт)
│   ├── ARCHITECTURE.md          как устроено (техника)
│   ├── ROADMAP.md               фазы
│   ├── PROGRESS.md              лог сделанного (append-only)
│   ├── IDEAS.md                 что хочется в будущем
│   └── HANDOFF.md               этот файл
└── .agents/skills/              методички для AI (см. CATALOG.md)
```

---

## 3. AI-пайплайн (как мысль превращается в задачи)

```
[ голос или текст в Telegram ]
        │
        ▼
[ Whisper (whisper-large-v3) ]                  ── только если голос
        │
        ▼
[ razdel.sentenize ]                             ── разбили на предложения
        │
        ▼
[ Splitter (llama-3.1-8b-instant) ]              ── список «сырых» интентов
        │
        ▼
[ time_resolver (Python, не LLM) ]               ── «через 43 минуты» → datetime
        │
        ▼
[ Classifier (llama-3.3-70b-versatile) ]         ── категория, горизонт, приоритет,
        │                                            task vs note, reminder_offsets,
        │                                            confidence
        ▼
[ Critic (qwen-qwq-32b) — если confidence<0.7 ]  ── ловит ошибки Classifier'а
        │
        ▼
[ persist (Postgres через SQLModel) ]
        │
        ▼
[ Courier reply (шаблон или LLM, рандом 50/50) ] ── короткое подтверждение
[ Summary (детерминированный) ]                  ── «добавил 4 задачи, 1 напоминание»
        │
        ▼
[ ответ в Telegram ]
```

Каждый шаг — отдельный файл в `app/ai/`. Все шаги **через `instructor`** (структурный output по Pydantic-моделям). Ноль regex по JSON.

---

## 4. Roadmap

| Phase | Что делаем | Статус |
|---|---|---|
| **0** | Чистка + Python скелет + docs | **смерджена** (PR #3) |
| **0.5** | `.agents/skills/` (Anthropic snapshots + 7 custom + Brex reference + CATALOG) | **смерджена** |
| **1** | Бот: webhook + БД + onboarding + первая Alembic миграция | **смерджена** (PR #6, sha `c17bab4`) |
| **1.5** | GitHub Actions CI (uv → ruff → pytest) + driver-нормализация для Neon | **смерджена** (PR #7, sha `eacb3a9`) |
| **4 (out-of-order, часть 1)** | `render.yaml` под Python + создание Render-сервиса + регистрация webhook | **смерджена** (PR #8, sha `6819d18` — render.yaml; PR #9 sha `606526a` — docs; PR #10 sha `fbae8fc` — e2e-проверка) |
| **2.1** | Splitter + AI infrastructure (`GroqKeyRouter`, `split_message`, `instructor`, Pydantic schemas) | **смерджена** (PR #12) |
| **2.2** | Classifier + русский NLP + модели Task/Note/AiRun + сохранение в БД | **следующая** |
| **2.3** | Critic + Whisper + Courier | после P2.2 |
| **3** | Команды бота (`/today` …), inline-кнопки, `/settings`, REST API заготовки | после P2 |
| **4 (часть 2)** | Cron worker — напоминания, утренние и вечерние дайджесты + FSM на Postgres-storage | после P2/P3 |
| **5** | Telegram Mini App (React + Vite + Tailwind) | после P4 |
| **6** | Polish: structlog, eval-сеты, DSPy, mypy strict, бэкап БД | финал |

Каждая фаза = отдельный PR. Размер PR ≤ 400 LOC, одна тема.

---

## 5. Что **не** делаем

- ❌ Никакого web-сайта вне Telegram.
- ❌ Никакого Redis (Render Free его не даёт; очередь — на Postgres).
- ❌ Никакой OpenAI/Anthropic — только Groq на старте. Локальные LLM — отдельный эксперимент в будущем.
- ❌ Никакой авторизации по email/паролю — только Telegram.
- ❌ Никакого `smartkeyrouter` (это была идея из старого репо, не нужна).
- ❌ Никаких больших PR.
- ❌ Никаких inline-промптов в коде.
- ❌ Никаких живых вызовов Groq в тестах. Только моки через `respx`.
- ❌ Никаких force-push в main.
- ❌ Никаких `git add .` без проверки.
- ❌ Никакого PII в логах (телефон, email, текст голосовух).

---

## 6. Стандартный workflow в этом репо

### 6.1. Перед любой работой
```bash
git checkout main && git pull
uv sync                    # обновить зависимости из uv.lock
git checkout -b devin/$(date +%s)-<short-name>
```

### 6.2. Перед commit'ом
```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
```

### 6.3. Создание PR
- Заголовок: `Phase X: <тема>` или `Bugfix: <тема>` или `Refactor: <тема>`.
- Описание — по шаблону из [`.agents/skills/writing-prs/SKILL.md`](../.agents/skills/writing-prs/SKILL.md).
- Размер ≤ 400 LOC, одна тема.
- В конце PR — обновить `docs/PROGRESS.md` новой секцией с датой.

### 6.4. Команды разработки
```bash
uv sync                                  # установка зависимостей
uv run ruff format .                     # авто-формат
uv run ruff check .                      # линт
uv run ruff check --fix .                # авто-фиксы
uv run pytest -q                         # тесты
uv run uvicorn app.main:app --reload     # dev-сервер (Phase 1+)
uv run alembic upgrade head              # применить миграции
uv run alembic revision --autogenerate -m "msg"   # новая миграция
docker build -t plan-app .               # собрать контейнер
```

### 6.5. Перед деплоем (Phase 1+)
- Установить webhook: `setWebhook` с `secret_token` (валидируется в `app/main.py`).
- Render env-vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_URL`, `DATABASE_URL`, `GROQ_API_KEY_1/2/3`.
- `autoDeploy: false` — пушим вручную после ревью.

---

## 7. Главные подводные камни (читать обязательно)

1. **Webhook должен ответить 200 за < 1 секунду** — иначе Telegram ретраит. Тяжёлая работа — в фоновую задачу (`asyncio.create_task` или `processing_jobs`).
2. **Voice ≤ 20 МБ** — Telegram режет. Для длинных голосовух — `getFile` сначала, размер проверять до скачивания.
3. **Структурный LLM-output** — только через `instructor` с Pydantic. Никакого `json.loads` по сырому ответу.
4. **Async LLM-calls** — `groq.AsyncGroq`, не sync. В webhook-хендлере sync блокирует event loop.
5. **TZ** — храним всё в UTC, отображаем в `users.tz`. Дайджесты считаем по `users.tz`.
6. **`drop_pending_updates=True`** при `setWebhook` — иначе при перезапуске прилетят все накопившиеся апдейты.
7. **`callback_data` ≤ 64 байта** — для inline-кнопок. Используем формат `domain:action:id` (например `task:done:42`).
8. **`uv.lock` коммитим** — иначе разные версии у разработчиков и в проде.
9. **`needs_clarification`** — если Critic не уверен, помечаем задачу/заметку этим флагом, бот переспрашивает в ответе.

---

## 8. Скиллы (`.agents/skills/`)

Это методички для AI-агентов и людей. **Перед правкой кода — читать.** Полная карта в [`.agents/skills/CATALOG.md`](../.agents/skills/CATALOG.md).

**Custom (под plan-app):**
- `plan-app-internal/SKILL.md` — карта проекта
- `prompt-engineering/SKILL.md` — best practices LLM-промптов
- `code-review/SKILL.md` — чек-лист на 30 пунктов
- `writing-prs/SKILL.md` — шаблон PR
- `russian-nlp/SKILL.md` — парсинг русского
- `aiogram-3/SKILL.md` — паттерны бота
- `groq-tips/SKILL.md` — Groq API + 3 ключа

**Snapshot (Anthropic, Apache 2.0):** `skill-creator/`, `mcp-builder/`, `webapp-testing/`.

**External reference:** `brex-prompt-engineering/REFERENCE.md` (MIT, 80 KB концентрат).

---

## 9. Уже сделано (статус Phase 0 + 0.5)

### Phase 4 — out-of-order часть 1 (3 PR'а, смерджены 2026-05-08)
- ✅ **PR #8** (`6819d18`) — `render.yaml` переписан под Python: один web-сервис `plan-app`, `runtime: python`, `region: frankfurt`, `plan: free`, `buildCommand: uv sync --frozen`, `startCommand: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /healthz`, `autoDeployTrigger: commit`. Старый Node-конфиг (TS-эпохи) удалён.
- ✅ Render-сервис создан через REST API: `srv-d7uohcf7f7vs73crmk3g`, public URL https://plan-app-t6nx.onrender.com, workspace «Cile Simme's workspace» (`tea-d7tr6vugvqtc73bsjka0`) — это второй Render-аккаунт юзера (подтверждено).
- ✅ ENV-переменные на Render проставлены через REST API: `ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12` + 5 секретных (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_BASE_URL`, `DATABASE_URL`, `GROQ_API_KEYS`). В git ничего из секретов не попало.
- ✅ Telegram webhook зарегистрирован, `getWebhookInfo` отдаёт URL+IP, ошибок нет.
- ✅ `/healthz` отвечает 200; e2e-онбординг живого юзера прошёл: `users` 1, `user_settings` 1, `inbox_entries` 3, `telegram_updates` 7, идемпотентность не сломана.
- ✅ **PR #9** (`606526a`) и **PR #10** (`fbae8fc`) — docs (PROGRESS + SKILL §13 «Live deploy (Render)»).

### Phase 1.5 (PR #7, смерджен 2026-05-08)
- ✅ `.github/workflows/ci.yml` — pipeline на каждый push в `main` и на каждый PR: чекаут → `astral-sh/setup-uv` (с кэшом по `uv.lock`) → `uv sync --frozen` → `ruff format --check` → `ruff check` → `pytest -q`. Concurrency: новая попытка отменяет предыдущую на той же ветке.
- ✅ Driver-hotfix: голый `postgresql://` (вид Neon copy-paste) автоматически становится `postgresql+psycopg://` в `app/db/base.py` и `alembic/env.py`. SQLite получает суффикс `+aiosqlite`.
- ✅ `tests/test_smoke.py` — `monkeypatch`-фикстура для тестов дефолтных настроек, чтобы не падали на дев-машинах с уже экспортированными секретами.
- ✅ В `.agents/skills/plan-app-internal/SKILL.md` зафиксированы §11 «Merge-workflow» и §12 «PR tooling».

### Phase 1 (PR #6, смерджен 2026-05-08)
- ✅ `app/shared/config.py` — Pydantic Settings, `webhook_url`, `lru_cache`-обёртка `get_settings()`.
- ✅ `app/shared/logging.py` — `structlog` (JSON в проде, console в dev), запрет PII в логах.
- ✅ `app/db/` — четыре модели Phase 1 (`User`, `UserSettings`, `InboxEntry`, `TelegramUpdate`), async engine + sessionmaker, BigInteger для Telegram-ID, JSON для `default_reminder_offsets`.
- ✅ Alembic подключён к `SQLModel.metadata` и `DATABASE_URL`, миграция `0001_init` создаёт 4 таблицы + индексы. Применена против настоящей Neon-БД (5 таблиц с учётом `alembic_version`).
- ✅ `app/bot/`:
  - `routers/start.py` — `/start`, `/help`, FSM-онбординг (имя → IANA-tz → дефолты).
  - `routers/text.py` — catch-all для текстов: пишет в `inbox_entries`, отвечает заглушкой «AI подключим в Phase 2».
  - Роутеры — фабрики (`create_router()`), чтобы каждое `build_dispatcher()` собирало свежий граф (aiogram запрещает повторное прикрепление одного `Router` к двум диспетчерам).
  - FSM-storage = `MemoryStorage` (Phase 4 переключим на Postgres-storage).
- ✅ `app/main.py` — FastAPI с lifespan-`set_webhook(drop_pending_updates=True, secret_token=...)`, `POST /tg/<secret>` с двойной валидацией (path-secret + `X-Telegram-Bot-Api-Secret-Token`), идемпотентность по `update_id`. `/healthz` сохранился.
- ✅ Тесты: `tests/test_services.py` (unit), `tests/test_webhook.py` (security + идемпотентность POST'а с замоканным aiogram), `tests/conftest.py` (in-memory SQLite, Settings, TestClient). Всего **14 тестов**.
- ✅ Dev-зависимости: `aiosqlite`, `respx`. Ruff: глобально игнорим `RUF001/002/003` (false positives на кириллице).

### Phase 0 (PR #3, смерджен 2026-05-07)
- ✅ удалён весь TS + Hermes-мусор
- ✅ Python 3.12 skeleton: `pyproject.toml` (uv), `ruff.toml`, Dockerfile, `.python-version`, `.env.example`
- ✅ структура `app/{bot,api,ai,db,workers,shared}/` с `__init__.py`
- ✅ `app/main.py` — FastAPI с `/healthz`
- ✅ `app/shared/config.py` — Pydantic Settings
- ✅ 4 smoke-теста, ruff чистый, pytest зелёный
- ✅ `alembic/` + `alembic.ini` (без миграций)
- ✅ `memory/` + `.agents/skills/` (placeholder)
- ✅ `render.yaml` — 1 web + 1 cron, `autoDeploy: false`
- ✅ `docs/`: PLAN, ARCHITECTURE, ROADMAP, PROGRESS, IDEAS, README

### Phase 0.5 (смерджен 2026-05-07)
- ✅ `.agents/skills/` — 49 файлов, ~672 КБ
- ✅ 7 custom SKILL.md
- ✅ 3 Anthropic snapshot
- ✅ Brex reference
- ✅ CATALOG.md
- ✅ ruff exclude для third-party снепшотов

### Phase 2.1 — Splitter + AI infrastructure (PR #12, смерджен 2026-05-08)
- `app/ai/router.py` — `GroqKeyRouter`: round-robin пул API-ключей Groq с `advance()` и `async_client()`.
- `app/ai/schemas.py` — Pydantic-модели `IntentUnit` и `SplitterResult`.
- `app/ai/splitter.py` — `split_message()`: `llama-3.1-8b-instant` через `instructor` (temperature 0.0). Короткие сообщения (< 2 символов) пропускаются без LLM.
- `app/ai/prompts/splitter.md` — системный промпт (ROLE → TASK → CONSTRAINTS → OUTPUT → EXAMPLES), 3 few-shot примера на русском.
- `app/bot/routers/text.py` — интеграция: splitter в фоне (`asyncio.create_task`), результат логируется.
- 10 новых тестов (5 GroqKeyRouter + 5 Splitter с моком Groq через `respx`). Итого 24 теста.
- 361 LOC.

### Phase 2.2 — НЕ начата
Дальше — Classifier (`llama-3.3-70b-versatile`) + русский NLP (`dateparser` + `pymorphy3` + `razdel`) + модели Task/Note/AiRun + Alembic-миграция + сохранение задач в БД.

### Phase 2.3 — НЕ начата
Critic (`qwen-qwq-32b`, по уверенности) + Whisper (`whisper-large-v3`) + Courier (шаблоны + LLM 50/50).

---

## 10. Что нужно от юзера для следующих фаз

### Прямо сейчас (Phase 2)
- `GROQ_API_KEYS` — **уже сохранён в профиле юзера** (1 ключ из 3). Если в Phase 2 поймём что нужно больше для нагрузки — попросим ещё, но для одного юзера и одного ключа хватит.
- Желательно (не блокирует): ответы на «открытые вопросы» из `IDEAS.md`:
  - Что делать с просрочкой (авто-перенос или метка)?
  - Догонять пропущенные дайджесты или нет?
  - Дедупликация задач (мерджить или предупреждать)?
  - Юзер сам выбирает модели Groq в `/settings` или нет?

### К Phase 4 (часть 2 — cron, напоминания, дайджесты)
- Ничего нового от юзера. Render и Neon уже подключены, Telegram bot token уже сохранён в профиле, cron-сервис в Render Free создаётся через REST API.

### Все секреты уже в профиле юзера (`save_scope=user`)
- `TELEGRAM_BOT_TOKEN` — от @BotFather для `@daylirobot` (id `8642044324`).
- `TELEGRAM_WEBHOOK_SECRET` — сгенерирован Devin'ом (43 символа).
- `DATABASE_URL` — direct connection-string Neon (для Render Free в будущем заменим на pooled).
- `GROQ_API_KEYS` — 1 ключ (по необходимости попросим ещё).
- `RENDER_API_KEY` — **только эта сессия** (`save_scope=session`); следующая сессия попросит заново.

### К Phase 5 (Mini App)
- Решить, нужны ли drag-n-drop **между** горизонтами (или только внутри).
- Тема под темизацию Telegram.

---

## 11. Открытые вопросы (не блокируют)

- Уведомления о массовых событиях («у тебя сегодня 10 задач, точно потянешь?») — нужны?
- Догонять пропущенные дайджесты или нет?
- Что делать с просроченными задачами (авто-перенос или метка)?
- Юзер сам выбирает модели Groq в `/settings` (advanced) или нет?
- Лимит размера voice — 20 МБ хватит?
- Дедупликация задач: «купить молоко» вчера и «молоко купить» сегодня — мерджить или предупреждать?

---

## 12. Если ты — нейронка, продолжающая работу

### Минимальный onboarding (5 минут)
1. Прочти этот файл.
2. Прочти [`docs/README.md`](README.md) — правила работы с docs/.
3. Прочти [`docs/ROADMAP.md`](ROADMAP.md) — на какой фазе мы сейчас.
4. Прочти [`docs/PROGRESS.md`](PROGRESS.md) — что уже сделано.
5. Прочти [`.agents/skills/CATALOG.md`](../.agents/skills/CATALOG.md) — карта методичек.
6. Прочти [`.agents/skills/plan-app-internal/SKILL.md`](../.agents/skills/plan-app-internal/SKILL.md) — карта репо.

### Перед написанием первой строчки кода
- Ты делаешь **Phase 1**? → читай [`.agents/skills/aiogram-3/SKILL.md`](../.agents/skills/aiogram-3/SKILL.md).
- Ты делаешь **Phase 2** (AI)? → [`prompt-engineering/SKILL.md`](../.agents/skills/prompt-engineering/SKILL.md) + [`groq-tips/SKILL.md`](../.agents/skills/groq-tips/SKILL.md) + [`russian-nlp/SKILL.md`](../.agents/skills/russian-nlp/SKILL.md).
- Перед PR → [`writing-prs/SKILL.md`](../.agents/skills/writing-prs/SKILL.md).
- Перед approve → [`code-review/SKILL.md`](../.agents/skills/code-review/SKILL.md).

### Если что-то непонятно
- Уточни у юзера **до того**, как начнёшь писать код. Потеря 5 минут на вопрос дешевле, чем 2 часа на переписывание.
- Юзер не разработчик. Не используй жаргон. Объясняй на пальцах.
- Юзер пишет на русском. Ты тоже отвечай на русском.
- Юзер любит маленькие PR пофазно. Не тащи всё в один PR.
- Юзер хочет видеть прогресс — обновляй `docs/PROGRESS.md` после каждого PR.

### Стиль общения юзера
- Голосовые → длинные потоки мыслей с переходами. Извлекай смысл, не зацикливайся на деталях.
- Просит «представь что мне 15 лет» — никакого жаргона про git/PR/merge.
- Доверяет тебе — но требует **понятных объяснений** перед действиями, которые ему неочевидны (типа merge).

### Безопасность
- Не клади секреты в код / docs / комменты. Никогда.
- Если юзер случайно прислал секрет в чат — **сразу** скажи отозвать на https://github.com/settings/tokens или в провайдере.
- Все секреты — через env, через `request_secret`, через Render Settings.

---

## 13. Ссылки

### Project
- **Repo:** https://github.com/Itosyro/plan-app
- **Live service:** https://plan-app-t6nx.onrender.com (`/healthz`, `POST /tg/<secret>`)
- **Render dashboard:** https://dashboard.render.com/web/srv-d7uohcf7f7vs73crmk3g (workspace `tea-d7tr6vugvqtc73bsjka0` = «Cile Simme's workspace», 2-й аккаунт юзера)
- **Telegram bot:** [@daylirobot](https://t.me/daylirobot) (имя в Telegram — «PLAN»; bot id `8642044324`)
- **Neon project:** `ep-super-sea-al0s5kug.c-3.eu-central-1.aws.neon.tech` / db `neondb` (direct connection)

### Merged PRs
- **PR #3 (Phase 0):** https://github.com/Itosyro/plan-app/pull/3
- **Phase 0.5 commit:** https://github.com/Itosyro/plan-app/commit/41b43c8
- **PR #6 (Phase 1, sha `c17bab4`):** https://github.com/Itosyro/plan-app/pull/6
- **PR #7 (Phase 1.5, sha `eacb3a9`):** https://github.com/Itosyro/plan-app/pull/7
- **PR #8 (Phase 4 — render.yaml, sha `6819d18`):** https://github.com/Itosyro/plan-app/pull/8
- **PR #9 (Phase 4 — docs, sha `606526a`):** https://github.com/Itosyro/plan-app/pull/9
- **PR #10 (Phase 4 — e2e, sha `fbae8fc`):** https://github.com/Itosyro/plan-app/pull/10
- **PR #11 (Phase 4 closeout — HANDOFF.md update, sha `cd2351c`):** https://github.com/Itosyro/plan-app/pull/11
- **PR #12 (Phase 2.1 — Splitter + AI infrastructure):** https://github.com/Itosyro/plan-app/pull/12

### External docs
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **aiogram 3 docs:** https://docs.aiogram.dev/en/latest/
- **Groq docs:** https://console.groq.com/docs/
- **Neon docs:** https://neon.tech/docs/
- **Render docs:** https://render.com/docs
- **dateparser:** https://dateparser.readthedocs.io/
- **pymorphy3:** https://github.com/no-plagiarism/pymorphy3
- **razdel:** https://github.com/natasha/razdel
- **instructor:** https://python.useinstructor.com/
- **SQLModel:** https://sqlmodel.tiangolo.com/
- **Alembic:** https://alembic.sqlalchemy.org/

---

## 14. Контрольные точки для нейронки

Перед `git push` пробеги по этому списку:

- [ ] `uv run ruff format .` — отформатировано
- [ ] `uv run ruff check .` — линт чистый
- [ ] `uv run pytest -q` — тесты зелёные
- [ ] PR ≤ 400 LOC, одна тема
- [ ] заголовок PR: `Phase X: ...` или `Bugfix: ...` или `Refactor: ...`
- [ ] описание PR по шаблону `writing-prs/SKILL.md`
- [ ] обновлён `docs/PROGRESS.md`
- [ ] нет секретов в коммитах
- [ ] нет inline-промптов (всё в `app/ai/prompts/`)
- [ ] нет `Any`, `getattr`, `setattr` для обхода типизации
- [ ] нет `print()` — только структурированный лог
- [ ] миграции, если меняешь БД (Alembic autogenerate)
- [ ] eval-сет, если меняешь промпт (`app/ai/prompts/<name>.eval.yaml`)

---

> Этот файл — **контракт** между тобой (нейронкой) и юзером. Если что-то здесь не так — поправь и сделай отдельный PR. Файл живой.
