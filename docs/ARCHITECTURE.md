# ARCHITECTURE — как это устроено

Документ для разработки. Если ты ИИ или человек, который начинает работать с кодом — читай это до того, как трогать что-либо.

---

## 1. Общая картина

```
                        Telegram
                           │ updates (webhook)
                           ▼
   ┌─────────────────────────────────────────────┐
   │           web service (Render)              │
   │  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
   │  │ aiogram  │  │ FastAPI  │  │ static    │  │
   │  │ webhook  │  │ /api/*   │  │ mini-app  │  │
   │  │ handler  │  │          │  │ (Phase 5) │  │
   │  └────┬─────┘  └────┬─────┘  └───────────┘  │
   │       │             │                       │
   │       ▼             ▼                       │
   │  ┌──────────────────────────────────────┐   │
   │  │   AI pipeline (app/ai/)              │   │
   │  │   Splitter → Classifier → Critic     │   │
   │  │   + GroqKeyRouter (3 keys)           │   │
   │  └──────────────────────────────────────┘   │
   │       │                                     │
   │       ▼                                     │
   │  ┌──────────────────────────────────────┐   │
   │  │   SQLModel repositories              │   │
   │  └──────────────────────────────────────┘   │
   └────────┬───────────────────────────────────┘
            │ Postgres protocol
            ▼
       Supabase PostgreSQL

   ┌──────────────────────────────────────┐
   │    cron worker (Render, every 1 min) │
   │  - dispatch due reminders            │
   │  - send morning/evening digests      │
   │  - retry failed AI runs              │
   └──────────────────────────────────────┘
```

Один web service содержит всё: webhook бота, REST API для mini-app, и саму mini-app (как статика). Cron worker — отдельный процесс, бьёт раз в минуту.

---

## 2. AI-пайплайн

```
voice/text in
    │
    ▼
┌───────────────┐
│  Whisper      │  whisper-large-v3 (Groq), max accuracy
│ Transcriber   │
└───────┬───────┘
        ▼
┌───────────────┐
│  Splitter     │  openai/gpt-oss-20b via GroqKeyRouter
│               │  task: разбить русский текст на отдельные интенты
│               │  output: list[RawIntent]
└───────┬───────┘
        ▼
┌───────────────┐
│ Time Resolver │  PURE PYTHON (dateparser + pymorphy3 + razdel)
│               │  «через 43 минуты», «во вторник», «до конца недели»
│               │  → конкретные datetime
└───────┬───────┘
        ▼
┌───────────────┐
│  Classifier   │  openai/gpt-oss-120b via GroqKeyRouter
│               │  task: каждому интенту → category + horizon + priority +
│               │       reminder_offsets (если есть)
│               │       решает «task или note», создаёт новые категории
│               │       при необходимости
│               │  output: list[ClassifiedIntent] + structured via instructor
└───────┬───────┘
        ▼
┌───────────────┐
│  Critic       │  openai/gpt-oss-120b via GroqKeyRouter
│               │  task: проверяет результат, исправляет ошибки,
│               │        либо отдаёт ОК. Режим «по уверенности» по
│               │        умолчанию (тумблер в /settings)
│               │  output: validated list, с пометкой «нужно уточнить»
│               │          если что-то непонятно
└───────┬───────┘
        ▼
   persist + reply
        │
        ▼
┌───────────────┐
│ Courier reply │  ~50% template / ~50% дешёвый LLM-call (gpt-oss-20b)
│               │  Шаблонов ≥30 (≥5 на стиль), выбираются рандомно
│               │  Юзер может зафиксировать «только шаблоны / только AI / микс»
└───────────────┘
```

### 2.1. Распределение моделей по ключам

Единственный источник правды — реестр `app/ai/models.py` (`get_models()`);
каждая стадия читает свой ID оттуда, любой перекрывается env-переменной
`GROQ_MODEL_<STAGE>` без редеплоя. Ключи не закреплены за стадиями:
`GroqKeyRouter` — round-robin с ротацией на 429/5xx, клиент кэшируется
на ключ.

| Шаг | Модель Groq (дефолт) | Почему |
|---|---|---|
| Whisper | `whisper-large-v3` | один большой запрос, точность > скорости (turbo хуже на русском) |
| Splitter / Intent / Reorder / Courier / TaskSplitter | `openai/gpt-oss-20b` | лёгкие стадии, важна скорость |
| Classifier | `openai/gpt-oss-120b` | основной мозг, надо понимать контекст |
| Critic | `openai/gpt-oss-120b` | вторая пара глаз над Classifier'ом |

**История (важно, чтобы не откатили):** до июля 2026 здесь стояли
`llama-3.1-8b-instant` / `llama-3.3-70b-versatile` / `qwen-qwq-32b`.
`qwen-qwq-32b` Groq снял с обслуживания; обе llama депрекированы
17 июня 2026 с отключением в августе 2026. Майская попытка перейти на
gpt-oss (PR #171) провалилась из-за `instructor.Mode.JSON` —
reasoning-токены ломали парсинг; в июле все колсайты переведены на
`Mode.TOOLS` (схема как tool, ответ из `tool_calls[0].function.arguments`),
и gpt-oss заработал. См. `docs/audit/2026-07-26-audit.md`.

ChatGPT/OpenAI на Groq не хостится — у Groq только опенсорс/опенвейт
(`openai/gpt-oss-*` — это открытые веса OpenAI, а не API OpenAI).

В Phase 2 проводим A/B на golden-set из 50 русских фраз (`tests/golden/ru/*.json`), оставляем то, что лучше по точности и стабильности.

Если какой-то из ключей упал/исчерпан — `GroqKeyRouter` пробует другой.

### 2.2. Critic-режим

- `paranoid` — Critic запускается всегда (дороже на ~30%, но надёжнее).
- `confidence` (по умолчанию) — Critic запускается только если Classifier вернул `confidence < 0.7`.
- `off` — Critic выключен (не рекомендуется, оставлено для отладки).
- Хранится в `UserSettings.critic_mode`, переключается тумблером в `/settings`.

### 2.3. Ревью-инбокс «Входящие» (вариант Б)

Раньше при низкой уверенности бот в чате спрашивал «создать? да/нет» и
откладывал создание. Теперь действует **вариант Б**: задачи создаются
сразу, а проверка вынесена в отдельную вкладку Mini-App «Входящие».

Триггер (в `app/bot/routers/_pipeline.py`): если из одного сообщения
получилось **≥2 задач** ИЛИ хотя бы одна единица с `confidence <
threshold`, то после персиста помечаем исходную запись
`InboxEntry.needs_review = True` и добавляем в ответ строку «📥 Отправил
на проверку — открой "Входящие"». Одиночная уверенная задача создаётся
молча, как и раньше.

Вкладка «Входящие» (Mini-App):
1. `GET /api/inbox/pending` — записи с `needs_review = True` + их
   топ-уровневые задачи (пустые карточки скрыты).
2. Юзер галочками оставляет нужные задачи (по умолчанию все отмечены) и
   жмёт «Подтвердить».
3. `POST /api/inbox/{id}/confirm` `{keep_task_ids}` — неотмеченные задачи
   soft-delete, флаг `needs_review` снимается, запись уходит из вкладки.

Отложено (следующие слайсы): инлайн-правка `[Исправить]` задачи до
подтверждения; настройка-выключатель триггера; ревью заметок (сейчас
только задачи).

### 2.4. Семантика «на этой неделе» и других относительных меток

| Фраза | Дефолт | Альтернатива (юзер выбирает в `/settings`) |
|---|---|---|
| «на этой неделе» | дедлайн = воскресенье 23:59 текущей ISO-недели | метка без срока (`due_at = null`, `horizon = week`) |
| «во вторник» | конкретная дата ближайшего вторника, время = 09:00 | время дня — настраиваемо |
| «в течение дня» | `due_at = сегодня 23:59`, `horizon = today` | — |
| «через N минут / часов» | абсолютный `fire_at`, `horizon = today/tomorrow` (по сдвигу) | — |
| «когда-нибудь» | `horizon = someday`, `due_at = null` | — |

### 2.5. Дефолтные напоминания

| Когда задача | Что создаём по умолчанию (если юзер не указал явно) |
|---|---|
| на сегодня (`due_at` сегодня) | напоминание за **1 час** и за **15 минут** |
| на следующие N дней (`due_at` через 1+ дней) | напоминание за **1 день** и за **1 час** |
| без `due_at` | напоминаний нет |

Хранится в `UserSettings.default_reminder_offsets` в формате `{"same_day": [60, 15], "multi_day": [1440, 60]}` (минуты).

### 2.6. «Курьер» — стиль ответа

Каждый ответ бота состоит из двух частей: **подтверждение** + **резюме сделанного**.

**Подтверждение** генерируется одним из двух способов, выбор рандомный per-reply:
- **Шаблон** (≥30 фраз, ≥5 на каждый стиль). Файл: `app/bot/courier_templates.py`. Стили: `neutral`, `formal_master` («мой господин»), `friendly`, `playful`, `terse`, `respectful`.
- **LLM** — лёгкая модель реестра (`openai/gpt-oss-20b`), очень короткий промпт «дай 1 фразу подтверждения в стиле X на русском, ≤8 слов». Логируется в `AiRun` для контроля стоимости.

Юзер в `/settings.response_style.source` может выставить `template_only` / `llm_only` / `mix` (дефолт `mix` 50/50).

**Резюме сделанного** всегда детерминированно собирается из персистнутых задач/напоминаний — без LLM.

### 2.7. Onboarding

При первом `/start` (нет записи в `users` для этого telegram_id) бот ведёт визард:
1. «Привет, как тебя зовут?» → `users.display_name`.
2. «Какой у тебя часовой пояс?» (`/timezone Europe/Moscow` или авто по геолокации Telegram) → `users.tz`.
3. Показывает дефолты:
   - утренний дайджест **08:00**, вечерний **21:00**;
   - напоминания за 1 час + 15 минут (для задач сегодня) и за 1 день + 1 час (для задач на N дней вперёд);
   - Critic — режим «по уверенности» (порог 0.7);
   - стиль курьера — микс (50/50 шаблоны/LLM);
   - семантика «на этой неделе» — дедлайн воскресенье 23:59.
4. «Всё это меняется в `/settings`».
5. Создаёт строку в `user_settings` с этими дефолтами.

---

## 3. Роутер ключей Groq

`app/ai/router.py` — простой round-robin с health-tracking. ~50 строк.

Возможности:
- хранит список ключей в порядке приоритета;
- на 429 или сетевой сбой — переключается на следующий, помечает текущий как «cool down 60 сек»;
- метрики (счётчик использований, ошибок) — пишет в `AiRun`;
- НИКАКОГО отдельного сервиса вроде `smartkeyrouter` — это часть приложения.

---

## 4. Доставка апдейтов: webhook, не polling

- Render free убивает long-running worker'ы → polling не годится.
- Telegram → POST на `https://<our-host>/tg/<secret-path>` → aiogram Dispatcher.
- Идемпотентность: `update_id` пишется в `TelegramUpdate`, дубль игнорируется.

---

## 5. Схема БД

PostgreSQL, одна база, multi-tenant (`user_id` на каждой записи).

### 5.1. Таблицы

| Таблица | Поля (ключевые) |
|---|---|
| `users` | id, telegram_id, display_name, lang_code, tz, onboarded_at, created_at |
| `user_settings` | user_id, critic_mode (`off`/`confidence`/`paranoid`, default `confidence`), critic_confidence_threshold (default 0.7), default_reminder_offsets (JSON: `{same_day:[60,15], multi_day:[1440,60]}`), morning_digest_at (default `08:00`), evening_digest_at (default `21:00`), response_style_source (`template_only`/`llm_only`/`mix`, default `mix`), week_due_semantic (`deadline_sunday`/`label_no_due`, default `deadline_sunday`) |
| `categories` | id, user_id, name, slug, prompt_hint, color, is_archived |
| `horizons` | id, user_id, slug (today/tomorrow/week/month/year/someday/custom), label, ordinal |
| `tasks` | id, user_id, category_id, horizon_id, title, description, priority, due_at, status, source_inbox_id, needs_clarification |
| `notes` | id, user_id, category_id, title, body, source_inbox_id |
| `reminders` | id, user_id, task_id (nullable), note_id (nullable), fire_at, status, sent_at, kind (custom/default) |
| `inbox_entries` | id, user_id, kind (text/voice), raw_text, transcript, telegram_message_id, needs_review, received_at |
| `ai_runs` | id, user_id, inbox_id, stage (split/classify/critic), model, key_index, latency_ms, tokens, status, error |
| `telegram_updates` | update_id PK, user_id, kind, processed_at |
| `task_events` | id, task_id, kind (created/updated/done/snoozed/deleted), payload_json, created_at |
| `processing_jobs` | id, user_id, kind, payload, run_at, status, attempts |

### 5.2. Связи

- `tasks.user_id` → `users.id`, `tasks.category_id` → `categories.id`, `tasks.horizon_id` → `horizons.id`.
- `notes.user_id` → `users.id`, `notes.category_id` → `categories.id`.
- `reminders.task_id` → `tasks.id` (опц), `reminders.note_id` → `notes.id` (опц).
- `task_events.task_id` → `tasks.id`.

### 5.3. Миграции

Alembic. Папка `alembic/versions/`. Каждый PR с изменениями схемы — новая ревизия.

---

## 6. Конфигурация

`app/shared/config.py` — Pydantic Settings, читает из ENV:

| ENV | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота |
| `TELEGRAM_WEBHOOK_SECRET` | секрет для пути `/tg/<secret>` |
| `GROQ_API_KEYS` | список через запятую |
| `DATABASE_URL` | Postgres URL (Supabase) |
| `LOG_LEVEL` | INFO / DEBUG |
| `CRITIC_DEFAULT_MODE` | confidence / paranoid |
| `WEBHOOK_BASE_URL` | публичный URL Render |
| `ENV` | development / production |

---

## 7. Стиль кода

- docstrings — английский (стандарт индустрии, удобнее для Sphinx и автодокументации).
- inline-комментарии в сложных местах — русский (ближе к проекту).
- ruff: format + check, fail-fast в CI.
- pytest + pytest-asyncio.
- Pydantic v2 для всех моделей запросов/ответов.
- SQLModel для таблиц.
- async везде где можно, `asyncio` event loop.

---

## 8. Что хранится в `memory/`

Папка для сырых транскриптов и потоков мыслей пользователя — для будущей оптимизации промптов через DSPy. **Сырые данные → не коммитим**, в репо лежит только README.md с описанием формата. На production — отдельный том или отдельный bucket (решим в Phase 6).

---

## 9. Безопасность

- Все секреты — только через ENV, никогда в репо.
- Telegram webhook валидирует `X-Telegram-Bot-Api-Secret-Token`.
- API mini-app валидирует `initData` Telegram.
- Логи без PII (текст голосовых не пишем в общий лог; только в `inbox_entries` за пользователем).
