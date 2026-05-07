---
name: aiogram-3
description: Паттерны работы с aiogram 3 в plan-app. Покрывает webhook setup, dispatcher / routers, FSM, обработку voice / text, inline-клавиатуры. Используй при правке любого кода в app/bot/.
---

# aiogram 3 — паттерны для plan-app

aiogram 3 — это **переход с класса-бота на functional dispatcher + routers**. Если ты гуглишь и видишь aiogram 2 (`@dp.message_handler(...)`) — это устарело. Мы на 3.

---

## 1. Webhook (НЕ polling)

### Setup в `app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update

bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
# регистрация роутеров
dp.include_router(start_router)
dp.include_router(text_router)
dp.include_router(voice_router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # set webhook on startup
    await bot.set_webhook(
        url=f"{settings.public_url}/webhook/telegram",
        secret_token=settings.webhook_secret,
        drop_pending_updates=True,
    )
    yield
    # don't delete webhook on shutdown (Render redeploys constantly)

app = FastAPI(lifespan=lifespan)

@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
):
    if x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(403)
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}
```

### Грабли

- **Всегда** проверять `secret_token` — иначе любой может слать тебе фейковые updates
- **`drop_pending_updates=True`** при старте — иначе после деплоя бот обработает 1000 старых сообщений
- **Не использовать `dp.start_polling()`** на проде — Render-сервис типа `web` это зарубит

---

## 2. Dispatcher и routers

Делим хендлеры по доменам:

```
app/bot/routers/
├── __init__.py
├── start.py        — /start, /help, onboarding
├── text.py         — обычный текст (поток мысли)
├── voice.py        — голосовые
├── settings.py     — настройки (категории, горизонты, дайджест)
└── reminders.py    — inline-кнопки на напоминаниях
```

Каждый файл:

```python
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router(name="start")

@router.message(Command("start"))
async def cmd_start(message: Message):
    ...
```

Регистрация в `app/bot/__init__.py`:

```python
from .routers import start, text, voice, settings, reminders

def register_all(dp: Dispatcher):
    dp.include_router(start.router)
    dp.include_router(settings.router)  # перед text, иначе перехватит
    dp.include_router(reminders.router)
    dp.include_router(voice.router)
    dp.include_router(text.router)      # catch-all в конце
```

**ВАЖНО:** порядок регистрации = приоритет. Catch-all (`text`) — последним.

---

## 3. FSM (для onboarding-визарда)

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class Onboarding(StatesGroup):
    name = State()
    timezone = State()
    digest_time = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(Onboarding.name)
    await message.answer("Как тебя зовут?")

@router.message(Onboarding.name)
async def onb_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(Onboarding.timezone)
    await message.answer("Какой у тебя часовой пояс? (например, Europe/Moscow)")
```

### FSM storage
- **dev:** `MemoryStorage()` — потеряется при рестарте
- **prod:** `RedisStorage` или **PostgreSQLStorage** (свой). На Phase 1 пойдёт MemoryStorage, в Phase 4 переключимся.

---

## 4. Voice handling

```python
from aiogram import F

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    # → передать в Whisper (см. .agents/skills/groq-tips/SKILL.md)
    text = await transcribe(file_bytes)
    await process_thought_stream(message.from_user.id, text)
```

### Лимиты
- voice ≤ 20 МБ (лимит Telegram bot API)
- voice длиннее 60 сек — предупредить юзера, разбить на куски

---

## 5. Inline-клавиатуры

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✓ Сделано", callback_data=f"task:done:{task_id}")],
    [InlineKeyboardButton(text="↻ Перенести", callback_data=f"task:reschedule:{task_id}")],
])
await message.answer("Пробежка через 30 мин", reply_markup=kb)

@router.callback_query(F.data.startswith("task:done:"))
async def cb_task_done(cb: CallbackQuery):
    task_id = cb.data.split(":")[2]
    ...
    await cb.answer("Записал ✓")  # обязательно — иначе у юзера часики
```

### Грабли
- `callback_data` ≤ 64 байта (Telegram limit). Не пихать туда длинный JSON — короткий формат `domain:action:id`.
- **Всегда** вызвать `cb.answer()` (хотя бы пустой) — иначе на кнопке часики 30 сек.

---

## 6. Длинные сообщения

Telegram режет на 4096. Разбивать вручную:

```python
from aiogram.utils.text_decorations import html_decoration as html

def split_long(text: str, limit: int = 4000) -> list[str]:
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > limit:
            chunks.append(current)
            current = para
        else:
            current += ("\n\n" if current else "") + para
    if current:
        chunks.append(current)
    return chunks
```

---

## 7. Парсинг ответа на кнопку без callback (плохая практика)

Не используй `ReplyKeyboardMarkup` для критичных действий — юзер может ввести текст руками, обойдя кнопку. Только `InlineKeyboardMarkup`.

---

## 8. Логирование

```python
import logging
from aiogram.fsm.context import FSMContext

@router.message()
async def any_message(message: Message, state: FSMContext):
    logging.info(
        "msg",
        extra={"user_id": message.from_user.id, "len": len(message.text or "")}
    )
    # никогда не логируй message.text — это PII
```

---

## 9. Тестирование

aiogram-тесты сложные (нужен мок dispatcher'а + фейковый бот). Для plan-app предпочитаем:
- unit-тесты на **сервисы** (`app/shared/`), а не на хендлеры
- e2e через настоящего бота на test-канале (Phase 5+)

---

## 10. Ссылки

- Официальные доки: https://docs.aiogram.dev/en/v3.x/
- Migration guide 2→3: https://docs.aiogram.dev/en/v3.x/migration_2_to_3.html
- Примеры: https://github.com/aiogram/aiogram/tree/dev-3.x/examples
