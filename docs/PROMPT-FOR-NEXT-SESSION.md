# Промпт для следующей сессии (Devin / Claude / Codex)

> Скопируй ВСЁ ниже (или приложи как файл) при запуске новой сессии.
> Этот промпт самодостаточен: новый агент не должен задавать
> уточняющих вопросов, чтобы начать работу.

---

## Кто ты и что делаешь

Ты — следующий AI-агент в проекте `Itosyro/plan-app`. Это
Telegram-бот для планирования / напоминаний на русском языке,
работающий на FastAPI + aiogram 3 + Postgres (Neon) + Groq (LLM).
Пользователь говорит/пишет «купи хлеб завтра в 18:00» — бот
классифицирует, ставит напоминание, утром/вечером шлёт дайджест.

Прод: https://plan-app-t6nx.onrender.com (Render Free + Neon)
Репо: https://github.com/Itosyro/plan-app
Активный деплой: автоматический по merge в `main`.

Ты НЕ обязан делать всё подряд. Прочитай `docs/HANDOFF-2026-05-09-v5.md`
(финальный handoff предыдущей сессии) и реши, какие задачи брать.
Пользователь всегда может уточнить приоритеты.

---

## С чего начать (15-минутный onboarding)

### Шаг 1. Понять, в каком состоянии репо

```bash
cd /home/ubuntu/repos
git clone https://github.com/Itosyro/plan-app.git
cd plan-app
git log --oneline -20
gh pr list --state all --limit 30   # или используй встроенный git-инструмент
```

### Шаг 2. Прочитать handoff'ы в порядке от нового к старому

1. `docs/HANDOFF-2026-05-09-v5.md` — что было сделано в last session,
   что закрыто, что открыто, какие PR'ы ждут merge.
2. `docs/HANDOFF-2026-05-09-v3.md` — предыдущая сессия (22 findings).
3. `docs/HANDOFF-2026-05-09-v2.md` / `v1` (он же `HANDOFF-2026-05-09.md`)
   — самая первая сессия с onboarding.
4. `docs/HANDOFF.md` — вечный handoff верхнего уровня (если есть).

### Шаг 3. Прочитать архитектурные документы

* `docs/ARCHITECTURE.md` — как устроены компоненты.
* `docs/ROADMAP.md` — фазы (Phase 0..5), что в каждой.
* `docs/PLAN.md` — продуктовое видение.
* `docs/PROGRESS.md` — хронологический лог по PR'ам.

### Шаг 4. Прочитать ревью

* `docs/REVIEW-2026-05-09.md` (v1) — 22 findings, все закрыты.
* `docs/REVIEW-2026-05-09-v2.md` — 14 findings:
  6 critical (закрыты в last session, PR'ы #52-#57),
  7 important + 9 minor (открыты, ждут тебя).

### Шаг 5. Поднять локальное окружение

```bash
uv sync                                  # NB: uv, НЕ pip/poetry
cp .env.example .env                     # заполни TELEGRAM_BOT_TOKEN, GROQ_API_KEY, DATABASE_URL
uv run ruff format . && uv run ruff check .
uv run mypy
uv run pytest -q                         # должно быть ≥ 207 passed
```

Если хочешь поднять бот локально (без webhook'а — long polling):

```bash
uv run python -m app.workers.poll        # если этого скрипта нет — придётся потратить 5 минут на его написание
```

Или прямо webhook через ngrok:

```bash
ngrok http 8000
WEBHOOK_BASE_URL=https://xxx.ngrok.io uv run uvicorn app.main:app --reload
```

### Шаг 6. Прочитать карту скиллов

`.agents/skills/CATALOG.md` — список всех методичек (24+ файлов).
Самые важные перед стартом:

* `plan-app-internal/SKILL.md` — карта проекта, gotchas, конвенции.
* `obra/using-superpowers/SKILL.md` — как находить и применять остальные скиллы.
* `obra/systematic-debugging/SKILL.md` — при любом баге.
* `obra/verification-before-completion/SKILL.md` — перед «готово».
* `defensive-programming/SKILL.md` — выжимка из mega-review.
* `code-review/SKILL.md` — чек-лист на 30 пунктов перед approve.

---

## Стек и конвенции (компактно)

* **Python 3.12** (см. `.python-version`)
* **Package manager: `uv`** (НЕ pip, НЕ poetry, НЕ conda).
  `uv sync`, `uv add`, `uv run`. `uv.lock` коммитим.
* **DB:** Postgres в проде (Neon), in-memory SQLite в тестах.
  ORM: SQLModel + SQLAlchemy 2.x async. Миграции: Alembic.
* **Bot:** aiogram 3.x. `Router` — фабрика (`create_router()`),
  иначе тесты падают (один Router в двух Dispatcher'ах = ошибка).
* **LLM:** Groq (бесплатные ключи с rotation). `app/ai/router.py`
  делает round-robin + 429-retry. Используем
  `instructor` для structured output. См. `groq-tips/SKILL.md`.
* **Web:** FastAPI с lifespan для setWebhook. Healthcheck `/healthz`.
* **Логи:** structlog (НЕ дефолтный Rich, иначе hang в тестах —
  см. PR #49 / M-4).
* **Время:** в БД храним **naive UTC** (`utcnow_naive()`). Никогда
  не пиши `datetime.now()` без tz.
* **Тесты:** pytest-asyncio (`asyncio: auto`), respx для HTTP моков
  (Groq), aiogram `BaseSession.make_request` мок для Telegram.
* **CI:** GitHub Actions, единственный job `ruff + pytest` (ruff
  format --check, ruff check, mypy, pytest). См. `.github/workflows/`.
* **Style:** русский язык в строках/комментариях/доках; код по-английски.

---

## Что осталось сделать (приоритеты)

### Критично (необязательно, но желательно)

1. **Смержить PR #52-#57** в порядке: 52 → 53 → 54 → 55 → 56 → 57.
   После каждого Render задеплоит автоматически, проверь
   `/healthz`. После всех 6 — миграция 0007 на проде поправит FK.
2. **Смержить docs PR'ы** #50, #51, #58 (в любом порядке).

### Important findings (открытые, из v2 review)

См. `docs/REVIEW-2026-05-09-v2.md::Important`. Кратко:

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
* **I-6** — `/today` шлёт N задач = N сообщений. Нужно
  склеить в одно сообщение ≤ 4096 символов (Telegram лимит).
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

Полезные скиллы для Phase 5:
* `webapp-testing/` — Playwright тесты.
* `anthropic/frontend-design/` — UI без AI-щаблонности.
* `anthropic/web-artifacts-builder/` — React + shadcn практики.

---

## Грабли, на которые я (Devin v5) уже наступил

**Читай это перед тем, как начнёшь — экономит часы.**

### G-1. PAT не может создавать PR'ы через `git_pr(action="create")`

Сообщение: `"Resource not accessible by personal access token"`.
**Workaround:** `curl POST` к GitHub REST API:

```bash
curl -s -X POST -H "Authorization: token ${GITHUB}" \
  -H "Accept: application/vnd.github+json" \
  -d '{"title":"...","head":"branch","base":"main","body":"..."}' \
  https://api.github.com/repos/Itosyro/plan-app/pulls
```

`view_pr`, `pr_checks`, `update` — работают штатно через `git`/`git_pr`.
Только `create` — через curl.

### G-2. Ruff `I001` (import sort) ломает CI после ручных правок

Если добавляешь импорт из `app.bot.services` где-то в test-файл,
есть шанс, что ruff отсортирует по-другому. **Всегда** перед
коммитом запускай:

```bash
uv run ruff format .
uv run ruff check .
```

В моём случае PR #54 упал в CI на этом, пришлось делать второй
коммит «ruff import sort fix».

### G-3. SQLAlchemy `MissingGreenlet` после `commit()` в asyncio

```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called
```

Происходит когда обращаешься к атрибуту ORM-объекта **после** `await
session.commit()`. SQLAlchemy ставит атрибут в expired-состояние и
триггерит lazy refresh в синхронном контексте.

**Фикс:** `expire_on_commit=False` на sessionmaker. Если используешь
`AsyncSession(engine)` напрямую (как в моём `tests/test_delete_task_fk.py`),
оборачивай в `async_sessionmaker(engine, expire_on_commit=False)`.

### G-4. SQLite не enforce'ит FK без `PRAGMA foreign_keys = ON`

Это ВНИМАНИЕ. Если пишешь тест на FK-поведение, обязательно:

```python
async with engine.begin() as conn:
    await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    await conn.run_sync(SQLModel.metadata.create_all)
```

И **используй `StaticPool`**, чтобы PRAGMA не сбросилась на новой
коннекте. Иначе FK-нарушения проходят молча, и ты пропустишь баг
вроде C-3 (delete_task FK violation на Postgres).

### G-5. SQLite не поддерживает `ALTER COLUMN ... DROP DEFAULT`

Старые миграции (например, `0004_courier_template_style.py`)
содержат Postgres-only ALTER, который ломает alembic upgrade на
SQLite. Это **известная** проблема, тесты обходят её через
`SQLModel.metadata.create_all`, не запуская миграции. Если
ты пишешь новую Postgres-only миграцию, добавляй защиту:

```python
def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite path: no-op
    ...
```

См. `alembic/versions/0007_fk_on_delete_policies.py` как пример.

### G-6. `getattr` / `Any` в коде = моментальный ругань на ревью

В `mypy --strict`-режиме этого нет, но конвенция проекта запрещает
`getattr`, `setattr`, `Any` для доступа к атрибутам. Если ты не
знаешь тип, посмотри код. См. `code-review/SKILL.md`.

Я лично попался на этом в одном из старых PR'ов — заменили на прямой
доступ к атрибуту. Не делай так.

### G-7. Render Free тушит сервер после 15 минут idle

При первом запросе после паузы будет cold-start ~30 секунд. Не
паникуй и не считай это багом. `/healthz` как пинг от UptimeRobot —
один из вариантов поддерживать сервер тёплым.

### G-8. Структурное логирование структlog + Rich = hang

Если ты НЕ вызовешь `configure_logging()` до первого `logger.exception()`,
structlog подцепит дефолтный Rich `ConsoleRenderer` с
`show_locals=True`. Rich пытается отрендерить httpx/Groq клиенты —
вечный hang. PR #49 это уже починил, но если ты пишешь новый
тест-файл, импортируй и вызывай `configure_logging()` в conftest
или в начале файла.

### G-9. Шеллы в Devin: shell_id персистентный, не запускай commands в parallel в одном shell

Если параллелишь `uv run pytest` и `uv run mypy`, дай им разные
`shell_id`, иначе один отменит другой. И не кэшируй output между
вызовами одного шелла без причины.

### G-10. Большие `cp -r` репо размером 5+ МБ

`anthropic/canvas-design` это 5.6 МБ шрифтов. Если будешь
бандлить новые скиллы — проверь размер `du -sh`. Не добавляй больше
~5 МБ суммарно к репо без явной нужды.

### G-11. aiogram не любит, когда один `Router` подключён к двум `Dispatcher`'ам

Это валит тесты. Используй фабрики (`create_router()`), чтобы каждый
вызов делал свежий граф. Шаблон есть в `app/bot/routers/*.py`.

### G-12. `dateparser` PREFER_DATES_FROM=future — ловушка

Дата `в 10:00`, если сейчас 14:00, парсится как **завтра** 10:00, а
НЕ как сегодня 10:00. Если хочешь поведение «остаться на сегодня»
(как для «сегодня в 10:00»), нужно **вручную** проверить explicit
маркер в тексте. См. C-2 fix в `app/ai/time_resolver.py:172-187`.

### G-13. Webhook idempotency — НЕ SELECT-then-INSERT

Это TOCTOU race. Используй атомарный INSERT + `IntegrityError`
catch. См. C-5 fix в `app/bot/services/inbox.py::mark_update_processed`.

### G-14. Telegram callback_data с двоеточиями ломает наивный `split(":")`

Если callback это `"settings:set:morning_digest_at:08:00"`, `split(":")`
даст 5 частей, а ожидалось 4. Используй `split(":", maxsplit=3)`.
См. C-1 fix.

### G-15. Бот может выглядеть «работающим» в тестах, но падать в проде

Тесты на SQLite не enforce FK, не enforce locking, не enforce
параллелизм. Если фича касается FK / concurrency / race —
**пиши тест на Postgres** (через `pytest-postgres` или docker
container) или хотя бы на SQLite с `PRAGMA foreign_keys = ON` +
`StaticPool`.

---

## Команды-шпаргалки

```bash
# Полный CI локально
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q

# Создать миграцию
uv run alembic revision --autogenerate -m "что меняем"
# Откорректировать руками, проверить:
DATABASE_URL=postgresql://... uv run alembic upgrade head

# Создать ветку (по конвенции)
git checkout -b "devin/$(date +%s)-короткое-описание"

# Push с upstream
git push -u origin HEAD

# Создать PR
curl -s -X POST -H "Authorization: token ${GITHUB}" \
  -H "Accept: application/vnd.github+json" \
  -d '{"title":"...","head":"<твоя-ветка>","base":"main","body":"..."}' \
  https://api.github.com/repos/Itosyro/plan-app/pulls

# Посмотреть статус CI
# (используй builtin git tool, action=pr_checks)
```

---

## Чем НЕ заниматься (явные границы)

* **Не мерджи самостоятельно**, пока пользователь не дал явного
  разрешения. Создавай PR'ы и жди review.
* **Не делай force-push в main.** Только в свои feature-branch'и
  с `--force-with-lease`.
* **Не используй `gh` CLI.** Используй встроенные git-инструменты
  Devin или curl к GitHub REST API.
* **Не модифицируй тесты, чтобы их зелёнить.** Если тест падает —
  значит баг в коде или тест неправильный (тогда опиши почему).
* **Не пиши в `Any`, `getattr`, `setattr`.** Узнай тип, используй прямой
  доступ.
* **Не коммить секреты** (API keys, токены, .env). Используй
  `os.environ` + Settings.
* **Не запускай боевые миграции на проде сам.** Render делает это
  при деплое. Если тебе нужно прогнать миграцию вручную — спроси.

---

## Если что-то непонятно

1. Прочти `.agents/skills/plan-app-internal/SKILL.md` — там
   ответы на 80% вопросов про архитектуру.
2. Прочти `docs/REVIEW-2026-05-09-v2.md` — там repro у каждого
   важного бага.
3. Прочти `docs/HANDOFF-2026-05-09-v5.md` — финальный handoff
   с PR-карточками и статусом CI.
4. Если совсем неясно — пингуй Itosyro (пользователь),
   он знает весь стек.

---

## Контрольный чек-лист перед первым коммитом

* [ ] Прочитал `HANDOFF-2026-05-09-v5.md`.
* [ ] Прочитал `REVIEW-2026-05-09-v2.md`.
* [ ] Понял что такое `uv` и не пытаешься использовать `pip`.
* [ ] Понял что такое `naive UTC` и используешь `utcnow_naive()`.
* [ ] Прогнал `uv run pytest -q` локально — 207+ passed.
* [ ] Создал ветку `devin/<timestamp>-описание`.
* [ ] Прочитал секцию «Грабли» в этом промпте.
* [ ] Прочитал `obra/using-superpowers/SKILL.md` и
  `obra/systematic-debugging/SKILL.md`.

Удачи. Не торопись, делай качественно. Pop quizzes ради pop
quizzes тут не нужны — это серьёзный продукт, который реально
используется одним человеком (Itosyro) и шансами выйти в публичный
beta-доступ.

— Devin (v5), 2026-05-09 14:30 UTC
