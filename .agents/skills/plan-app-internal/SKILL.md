---
name: plan-app-internal
description: Внутренний справочник по проекту plan-app — как устроено, где что лежит, частые ошибки. Читать в первую очередь, до правок кода. Это карта проекта для AI-агента.
---

# plan-app — внутренний справочник

Если ты — AI-агент, открывший этот репо в первый раз, **прочти этот файл и `docs/`**. Дальше станет легче.

---

## 1. О чём проект

Telegram-бот **«ассистент-плановщик»**. Юзер скидывает голосовухой / текстом «поток мысли» — бот раскладывает на задачи / заметки / напоминания. С AI-обогащением: горизонты («сегодня», «неделя», «когда-нибудь»), категории (свои у каждого юзера), тон ответов («тыкающий», «формальный»), напоминания.

Ключевая особенность: **многоступенчатая AI-обработка** через Groq:
1. **Splitter** (`llama-3.1-8b-instant`) — разбить поток мысли на интенты
2. **Classifier** (`llama-3.3-70b-versatile`) — присвоить каждому интенту категорию + горизонт
3. **Critic** (`qwen-qwq-32b`) — пересмотреть результат, поправить (опционально по уверенности)

Юзер один (сам автор + друзья на пробу), но архитектура должна выдержать ~100.

---

## 2. Карта репозитория

```
plan-app/
├── app/
│   ├── bot/         — aiogram 3 хендлеры (telegram-side)
│   ├── api/         — FastAPI endpoints (mini-app, webhooks)
│   ├── ai/          — LLM-пайплайн (Splitter / Classifier / Critic / Courier)
│   ├── db/          — SQLModel модели + миграции
│   ├── workers/     — фоновые задачи (cron, scheduler)
│   ├── shared/      — общие утилиты, config, типы
│   └── main.py      — FastAPI app + lifespan + подключение всего
├── tests/           — pytest, async-фикстуры, моки Groq
├── alembic/         — миграции БД
├── docs/            — мегаподробное планирование (читай первым!)
├── memory/          — сырые потоки мысли юзера (для DSPy в будущем)
├── .agents/skills/  — этот каталог методичек
├── pyproject.toml   — uv + ruff + deps
├── ruff.toml        — конфиг линтера/форматтера
├── Dockerfile       — для Render-деплоя
├── render.yaml      — конфиг сервисов Render
└── README.md        — короткое описание для GitHub
```

---

## 3. Где что искать (быстрый индекс)

| Хочу понять… | Смотри… |
|---|---|
| Какие фичи планируются | `docs/PLAN.md` + `docs/ROADMAP.md` |
| Архитектуру (схемы, БД, AI-пайплайн) | `docs/ARCHITECTURE.md` |
| Что уже сделано | `docs/PROGRESS.md` |
| Будущие идеи | `docs/IDEAS.md` |
| Какую модель Groq использовать | `.agents/skills/groq-tips/SKILL.md` |
| Как написать промпт | `.agents/skills/prompt-engineering/SKILL.md` |
| Парсинг русского («через 43 мин») | `.agents/skills/russian-nlp/SKILL.md` |
| Паттерны aiogram 3 | `.agents/skills/aiogram-3/SKILL.md` |
| Как ревьюить PR | `.agents/skills/code-review/SKILL.md` |
| Как описать PR | `.agents/skills/writing-prs/SKILL.md` |

---

## 4. Code style — что важно знать

- **Docstrings — на английском** (industry standard)
- **Комментарии — на русском** для сложных мест (объясняем «почему», не «что»)
- **Никаких `Any` / `getattr` / `setattr`** для обхода типизации — это «ленивый путь», бьёт по поддержке
- **Никакого `print()`** в проде — только `logger`
- **Импорты — наверху файла**, не внутри функций
- **Никаких inline-промптов** — только в `app/ai/prompts/<name>.md`

Подробнее — `docs/ARCHITECTURE.md` §6 (Code style).

---

## 5. Команды разработки

```bash
# Установка
uv sync

# Линтер + форматтер
uv run ruff format .
uv run ruff check .

# Тесты
uv run pytest -q

# Локальный запуск (dev)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Миграция (при правке моделей)
uv run alembic revision --autogenerate -m "what changed"
uv run alembic upgrade head
```

---

## 6. Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.12 |
| Bot | aiogram 3 (async) |
| HTTP | FastAPI |
| DB | Postgres (Neon free) + SQLModel + Alembic |
| LLM | Groq (Llama / Qwen / Whisper) + instructor |
| NLP | dateparser, pymorphy3, razdel |
| Линтер | ruff |
| Тесты | pytest + pytest-asyncio + respx |
| Деплой | Render Free (web + cron) |
| Контейнер | Docker (multi-stage) |

---

## 7. Окружение / секреты

В `.env` (локально) и Render ENV (прод):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...     # любая случайная строка
PUBLIC_URL=https://plan-app.onrender.com

GROQ_API_KEY_1=...              # для Splitter
GROQ_API_KEY_2=...              # для Classifier
GROQ_API_KEY_3=...              # для Critic + Whisper

DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

Полный список — `.env.example` в корне.

---

## 8. AI-пайплайн в одном месте

Когда юзер пишет / голос → Telegram → webhook FastAPI → aiogram dispatcher → handler:

```
1. handler сохраняет raw text в InboxEntry
2. handler ставит задачу `process_inbox(entry_id)` в фон
3. process_inbox:
   a. razdel.sentenize → [sent1, sent2, …]
   b. Splitter (llama-8b) → [intent1, intent2, …]
   c. для каждого intent:
      - dateparser → время (если есть)
      - Classifier (llama-70b) → category, horizon, priority
      - if confidence < 0.7 OR critic_mode == "paranoid":
          Critic (qwen-qwq-32b) → ревизия
      - сохранить Task / Note / Reminder в БД
   d. Courier выбирает ответ юзеру (template или LLM, 50/50)
   e. бот отвечает
4. cron worker раз в минуту сканирует Reminder → шлёт в нужный момент
```

Подробнее — `docs/ARCHITECTURE.md` §2-3.

---

## 9. Frequently encountered «gotchas»

1. **Webhook 200 за < 1 сек** — иначе Telegram повторит. Тяжёлую работу — в очередь (Phase 4: Redis/RQ).
2. **Voice ≤ 20 МБ** — Telegram limit, обработать (предупредить юзера).
3. **Структурный output** — только через `instructor` + Pydantic, не regex.
4. **Все LLM-вызовы async** — никогда `requests.post`, всегда `httpx.AsyncClient` или groq-sdk async-методы.
5. **TZ юзера, не сервера** — везде `datetime` хранить в UTC, конвертировать в TZ юзера на выводе.
6. **`drop_pending_updates=True`** при `set_webhook` — иначе после деплоя бот раскопает 1000 старых.
7. **callback_data ≤ 64 байта** — короткий формат `domain:action:id`, не JSON.
8. **`uv.lock` — коммитим**, для воспроизводимости в CI / Docker.

---

## 10. Что **не** делать

- ❌ Дёргать Groq API из CI / тестов — только моки
- ❌ Хранить promo / inline-промпты в коде — отдельный файл в `app/ai/prompts/`
- ❌ Делать большие PR (> 600 LOC) — режь
- ❌ Использовать polling — только webhook
- ❌ Логировать `message.text` (PII)
- ❌ Force-push в main / master
- ❌ `git add .` — только конкретные пути

---

## 11. Merge-workflow (важно для будущих AI-сессий)

Юзер (Itosyro / Юсуф) — не разработчик и **не мерджит PR'ы сам**. Полный цикл (открыть → починить CI → squash-merge) **делает AI-агент**.

Стандартная последовательность:

1. Перед запросом ревью: `uv run ruff format .` + `uv run ruff check .` + `uv run pytest -q` — всё зелёное.
2. Создать PR (см. §12 ниже про tooling), отправить ссылку юзеру в чат.
3. Дождаться его словесного «ок / мерджи / давай дальше».
4. Squash-merge через REST API.
5. `git checkout main && git pull --ff-only`, новая ветка `devin/$(date +%s)-<slug>` для следующей задачи.

**Никогда не**:
- `force-push` в `main` / `master`
- мерджить, если CI красный или юзер не дал явного одобрения
- мерджить через rebase/merge — только squash (один коммит на фазу)

---

## 12. PR tooling — особенности этого репо

Встроенные `git_create_pr` / `git_update_pr_description` Devin'а **сейчас не работают** для `Itosyro/plan-app` (PAT инструмента не имеет write-доступа к этому репо). Используем GitHub REST API через user-provided fine-grained PAT.

```bash
# PAT хранится в env как GITHUB_PLAN_APP_PAT
# scope: Contents R/W + Pull Requests R/W на plan-app

# push (без credential helper, чтобы не дёргать прокси)
git -c credential.helper= push \
  "https://x-access-token:${GITHUB_PLAN_APP_PAT}@github.com/Itosyro/plan-app.git" \
  "$BRANCH"

# create PR
curl -s -X POST \
  -H "Authorization: Bearer ${GITHUB_PLAN_APP_PAT}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/Itosyro/plan-app/pulls \
  -d '{"title":"...","head":"'"$BRANCH"'","base":"main","body":"..."}'

# update PR body
curl -s -X PATCH \
  -H "Authorization: Bearer ${GITHUB_PLAN_APP_PAT}" \
  https://api.github.com/repos/Itosyro/plan-app/pulls/<num> \
  -d '{"body":"..."}'

# squash merge
curl -s -X PUT \
  -H "Authorization: Bearer ${GITHUB_PLAN_APP_PAT}" \
  https://api.github.com/repos/Itosyro/plan-app/pulls/<num>/merge \
  -d '{"merge_method":"squash"}'
```

Никогда не вписывай PAT в `.git/config` (вычисти, если протёк). PAT короткоживущий — если 401, попроси юзера через `request_secret` (в чат не присылать).

---

## 13. Live deploy (Render)

Прод живёт в Render Free, Frankfurt:

| Поле | Значение |
|---|---|
| Service ID | `srv-d7uohcf7f7vs73crmk3g` |
| Service slug | `plan-app-t6nx` |
| Public URL | `https://plan-app-t6nx.onrender.com` |
| Webhook path | `/tg/<TELEGRAM_WEBHOOK_SECRET>` |
| Health check | `GET /healthz` → `{"status":"ok"}` |
| Workspace (ownerId) | `tea-d7tr6vugvqtc73bsjka0` (Cile Simme's workspace) |
| Dashboard | `https://dashboard.render.com/web/srv-d7uohcf7f7vs73crmk3g` |
| Auto-deploy | `commit` (push to `main` → redeploy) |
| Build / Start | `uv sync --frozen` / `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Cold-start | ~3 мин (free-tier sleeps after 15 min idle) |

Render API через `RENDER_API_KEY` (юзер выдаёт через `request_secret`, не в чат):

```bash
SVC=srv-d7uohcf7f7vs73crmk3g

# Health
curl https://plan-app-t6nx.onrender.com/healthz

# Latest deploys
curl -s -H "Authorization: Bearer ${RENDER_API_KEY}" \
  "https://api.render.com/v1/services/${SVC}/deploys?limit=3" | jq

# Trigger redeploy (e.g. after env-var change)
curl -s -X POST -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  "https://api.render.com/v1/services/${SVC}/deploys" \
  -d '{"clearCache":"do_not_clear"}'

# Update single env var (auto-redeploys)
curl -s -X PUT -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  "https://api.render.com/v1/services/${SVC}/env-vars/<KEY>" \
  -d '{"value":"<VALUE>"}'

# List env vars (values masked for SDK secrets in dashboard, not API)
curl -s -H "Authorization: Bearer ${RENDER_API_KEY}" \
  "https://api.render.com/v1/services/${SVC}/env-vars?limit=20" | jq

# Logs (Render API)
curl -s -H "Authorization: Bearer ${RENDER_API_KEY}" \
  "https://api.render.com/v1/logs?ownerId=tea-d7tr6vugvqtc73bsjka0&resource=${SVC}&limit=100" | jq
```

**Подводные камни:**
- `WEBHOOK_BASE_URL` должен быть выставлен **до** запуска сервиса, иначе lifespan не зарегистрирует webhook (`if bot is not None and settings.webhook_url:`). При первом создании сервиса URL ещё неизвестен — выставляем `WEBHOOK_BASE_URL` после `POST /v1/services` и триггерим явный redeploy.
- Free plan не имеет `preDeployCommand` → миграции Alembic накатываются вручную (`uv run alembic upgrade head`) с локальной машины против Neon перед каждым релизом, который меняет схему. Альтернатива на потом — апгрейд до Starter-плана и `preDeployCommand: uv run alembic upgrade head`.
- Free-tier после 15 мин простоя засыпает — первый webhook после паузы прилетает на холодный старт (~3 мин), Telegram ретраит до 24 ч. Это известная особенность free, не баг.
- Workspace, к которому привязан текущий `RENDER_API_KEY` — `tea-d7tr6vugvqtc73bsjka0` («Cile Simme's workspace», email `city.cile.simme@gmail.com`). Это **не** основной email юзера. Если нужен переход в другой workspace — отдельный шаг (delete service + recreate).

---

## 14. Кто может помочь

- AI-агенту: читай этот файл + `docs/` + `.agents/skills/`. Если непонятно — спроси юзера комментарием в PR.
- Юзеру: читай `docs/PROGRESS.md` чтобы видеть прогресс. Если что-то сломалось — открой issue с шагами повтора.

---

## 15. Где жить идеям и заметкам

- **Идея на потом** → `docs/IDEAS.md` (а не TODO в коде)
- **Сделанное** → `docs/PROGRESS.md`
- **Сырые потоки мысли юзера для DSPy / эвалов** → `memory/<date>.md`
- **Best practices, методички** → `.agents/skills/<topic>/SKILL.md` (этот каталог)
