# Промпт для следующей сессии (Devin / Claude / Codex / любая нейросеть)

> Скопируй ВСЁ ниже (или приложи как файл) при запуске новой
> сессии. Этот промпт самодостаточен: новый агент не должен
> задавать уточняющих вопросов, чтобы начать работу.
>
> Пользователь (Itosyro) **не программист**. Он не умеет мержить,
> пушить, чинить конфликты в git, ревьюить. Всё это делаешь **ты**,
> сам, без вопросов.
>
> Если что-то совсем непонятно — пинг пользователя коротким
> сообщением, но **не** проси его делать технические действия.

---

## ⚡ Главные правила (читай ПЕРВЫМ)

1. **Ты делаешь всё сам**: коммитишь, пушишь, открываешь PR,
   мержишь PR, обновляешь docs. Не проси юзера это делать.
2. **Каждая сессия = отдельный handoff документ**. Перед `stop`/
   `block_on_user=true` ты ОБЯЗАН создать
   `docs/HANDOFF-YYYY-MM-DD-vN.md` (где `vN+1` относительно
   последнего существующего) с описанием того, что делал.
3. **`docs/PROGRESS.md` обновляется** в каждом PR где есть
   значимые изменения. Перед коммитом — добавь запись.
4. **Каждое значимое изменение = отдельный PR.** Не сваливай
   фичу + рефактор + миграцию в один PR.
5. **Каждый PR обязан**: пройти CI (ruff format/check + mypy +
   pytest), иметь тесты на новый код, иметь описание по шаблону.
6. **CI должен быть зелёный перед merge.** Если красный — фиксь.
   Если 3 раза подряд не получается — пингуй пользователя.
7. **Не делай force-push в main.** В свои feature-branch'и —
   `--force-with-lease` ок.
8. **НЕ используй `gh` CLI.** Используй встроенные git tools или
   curl к GitHub REST API.
9. **PAT не даёт `git_pr(action="create")`** работать (G-1 ниже).
   Используй curl. Merge PR — наоборот, через PAT работает.
10. **Не амэндь коммиты, не сквошь чужие, не меняй git config.**

---

## Кто ты и что делаешь

Ты — следующий AI-агент в проекте `Itosyro/plan-app`. Это
**Telegram-бот для планирования и напоминаний на русском**,
работающий на FastAPI + aiogram 3 + Postgres (Neon) + Groq (LLM).

Пользователь говорит/пишет: «купи хлеб завтра в 18:00, через час
позвонить маме». Бот:
1. Принимает (text / voice).
2. Прогоняет через AI пайплайн (Splitter → Classifier → Critic).
3. Создаёт задачи / заметки в БД.
4. Шлёт напоминания.
5. Утром/вечером шлёт дайджест.

**Стек:**
* **Python 3.12** (`.python-version`).
* **uv** — package manager (НЕ pip / poetry).
* **FastAPI** + lifespan для setWebhook.
* **aiogram 3.x** — Telegram bot framework.
* **SQLModel** (поверх SQLAlchemy 2.0 async).
* **Alembic** — миграции.
* **Postgres** (Neon в проде, SQLite in-memory в тестах).
* **Groq** — LLM API (бесплатный, с rotation ключей).
* **structlog** — логи.
* **pytest-asyncio + respx** — тесты.
* **ruff + mypy** — линтер + типы.
* **Render Free** — хостинг (auto-deploy на merge в main).

**Прод:** https://plan-app-t6nx.onrender.com (`/healthz` для проверки).
**Репо:** https://github.com/Itosyro/plan-app

---

## Архитектура (ASCII диаграмма)

```
┌─────────────────────────────────────────────────────────────┐
│                  Telegram (пользователь)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ webhook
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FastAPI lifespan: setWebhook + GroqKeyRouter init           │
│                                                              │
│ POST /tg/<secret>     ──► aiogram Dispatcher                 │
│   (idempotency check)        │                               │
│                              ▼                               │
│                        Routers (factory):                    │
│                          start.py (/start, FSM onboarding)   │
│                          text.py (catch-all text)            │
│                          voice.py (voice → Whisper)          │
│                          today.py (/today)                   │
│                          week.py (/week)                     │
│                          settings.py (/settings, callbacks)  │
│                          digest.py (/digest)                 │
│                              │                               │
│                              ▼                               │
│                        _pipeline.py::run_pipeline:           │
│                          1. Splitter (LLM) → list[Item]      │
│                          2. Classifier (LLM) → category      │
│                          3. Critic (LLM) → improved fields   │
│                          4. resolve_time (dateparser+heur.)  │
│                              │                               │
│                              ▼                               │
│                        services/                             │
│                          users.py | inbox.py | tasks.py      │
│                          settings.py | ai.py                 │
│                              │                               │
│                              ▼                               │
│                         BD (Postgres / SQLite)               │
│                              │                               │
└─────┬───────────────────────────────────────────────────────┘
      │
      │ scheduler (APScheduler in lifespan)
      ▼
   Reminder worker (workers/reminders.py)
   Digest worker (workers/digest.py)
      │
      ▼
   Telegram sendMessage / sendVoice
```

---

## Шаг-за-шагом onboarding (15 минут на чтение, потом работа)

### Шаг 1. Прочитай документы (ВАЖНОЕ → старое)

В таком порядке:

1. **`docs/HANDOFF-YYYY-MM-DD-vN.md`** — последний по дате/версии.
   Это финальный отчёт прошлой сессии: что делалось, что
   осталось, какие PR'ы открыты.
2. `docs/PROGRESS.md` — хронологический лог по PR'ам.
3. `docs/REVIEW-2026-05-09-v2.md` — 14 findings ревью (6 critical
   уже закрыты, 8 important + 9 minor открыты).
4. `docs/HANDOFF-2026-05-09-v3.md` (или старее) — для глубокого
   контекста.
5. `docs/PLAN.md` — продуктовое видение.
6. `docs/ROADMAP.md` — фазы (Phase 0 .. Phase 5).
7. `docs/ARCHITECTURE.md` — как устроены компоненты.

### Шаг 2. Прочитай скиллы

Открой `.agents/skills/CATALOG.md` — там карта.

**Маст-рид перед стартом:**
* `plan-app-internal/SKILL.md` — карта проекта, gotchas, конвенции.
* `obra/using-superpowers/SKILL.md` — как применять остальные.
* `obra/systematic-debugging/SKILL.md` — при ЛЮБОМ баге.
* `obra/verification-before-completion/SKILL.md` — перед "готово".
* `defensive-programming/SKILL.md` — выжимка из mega-review.
* `tg-bot-api/SKILL.md` — актуальное состояние Bot API 10.0.
* `python-best-practices/SKILL.md` — async, типы, FastAPI, SQLAlchemy.

**По задаче:**
* aiogram изменения → `aiogram-3/SKILL.md` + `tg-bot-api/SKILL.md`.
* AI/Groq → `groq-tips/SKILL.md` + `prompt-engineering/SKILL.md`.
* Tests → `testing-async-python/SKILL.md`.
* DB → `migrations-safely/SKILL.md` + `voltagent/postgres-pro.md`.
* PR → `writing-prs/SKILL.md` + `code-review/SKILL.md`.
* Russian NLP → `russian-nlp/SKILL.md`.
* Phase 5 mini-app → `webapp-testing/`, `anthropic/frontend-design/`,
  `anthropic/web-artifacts-builder/`, `voltagent/frontend-developer.md`.

### Шаг 3. Подними окружение

```bash
cd /home/ubuntu/repos
git clone https://github.com/Itosyro/plan-app.git
cd plan-app
uv sync                                      # NB: uv, не pip
cp .env.example .env                         # потом запросишь у юзера секреты, см. ниже
```

### Шаг 4. Прогоны CI локально (ОБЯЗАТЕЛЬНО)

```bash
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
```

Должно быть: format clean, ruff clean, mypy clean, **217+ passed**.

Если красное — **не начинай работу**, сначала пойми почему и
напиши пользователю.

### Шаг 5. Проверь прод живой

```bash
curl -sS https://plan-app-t6nx.onrender.com/healthz
# expect: {"status":"ok"}
```

Если 502/503 → Render Free засыпает (cold-start ~30s, нормально).
Если 5xx после 1 минуты → пиши пользователю.

### Шаг 6. Проверь свежие PR'ы

Используй `git list_repos` или `git view_pr` чтобы посмотреть, что
открыто. Если есть незавершённые PR'ы предыдущей сессии — реши,
продолжать или закрывать.

---

## Что осталось сделать (приоритеты)

### Important findings (открытые, из `REVIEW-2026-05-09-v2.md`)

* **I-1** — некоторые callback handlers всё ещё без try/except
  на `int()`. C-1 закрыл только settings; ищи похожие в
  `_today.py`, `_settings.py` (старые до C-1).
* **I-2** — `get_or_create_*` под нагрузкой ловит race на UNIQUE.
  Нужен `try INSERT / IntegrityError → SELECT` паттерн (как C-5).
* **I-3** — повторный `/start` крашит, потому что
  `get_or_create_user` ожидает первый раз. Идемпотентный flow.
* **I-4** — digest scheduler tick drift: scheduler просыпается
  каждые 60s, но если юзер обновил `morning_digest_at` посреди
  интервала, дайджест может пропуститься на этот день.
  Исправить — двойная проверка `last_morning_digest_on`.
* **I-5** — reminder worker не идемпотентен на crash:
  перезапуск может выслать одно и то же напоминание дважды.
  Решение — `attempt_count` + `idempotency_key`.
* **I-6** — `/today` шлёт N задач = N сообщений. Нужно склеить
  в одно сообщение ≤ 4096 символов.
* **I-8** — нет backpressure на webhook: при пиковой нагрузке
  Telegram retries будут наслаиваться. Добавить semaphore +
  graceful queue.

### Minor findings (тоже открыты)

`docs/REVIEW-2026-05-09-v2.md::Minor` — M-1..M-9. Hygiene-уровень.
Можно делать когда есть свободное время.

### Phase 5 — Mini App (никто не начал)

`docs/PLAN.md` + `docs/ROADMAP.md` описывают Phase 5: Telegram
Mini App (web-страница внутри бота). Стек предполагается React +
shadcn/ui + Tailwind, бэкенд — тот же FastAPI с новыми эндпоинтами.

Полезные скиллы:
* `webapp-testing/` — Playwright тесты.
* `anthropic/frontend-design/` — UI без AI-щаблонности.
* `anthropic/web-artifacts-builder/` — React + shadcn практики.
* `voltagent/frontend-developer.md` + `voltagent/fullstack-developer.md`.

---

## Workflow для каждой задачи

### A. Если просят пофиксить баг

1. Прочитай тикет / репро-шаги пользователя.
2. **Воспроизведи** баг локально (тест который падает, или
   ручное взаимодействие). См. `obra/systematic-debugging/`.
3. Найди root-cause. **НЕ** фикси симптом — найди реальную
   причину.
4. Напиши тест который **падает на main**, **проходит после
   фикса**.
5. Сделай минимальный фикс.
6. Прогон CI локально (ruff format → check → mypy → pytest).
7. Создай ветку `devin/$(date +%s)-кратко-про-баг`.
8. `git add -A && git commit -m "fix: краткое описание

Подробное описание причины и решения. Объясни почему это работает.
Сошлись на тест."`
9. `git push -u origin HEAD`.
10. Открой PR через **curl** (см. ниже).
11. Жди CI. Если красный — фикси.
12. Когда CI зелёный — **смержи сам** через curl PUT (см. ниже).
13. Обнови `docs/PROGRESS.md` в этом же PR (или в следующем).
14. Перед `stop` — обнови `HANDOFF-…-vN.md`.

### B. Если просят добавить фичу

Аналогично, но:
1. Сначала **обсуди дизайн** (см. `obra/brainstorming/`).
2. Опиши план в issue или в комментарии PR в начале работы.
3. Разбей на **несколько маленьких PR'ов** если фича большая.
4. Каждый PR — самостоятельный, проходит CI, закрывает что-то
   осмысленное.

### C. Если просят миграцию БД

1. См. `migrations-safely/SKILL.md`.
2. **Двухстадийный паттерн** для drop column:
   - PR 1: nullable=True, application stops writing.
   - PR 2: drop column.
3. Migration **обязана** быть Postgres-совместимой. SQLite — no-op
   через `if op.get_bind().dialect.name != "postgresql": return`.
4. Прогони `alembic upgrade head` локально (Postgres docker если
   нужно) и `alembic downgrade -1`.

### D. Если просят рефакторинг

1. **НЕ** делай рефакторинг без явного разрешения.
2. Если делаешь — отдельный PR, не смешивай с фичей/багом.
3. Тесты не должны меняться (если не добавляешь новых).
4. Покрытие должно остаться или улучшиться.

---

## Рабочие команды (скопируй и используй)

### Git workflow

```bash
# Старт ветки
git checkout main && git pull --ff-only origin main
git checkout -b "devin/$(date +%s)-описание"

# Коммит и пуш
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
git add -A && git commit -m "тип: краткое

Подробное описание."
git push -u origin HEAD
```

### Создание PR (curl, потому что PAT)

```bash
cat > /tmp/pr.json <<'EOF'
{
  "title": "...",
  "head": "<твоя-ветка>",
  "base": "main",
  "body": "## Summary\n\n...\n\n## Review & Testing Checklist for Human\n\n- [ ] ...\n"
}
EOF
curl -s -X POST -H "Authorization: token ${GITHUB}" \
  -H "Accept: application/vnd.github+json" \
  -d @/tmp/pr.json \
  https://api.github.com/repos/Itosyro/plan-app/pulls | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('html_url') or d)"
```

### Мерж PR (тоже curl)

```bash
# squash merge, чистая history на main
curl -s -X PUT -H "Authorization: token ${GITHUB}" \
  -H "Accept: application/vnd.github+json" \
  -d '{"merge_method":"squash"}' \
  https://api.github.com/repos/Itosyro/plan-app/pulls/<NUM>/merge
```

### Запуск CI / просмотр статуса

* Используй встроенный `git pr_checks` инструмент Devin.
* Или curl: `GET /repos/Itosyro/plan-app/pulls/<NUM>/checks`.

---

## ГРАБЛИ — на которые мы наступали и куда не возвращаемся

> Это самая важная секция. Эти 18 пунктов экономят часы.

### G-1. PAT не даёт `git_pr(action="create")` работать

Сообщение: `"Resource not accessible by personal access token"`.
**Workaround:** curl POST к GitHub REST API (см. выше).

`view_pr`, `pr_checks`, `update`, **merge** — работают штатно
через `git`/`git_pr`/curl. Только `create` — обязательно через curl.

### G-2. Ruff `I001` (import sort) ломает CI после ручных правок

Если добавляешь импорт, есть шанс что ruff отсортирует по-другому.
Поэтому **всегда** перед коммитом:

```bash
uv run ruff format .
uv run ruff check .
```

Если упало — `uv run ruff check . --fix` и снова коммит.

### G-3. SQLAlchemy `MissingGreenlet` после `commit()` в asyncio

```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
```

Происходит когда обращаешься к атрибуту ORM-объекта **после**
`await session.commit()`. SQLAlchemy ставит атрибут в
expired-состояние и триггерит lazy refresh в синхронном контексте.

**Фикс:** `expire_on_commit=False` на sessionmaker. Если
используешь `AsyncSession(engine)` напрямую (как в моём
`tests/test_delete_task_fk.py`), оборачивай в
`async_sessionmaker(engine, expire_on_commit=False)`.

### G-4. SQLite не enforce'ит FK без `PRAGMA foreign_keys = ON`

Если пишешь тест на FK-поведение, обязательно:

```python
async with engine.begin() as conn:
    await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    await conn.run_sync(SQLModel.metadata.create_all)
```

И **используй `StaticPool`**, чтобы PRAGMA не сбросилась на новой
коннекте. Иначе FK-нарушения проходят молча.

### G-5. SQLite не поддерживает `ALTER COLUMN ... DROP DEFAULT`

Тесты обходят это через `SQLModel.metadata.create_all`, не запуская
миграции. Если пишешь Postgres-only миграцию:

```python
def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite path: no-op
    ...
```

См. `alembic/versions/0007_fk_on_delete_policies.py`.

### G-6. `getattr` / `Any` в коде = ругань на ревью

В `mypy`-strict режиме это запрещено конвенцией. Если ты не
знаешь тип, посмотри код. См. `code-review/SKILL.md`.

### G-7. Render Free тушит сервер после 15 минут idle

При первом запросе после паузы будет cold-start ~30 секунд.
Не паникуй. `/healthz` как пинг от UptimeRobot — один из вариантов.

### G-8. structlog без `configure_logging()` = Rich hang

Если ты НЕ вызовешь `configure_logging()` до первого
`logger.exception()`, structlog подцепит дефолтный Rich
`ConsoleRenderer` с `show_locals=True`. Rich пытается отрендерить
httpx/Groq клиенты — вечный hang.

PR #49 это уже починил, но если ты пишешь новый тест-файл,
импортируй и вызывай `configure_logging()` в conftest или в начале
файла.

### G-9. Не запускай несколько `exec` в одном `shell_id` параллельно

Devin shell персистентный. Если два exec в одном shell_id — второй
отменяет первый. Используй разные shell_id для параллельных
команд.

### G-10. Большие `cp -r` репо размером 5+ МБ

`anthropic/canvas-design` это 5.6 МБ шрифтов. Если бандлишь новые
скиллы — проверь размер `du -sh`. Не добавляй больше ~5 МБ к репо
без явной нужды.

### G-11. aiogram не любит, когда один `Router` подключён к двум `Dispatcher`'ам

Это валит тесты. Используй фабрики (`create_router()`), чтобы
каждый вызов делал свежий граф. Шаблон есть в `app/bot/routers/*.py`.

### G-12. `dateparser` PREFER_DATES_FROM=future — ловушка

Дата `в 10:00`, если сейчас 14:00, парсится как **завтра** 10:00, а
НЕ как сегодня 10:00. Если хочешь поведение «остаться на сегодня»
(как для «сегодня в 10:00»), нужно **вручную** проверить explicit
маркер в тексте. См. C-2 fix в `app/ai/time_resolver.py:172-187`.

### G-13. Webhook idempotency — НЕ SELECT-then-INSERT

Это TOCTOU race. Используй атомарный INSERT + `IntegrityError`
catch. См. C-5 fix в `app/bot/services/inbox.py::mark_update_processed`.

### G-14. Telegram callback_data с двоеточиями ломает наивный `split(":")`

Если callback это `"settings:set:morning_digest_at:08:00"`,
`split(":")` даст 5 частей, а ожидалось 4. Используй
`split(":", maxsplit=3)`. См. C-1 fix.

### G-15. Бот «работает» в тестах, но падает в проде

Тесты на SQLite не enforce FK, не enforce locking, не enforce
параллелизм. Если фича касается FK / concurrency / race —
**пиши тест на Postgres** (через testcontainers) или хотя бы
на SQLite с `PRAGMA foreign_keys = ON` + `StaticPool`.

### G-16. Telegram Bot API 10.0 (май 2026) — Guest Mode

Если ловишь странные `update`'ы где `message.from` другой бот —
это новый Bot API 10.0 Guest Mode. Не паникуй, проверь
`update.guest_message`. См. `tg-bot-api/SKILL.md`.

### G-17. uv.lock конфликты при rebase

Если бранч долго живёт и `uv.lock` пересекается — не пытайся
мерджить .lock руками. Сделай `git checkout main -- uv.lock`,
затем `uv lock --upgrade`, посмотри diff, закоммить.

### G-18. Render auto-deploy не запускает миграции для feature-branch'ей

Только main → деплой. Если ты на feature-branch и тебе нужна
миграция в проде — мерж в main первым.

---

## Что **НЕЛЬЗЯ** делать

* ❌ **Просить пользователя мержить.** Делай сам.
* ❌ **Просить пользователя пушить.** Делай сам.
* ❌ **Просить пользователя коммитить.** Делай сам.
* ❌ **Просить пользователя создавать PR.** Делай сам через curl.
* ❌ **Force-push в main.**
* ❌ **`git commit --amend`** на чужих коммитах.
* ❌ **`gh` CLI.**
* ❌ **`pip install`** (используй `uv add`).
* ❌ **Менять тесты чтобы зелёнить** (только если уверен что
  тест был неверным).
* ❌ **Пушить секреты** (API keys, токены, .env).
* ❌ **Коммитить изменения без обновления PROGRESS.md**, если
  изменения значимые.
* ❌ **Завершать сессию без HANDOFF v(N+1)**, если делал работу.

---

## Что **ОБЯЗАТЕЛЬНО** делать

* ✅ **Сам мержить** PR'ы которые ты создал, после CI green.
* ✅ **Обновлять `docs/PROGRESS.md`** в каждом значимом PR.
* ✅ **Создавать `docs/HANDOFF-YYYY-MM-DD-vN.md`** перед
  завершением сессии.
* ✅ **Прогонять полный CI локально** перед каждым commit.
* ✅ **Писать тесты** для каждого нового фикса/фичи.
* ✅ **Использовать русский** в строках/комментариях/доках,
  английский в коде.
* ✅ **Использовать `naive UTC`** через `utcnow_naive()`.
* ✅ **Структурное логирование** через structlog с kwargs.
* ✅ **Скиллы открывать перед задачей**, не во время.

---

## Шаблон HANDOFF документа

Создавай `docs/HANDOFF-YYYY-MM-DD-vN.md` (где `N` — следующий после
последнего). Шаблон:

```markdown
# HANDOFF v<N> — <YYYY-MM-DD>

> Кому: следующей нейросети
> От кого: Devin/Claude/Codex, сессия <session_url>
> Цель: дать всё чтобы возобновить работу за 15 минут

## TL;DR

(2-3 предложения о том что сделано в этой сессии.)

## Текущее состояние main

* HEAD = <hash> (PR #N merged)
* Тесты: <count> passed
* CI зелёный / красный

## PR'ы этой сессии

| # | Тема | Статус |
|---|---|---|
| ... | ... | merged / open / closed |

## Что закрыто

(Каждый закрытый item с кратким резюме: что было сломано, как
починили, тест который теперь падает на main без фикса.)

## Что НЕ закрыто

(Items которые осталось делать.)

## Что НЕ делал (граница ответственности)

* Какие задачи я мог делать но не стал и почему.
* Какие риски я не покрыл.

## Грабли которые наловил в этой сессии

(Если что-то новое — добавь в основной промпт. Если повторил
старые — упомяни как "G-X сработал".)

## Полезные ссылки на код

(file:line ссылки на ключевые места.)
```

---

## Шаблон PR описания

```markdown
## Summary

(1-2 параграфа о том что меняем и зачем.)

(Если фикс бага: ссылка на репро / issue / review-doc.)

## Changes

* Файл X: что изменили и почему.
* Файл Y: что изменили и почему.
* Тесты: какие добавили и что они проверяют.

## Review & Testing Checklist for Human

- [ ] Прочесть код (если интересно — но это уже proven by tests).
- [ ] Подтвердить что фикс соответствует репро в review-doc.
- [ ] Подтвердить что тест бы упал на main без этого фикса.
```

---

## Текущее состояние репо (на 2026-05-09)

* main HEAD: после merge всех PR #50-#59.
* Тесты: 217 passing, ruff/mypy clean.
* Phase 0..4: ✅ полностью.
* Phase 5: 🟡 ещё не начат.
* Critical findings из v2 review: ✅ закрыты (PR #52-#57).
* Important findings: 🟡 открыты (I-1..I-6, I-8). I-7 закрыт с C-3.
* Minor findings: 🟡 открыты.

---

## Если что-то совсем непонятно

1. Прочти `.agents/skills/plan-app-internal/SKILL.md`.
2. Прочти `docs/REVIEW-2026-05-09-v2.md`.
3. Прочти последний `docs/HANDOFF-...-vN.md`.
4. Если совсем неясно — отправь короткое сообщение пользователю
   (`Itosyro`), он знает весь стек.
5. **НЕ** проси его делать технические действия (мерж, push, и т.д.).

---

## Контрольный чек-лист перед первым коммитом

* [ ] Прочитал последний `HANDOFF-...-vN.md`.
* [ ] Прочитал `REVIEW-2026-05-09-v2.md`.
* [ ] Прочитал секцию «Грабли» в этом промпте.
* [ ] Прочитал `obra/using-superpowers/SKILL.md` и
  `obra/systematic-debugging/SKILL.md`.
* [ ] Прочитал `python-best-practices/SKILL.md`.
* [ ] Понял что такое `uv`, `naive UTC`, factory routers.
* [ ] Прогнал `uv run pytest -q` локально — 217+ passed.
* [ ] Создал ветку `devin/<timestamp>-описание`.

## Контрольный чек-лист перед `stop` (концом сессии)

* [ ] Все мои PR'ы либо merged, либо открыты с зелёным CI.
* [ ] `docs/PROGRESS.md` обновлён.
* [ ] Создан `docs/HANDOFF-YYYY-MM-DD-v(N+1).md`.
* [ ] Если наступал на новые грабли — добавил в этот файл.
* [ ] Финальное сообщение пользователю содержит ссылки на PR'ы и
  что merged.

---

Удачи. Делай качественно, не торопись. Это серьёзный продукт,
который реально используется одним человеком (Itosyro) и однажды
выйдет в публичный beta.

— Devin (v6+), 2026-05-09
