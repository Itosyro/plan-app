---
name: python-best-practices
description: Свод лучших практик Python для plan-app — async/await, типы, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, pytest, ruff, mypy. Используй перед написанием/правкой любого нетривиального Python-кода в проекте. Ловит большинство «горячих» граблей которые видят при переходе с Flask/Django на async-FastAPI.
---

# Python Best Practices — для plan-app

> **Стек:** Python 3.12, FastAPI, SQLModel (поверх SQLAlchemy 2.0 async),
> Pydantic v2, aiogram 3, pytest-asyncio, ruff, mypy, uv.

Этот файл **не** теоретический туториал. Это конкретные правила,
которые мы выработали в процессе работы над plan-app, плюс свежий
консенсус из community 2025-2026.

---

## 1. Async / await — как НЕ выстрелить себе в ногу

### Правило 1.1: один движок (engine) на процесс

`AsyncEngine` дорогой объект — создавай **один** в lifespan
FastAPI и переиспользуй. Никогда не создавай в каждом запросе.

```python
# app/db/base.py — правильно
_engine: AsyncEngine | None = None
def init_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, ...)
    return _engine
```

### Правило 1.2: `expire_on_commit=False` для async sessions

После `await session.commit()` SQLAlchemy ставит атрибуты ORM
объектов в **expired** состояние и пытается лениво их перечитать.
В asyncio это вызывает `MissingGreenlet`.

**Фикс:** всегда

```python
async_session = async_sessionmaker(engine, expire_on_commit=False)
```

См. `app/db/base.py::get_sessionmaker`.

### Правило 1.3: НЕ блокируй event loop синхронным IO

Каждое из этого = **смерть** asyncio:
* `requests.get(...)` — используй `httpx.AsyncClient`.
* `time.sleep(N)` — используй `await asyncio.sleep(N)`.
* `psycopg2` без async — используй `asyncpg` (мы используем).
* Чтение больших файлов через `open()` — для крупных используй
  `aiofiles`.
* CPU-bound: `pickle.loads(huge_blob)`, regex по 10 МБ строке —
  выноси в `asyncio.to_thread(...)` или `loop.run_in_executor`.

### Правило 1.4: `asyncio.gather` против последовательных await

Если задачи **независимые** — параллель через `gather`:

```python
# плохо: 3 секунды
user = await get_user(user_id)
settings = await get_settings(user_id)
tasks = await get_tasks(user_id)

# хорошо: max(t1, t2, t3) ≈ 1 секунда
user, settings, tasks = await asyncio.gather(
    get_user(user_id),
    get_settings(user_id),
    get_tasks(user_id),
)
```

### Правило 1.5: `asyncio.create_task` для fire-and-forget

```python
# Веб-хук должен ответить за 60 секунд. AI обработка может занять
# 30+. Решение:
async def webhook_handler(update):
    asyncio.create_task(process_update(update))   # не блокируем
    return {"ok": True}                            # 200 в Telegram
```

**Гочка:** держи ссылку на task в множестве, иначе GC может его
прибить:

```python
_background_tasks: set[asyncio.Task] = set()

task = asyncio.create_task(...)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

### Правило 1.6: НЕ создавай `httpx.AsyncClient` на каждый запрос

```python
# плохо: каждый запрос = новый TCP handshake
async def call_api():
    async with httpx.AsyncClient() as client:
        return await client.get(url)

# хорошо: один клиент на жизнь приложения
class Settings:
    @cached_property
    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0)
```

В нашем коде Groq клиент создаётся один в `app/ai/router.py`.

---

## 2. Типы — НЕ Any, НЕ getattr, НЕ setattr

### Правило 2.1: каждая функция возвращает annotated тип

```python
# плохо
def get_user(uid):
    return ...

# хорошо
async def get_user(uid: int) -> User | None:
    return await session.get(User, uid)
```

### Правило 2.2: НЕ Any

`Any` отключает mypy. Используй конкретный тип, `object`, или
`Protocol`.

### Правило 2.3: НЕ getattr / setattr

Если ты не знаешь имя атрибута — посмотри код и узнай. Если имя
динамическое — используй `dict[str, T]`, не object.

```python
# плохо
status_code = getattr(exc, "status_code", None)

# хорошо
if isinstance(exc, APIStatusError):
    status_code = exc.status_code
```

### Правило 2.4: `T | None` лучше `Optional[T]` (PEP 604)

```python
# плохо
from typing import Optional
def f(x: Optional[int]) -> Optional[str]: ...

# хорошо
def f(x: int | None) -> str | None: ...
```

### Правило 2.5: `Sequence[T]` / `Iterable[T]` / `Mapping[K,V]` лучше `list` / `dict`

В аргументах функций — Sequence, Iterable, Mapping. В возвратах —
конкретный тип (list / dict).

```python
def f(items: Sequence[int]) -> list[int]: ...
```

### Правило 2.6: SQLModel + select() = type-safe

```python
# плохо: result.first() возвращает Any
result = await session.exec(select(User).where(User.id == uid))
user = result.first()

# хорошо: ясно что вернётся
stmt = select(User).where(User.id == uid)
user: User | None = (await session.exec(stmt)).first()
```

---

## 3. Pydantic v2

### Правило 3.1: `BaseSettings` через `pydantic-settings`

(У нас уже сделано в `app/shared/config.py`.)

### Правило 3.2: `model_config` вместо `class Config`

```python
# Pydantic v1 (старо)
class User(BaseModel):
    class Config:
        from_attributes = True

# Pydantic v2 (новый стиль)
class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

### Правило 3.3: `field_validator` вместо `validator`

```python
from pydantic import field_validator

class User(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def trim(cls, v: str) -> str:
        return v.strip()
```

### Правило 3.4: `Field(...)` для required, `Field(default=...)` для optional

```python
from pydantic import Field

class Task(BaseModel):
    title: str                              # required, без Field
    due_at: datetime | None = None          # optional, без Field
    priority: int = Field(default=0, ge=0, le=5)  # с валидацией
```

### Правило 3.5: НЕ Annotated[X, Field()] если не нужно

Если не нужны constraints — обычное `: T`. `Annotated` только
для constraints / dependency injection.

---

## 4. SQLAlchemy 2.0 async — главные паттерны

### Правило 4.1: `select(...)` style, НЕ `query(...)` style

```python
# 1.x style — устарело
session.query(User).filter(User.id == 1).first()

# 2.x style — современный
stmt = select(User).where(User.id == 1)
result = await session.execute(stmt)
user = result.scalar_one_or_none()
```

### Правило 4.2: `selectinload` вместо `joinedload` для async

`joinedload` создаёт гигантский JOIN, который не разбирается в
async-сессии нормально. Используй `selectinload`:

```python
stmt = (
    select(User)
    .where(User.id == uid)
    .options(selectinload(User.tasks))
)
```

### Правило 4.3: Транзакции через `async with session.begin()`

```python
async with session.begin():
    session.add(task)
    session.add(event)
    # commit at end of with-block; rollback on exception
```

### Правило 4.4: `IntegrityError` ловится — обновление race-safe

```python
from sqlalchemy.exc import IntegrityError

try:
    session.add(record)
    await session.flush()
except IntegrityError:
    await session.rollback()
    record = await session.get(Model, key)   # уже создан кем-то
```

См. `app/bot/services/inbox.py::mark_update_processed` — наш
эталон.

### Правило 4.5: НЕ забывай `ON DELETE` policies

SQLite не enforce'ит. Postgres enforce'ит. Если у тебя FK без
`ondelete="CASCADE"` или `"SET NULL"` — `delete` родителя упадёт.

См. `alembic/versions/0007_fk_on_delete_policies.py` для эталона.

---

## 5. Pytest async — наши конвенции

### Правило 5.1: `pytest_asyncio.fixture` + `async def test_X`

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s

async def test_get_user(session: AsyncSession) -> None:
    user = await get_user(session, uid=1)
    assert user is None
```

### Правило 5.2: `pyproject.toml`: `asyncio_mode = "auto"`

(У нас уже стоит.) Не нужно `@pytest.mark.asyncio` на каждый тест.

### Правило 5.3: in-memory SQLite + StaticPool для FK тестов

```python
engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,                    # один connection на life
)
async with engine.begin() as conn:
    await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    await conn.run_sync(SQLModel.metadata.create_all)
```

См. `tests/test_delete_task_fk.py`.

### Правило 5.4: Мокаем HTTP через `respx`

```python
import respx
@respx.mock
async def test_groq_call() -> None:
    respx.post("https://api.groq.com/...").mock(
        return_value=httpx.Response(200, json={...})
    )
    result = await groq_classify(...)
    assert result == ...
```

### Правило 5.5: Мокаем Telegram через aiogram BaseSession

```python
async def fake_send(*args, **kwargs):
    return Message(...)

monkeypatch.setattr(BaseSession, "make_request", fake_send)
```

См. `tests/test_webhook.py`.

### Правило 5.6: НЕ модифицируй test чтобы зелёнить

Если тест падает — фикси код. Тест трогай только если уверен,
что условие в тесте было неверным с самого начала.

---

## 6. Ruff / mypy / форматтер

### Правило 6.1: `ruff format .` перед каждым коммитом

Это автоматический форматтер. Его нельзя «переиграть» — лучше
смириться.

### Правило 6.2: `ruff check .` без --fix перед коммитом

Если ругается — посмотри **что** именно. `I001` (import sort) —
автофиксится через `--fix`. Остальное обычно требует мысли.

### Правило 6.3: `mypy` (strict-ish)

В `pyproject.toml` у нас mypy строгий. Когда падает — это почти
всегда **реальный** баг (None pointer, неверный тип). Не
обходи через `# type: ignore` — почини.

### Правило 6.4: Кириллические RUF001/002/003 — игнорь

Глобально игнорится в `ruff.toml`. Не задавай вопросов, это
постоянные false-positive на «лишних» русских символах.

---

## 7. Зависимости — uv

### Правило 7.1: `uv add <pkg>` чтобы добавить

Не редактируй `pyproject.toml` руками. `uv` сам обновит и
`uv.lock`.

### Правило 7.2: `uv add --dev <pkg>` для dev-зависимостей

Tests, linters, types — в dev. Только то, что нужно в
проде — в основные deps.

### Правило 7.3: `uv sync` ставит из lock

После `git pull` запускай `uv sync`, иначе локальные deps
расходятся с CI.

### Правило 7.4: `uv lock` обновляет lock без install

Если нужно обновить минимальные версии — `uv lock --upgrade`.

### Правило 7.5: Коммитим `uv.lock`

Без него CI может поставить другие версии и упасть. Это
нормальная практика.

---

## 8. Logging — structlog

### Правило 8.1: `configure_logging()` ВСЕГДА в начале

Если не вызовешь — структlog возьмёт Rich по умолчанию,
Rich попытается отрендерить httpx Client / Groq клиенты,
вечный hang. Урок выучен в PR #49.

В тестах — `tests/conftest.py` вызывает `configure_logging()`
в module level.

### Правило 8.2: Структурное логирование, НЕ format strings

```python
# плохо
logger.info(f"User {uid} sent {N} tasks")

# хорошо
logger.info("user_sent_tasks", user_id=uid, count=N)
```

Тогда логи — машиночитаемые JSON, можно агрегировать.

### Правило 8.3: НЕ `print` в продакшн коде

В тестах debug-print ок (но удаляй перед коммитом). В коде —
никогда.

---

## 9. Datetime — naive UTC

### Правило 9.1: `utcnow_naive()` — наш стандарт

```python
from app.shared.time import utcnow_naive
now = utcnow_naive()                     # naive datetime in UTC
```

### Правило 9.2: НЕ `datetime.now()` без tz

`datetime.now()` возвращает локальное время сервера. Render =
UTC, твой ноут — нет. Это вечный источник багов.

### Правило 9.3: Хранение в БД — naive UTC

В Postgres колонка `timestamp without time zone`, в neutral UTC.
Конвертация в локальное время — на frontend / на отправке
сообщений (через `user.timezone`).

### Правило 9.4: Парсинг русского языка — `dateparser`

С нашими настройками (`PREFER_DATES_FROM='future'`,
`RELATIVE_BASE=now`). Гочка — explicit «сегодня в 10:00» в 14:00
парсится как **завтра**, не как «прошло». См. C-2 fix в
`app/ai/time_resolver.py:172-187`.

---

## 10. Безопасность

### Правило 10.1: Секреты — только через env / Settings

* `BOT_TOKEN`, `GROQ_API_KEY*`, `DATABASE_URL`,
  `WEBHOOK_SECRET` — env vars.
* НЕ коммить `.env`. У нас в `.gitignore`.

### Правило 10.2: Webhook double-check

Path `/tg/<secret>` + header `X-Telegram-Bot-Api-Secret-Token`.
Оба должны совпасть.

### Правило 10.3: User input — escape в Markdown/HTML

См. правило 3 в TG-Bot-API skill (G-3).

### Правило 10.4: SQL-injection — НЕ форматируй строки

Используй `select(...)` или параметризацию, не f-strings.

### Правило 10.5: Логирование секретов

```python
# плохо
logger.info("call_groq", api_key=settings.groq_key)

# хорошо
logger.info("call_groq", api_key_id=settings.groq_key[:6] + "...")
```

---

## 11. Производительность

### Правило 11.1: N+1 query — самый частый баг

```python
# плохо — N+1
users = await session.execute(select(User))
for u in users.scalars():
    tasks = await session.execute(select(Task).where(Task.user_id == u.id))

# хорошо — один SELECT с JOIN/IN
users = await session.execute(
    select(User).options(selectinload(User.tasks))
)
```

### Правило 11.2: Composite indexes для частых запросов

Если запрос идёт `WHERE user_id = ? AND created_at > ?` —
у тебя должен быть `Index(user_id, created_at)`, не два
отдельных.

### Правило 11.3: Профайлинг через `cProfile` / py-spy

```bash
uv run py-spy top --pid <pid>
uv run python -m cProfile -o profile.out app/main.py
```

### Правило 11.4: Connection pool

Дефолтный `pool_size=5` мал для прода. У нас:

```python
engine = create_async_engine(
    url, pool_size=20, max_overflow=10, pool_pre_ping=True,
)
```

### Правило 11.5: Кэшируй неизменяемое

`@lru_cache` на функции, которые читают конфиг.
`functools.cached_property` на attribute. Не на coroutine — это
не работает.

---

## 12. CI — что проверять перед PR

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest -q
```

Все четыре зелёные → готов к PR. Один из четырёх красный →
не пуш.

---

## Что почитать когда сомневаешься

* **SQLAlchemy 2.0 async docs:** https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
* **Pydantic v2 migration:** https://docs.pydantic.dev/latest/migration/
* **FastAPI advanced:** https://fastapi.tiangolo.com/advanced/
* **PEP 604 (X | None):** https://peps.python.org/pep-0604/
* **Real Python async crash:** https://realpython.com/async-io-python/
* **dev.to FastAPI+SQLAlchemy 2.0 prod:** https://dev.to/ayush_kaushik_b450595c233/fastapi-sqlalchemy-20-in-production-building-high-performance-async-apis-11ni

## Связанные скиллы

* `defensive-programming/SKILL.md` — гочки которые мы наловили.
* `tg-bot-api/SKILL.md` — Telegram-specific.
* `aiogram-3/SKILL.md` — наш bot framework.
* `groq-tips/SKILL.md` — LLM API.
* `migrations-safely/SKILL.md` — Alembic.
* `testing-async-python/SKILL.md` — наш test setup.
* `voltagent/python-pro.md` — общая Python экспертиза.
* `voltagent/fastapi-developer.md` — FastAPI deep-dive.
