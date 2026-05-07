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
       Neon PostgreSQL

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
│  Splitter     │  llama-3.1-8b-instant via Groq key 1
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
│  Classifier   │  llama-3.3-70b-versatile via Groq key 2
│               │  task: каждому интенту → category + horizon + priority +
│               │       reminder_offsets (если есть)
│               │       решает «task или note», создаёт новые категории
│               │       при необходимости
│               │  output: list[ClassifiedIntent] + structured via instructor
└───────┬───────┘
        ▼
┌───────────────┐
│  Critic       │  qwen-qwq-32b (reasoning) via Groq key 3
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
│ Courier reply │  ~50% template / ~50% дешёвый LLM-call (8b-instant)
│               │  Шаблонов ≥30 (≥5 на стиль), выбираются рандомно
│               │  Юзер может зафиксировать «только шаблоны / только AI / микс»
└───────────────┘
```

### 2.1. Распределение моделей по ключам

| Шаг | Модель Groq | Ключ | Почему |
|---|---|---|---|
| Whisper | `whisper-large-v3` | round-robin | один большой запрос, точность > скорости |
| Splitter | `llama-3.1-8b-instant` | key 1 | задача простая (разбить), важна скорость |
| Classifier | `llama-3.3-70b-versatile` | key 2 | основной мозг, надо понимать контекст |
| Critic | `qwen-qwq-32b` (reasoning) | key 3 | специально натаскана думать пошагово, отлично ловит ошибки Classifier'а |
| Courier-LLM (~50% ответов) | `llama-3.1-8b-instant` | round-robin | очень короткая фраза, минимум токенов |

#### Резервы / альтернативы (для Phase 2 будем сравнивать)

Groq на бесплатном тарифе сейчас даёт намного больше моделей, чем нам нужно. Кроме перечисленных выше доступны как минимум:
- `meta-llama/llama-4-scout-17b-16e-instruct` — Llama 4 Scout, новая, может оказаться лучше 70B для Classifier;
- `meta-llama/llama-4-maverick-17b-128e-instruct` — Llama 4 Maverick, крупнее Scout;
- `gemma2-9b-it` — лёгкая Gemma от Google (запасная для Splitter, если 8B-instant ляжет);
- `whisper-large-v3-turbo` — быстрее, чуть менее точно, чем `large-v3`.

ChatGPT/OpenAI на Groq не хостится — у Groq только опенсорс/опенвейт. Это нормально: на текущем стеке нам этого хватает с запасом.

В Phase 2 проводим A/B на golden-set из 50 русских фраз (`tests/golden/ru/*.json`), оставляем то, что лучше по точности и стабильности.

Если какой-то из ключей упал/исчерпан — `GroqKeyRouter` пробует другой.

### 2.2. Critic-режим

- `paranoid` — Critic запускается всегда (дороже на ~30%, но надёжнее).
- `confidence` (по умолчанию) — Critic запускается только если Classifier вернул `confidence < 0.7`.
- `off` — Critic выключен (не рекомендуется, оставлено для отладки).
- Хранится в `UserSettings.critic_mode`, переключается тумблером в `/settings`.

### 2.3. Уточняющие вопросы

Если Classifier или Critic не уверены, что имелось в виду («сделать вот эту фигню»):
1. Создать задачу / заметку с тегом `needs_clarification = true`.
2. Бот в ответе **дополнительно** задаёт уточняющий вопрос («что ты имеешь в виду под «фигнёй»?»).
3. Ответ юзера обрабатывается как обновление, а не новый интент.

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
- **LLM** — `llama-3.1-8b-instant`, очень короткий промпт «дай 1 фразу подтверждения в стиле X на русском, ≤8 слов». Логируется в `AiRun` для контроля стоимости.

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
| `inbox_entries` | id, user_id, kind (text/voice), raw_text, transcript, telegram_message_id, received_at |
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
| `DATABASE_URL` | Postgres URL (Neon) |
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
