---
name: tg-bot-api
description: Cheat-sheet по актуальной (Bot API 10.0, май 2026) Telegram Bot API. Что доступно, что новое, что важное для plan-app. Используй перед добавлением любых новых фич бота — особенно если клиент просит то, чего раньше не было (например, реакции, polls, payments, mini app, business mode).
---

# Telegram Bot API — выжимка для plan-app

> **Источник:** https://core.telegram.org/bots/api-changelog
> **Актуальная версия на 2026-05-09:** **Bot API 10.0** (от 8 мая 2026)
> **aiogram (Python библиотека) последняя:** 3.26.0+ (Bot API 9.5+)

Этот файл — **выжимка** того, что меняется быстро. Полная
актуальная спека всегда тут:
* Reference: https://core.telegram.org/bots/api
* Changelog: https://core.telegram.org/bots/api-changelog

Перед использованием новой возможности — **проверь changelog** на
свежие правки.

---

## Что мы используем сейчас

* **aiogram 3.x** (см. `pyproject.toml`).
* **Webhook** через `setWebhook(drop_pending_updates=True)`.
* **MarkdownV2** для форматирования сообщений (escape через
  `aiogram.utils.markdown`).
* **Inline keyboards** для `/today`, `/settings`, /digest.
* **Voice messages** через `getFile + downloadFile`, потом Whisper-like
  обработка через Groq.
* **`update_id` идемпотентность** — таблица `telegram_updates`.

## Чего НЕ используем (но могли бы)

| Возможность | Версия | Статус | Можно использовать как |
|---|---|---|---|
| **Reactions** на сообщения | 7.0 (фев 2024) | Не используем | Эмоции на статус задачи (✅, 🔥, 👀). |
| **Stars / payments 2.0** | 7.4 / 7.6 | Не используем | Premium subscription за продвинутые фичи. |
| **Mini Apps (WebApp)** | 6.0+ / актуально | Phase 5 | Веб-интерфейс задач/настроек. |
| **Business mode** | 7.2+ | Не используем | Если будем продавать как сервис компаниям. |
| **Inline-mode** | давно | Не используем | `@plan_bot задача завтра` из любого чата. |
| **Stickers / sticker sets** | давно | Не используем | UX украшение. |
| **Custom emoji** | 6.6+ | Premium-only | Брендинг. |
| **Polls / quizzes** | давно | Не используем | Опросы для команды (Phase 5+). |
| **Forum topics** | 6.3+ | Не используем | Топики для категорий задач. |
| **Live locations** | давно | Не используем | Не наш use-case. |
| **Live photos** | 10.0 (май 2026) | Не используем | Возможно для voice-реплеев. |
| **Guest mode** | 10.0 (май 2026) | Не используем | Бот видит сообщения других ботов. |

---

## Свежие изменения (что появилось в 2026)

### Bot API 10.0 (8 мая 2026)
* **Guest Mode**: бот может получать сообщения и отвечать в чатах,
  где не является участником. Новые поля
  `supports_guest_queries`, `guest_bot_caller_user`,
  `guest_query_id`. Метод `answerGuestQuery`.
* **Polls с медиа**: `PollMedia`, `InputPollMedia`, теперь варианты
  ответов могут содержать стикеры / локации / venue. Минимум опций
  снижен с 2 до 1.
* **Live Photos**: новый тип медиа `LivePhoto` — фото + короткое
  видео. Можно отправлять через `sendLivePhoto`.
* **Bot-to-bot communication**: бизнес-боты могут общаться друг
  с другом по username (если оба включили этот режим).
* **deleteAllMessageReactions / deleteMessageReaction** — раньше
  удалить реакции мог только пользователь.

### Bot API 9.6 (3 апреля 2026)
* **Managed Bots** — родительский бот может создавать и управлять
  под-ботами. `getManagedBotToken`, `replaceManagedBotToken`.
* **Quizzes с несколькими правильными ответами**:
  `correct_option_ids` (массив), `allows_multiple_answers`.
* **Polls**: `shuffle_options`, `allow_adding_options`,
  `allows_revoting`, увеличено максимальное время автозакрытия до
  2 628 000 секунд (~30 дней).

### Bot API 9.5 (1 марта 2026)
* **Member tags** — расширенная разметка участников чатов.
* **`date_time` entities** в сообщениях — встроенные временные
  метки.
* **`can_manage_tags`** admin right.

### Bot API 9.4 (9 февраля 2026)
* **Custom emoji в обычных сообщениях** для ботов с Premium.
* **Forum topics в private chats** — можно создавать топики из бота.
* **Кастомные иконки** на кнопках через `icon_custom_emoji_id`.
* **Цветные кнопки** через поле `style` (новое значение для
  `KeyboardButton` / `InlineKeyboardButton`).

### Bot API 9.3 (31 декабря 2025)
* Stable release нескольких ранних 9.x фич.

---

## Гочки нашего бота (plan-app)

### G-1. Webhook secret_token

Мы используем **двойную проверку**: secret в URL пути + секрет в
header `X-Telegram-Bot-Api-Secret-Token`. Не убирай ни одну.

### G-2. `drop_pending_updates=True`

Стоит на старте через lifespan. Если кто-то писал боту пока он
лежал — эти update'ы не доедут. Если когда-то понадобится держать
их — снимай флаг **и тестируй** (чтобы webhook idempotency
не сломалась).

### G-3. `parse_mode = MarkdownV2`

Все спецсимволы в пользовательском вводе должны быть экранированы.
Используй `aiogram.utils.markdown.text(.., escape=True)` или
`html.escape` (если перейдёшь на HTML).

**Что ломает**: `*`, `_`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`,
`#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`. Один не-экранированный
символ → 400 Bad Request: can't parse entities.

### G-4. Inline-keyboard callback_data lim 64 байта

Telegram режет всё после 64. Если пакуешь несколько значений
через `:`, не превышай. Используй короткие префиксы (`s:set:m:08:00`,
не `settings:set_morning_digest_at:08:00`).

Также — символ `:` валиден в callback_data, но **парсить его надо
с `maxsplit`** (см. defensive-programming/SKILL.md G-14).

### G-5. Лимит сообщения 4096 символов

Длинные дайджесты режь / шли несколькими сообщениями. Не надейся,
что Telegram сам разобьёт.

### G-6. Голосовые сообщения

`message.voice.file_id` → `bot.get_file(file_id)` →
`bot.download_file(file.file_path)` → отправка в Groq Whisper.

Лимит — 20 МБ для downloadFile через бота. Реально голосовые
короче 1-2 МБ.

### G-7. Rate limits

Дефолт: 30 сообщений/секунду общий, 1 сообщение/секунду на чат.
При превышении — 429 + `retry_after`. aiogram `Bot` сам уважает
эти лимиты, но если шлёшь массовый дайджест по N чатам — добавляй
свою очередь (см. I-8 в `docs/REVIEW-2026-05-09-v2.md`).

### G-8. Webhook timeouts

Telegram даёт **серверу 60 секунд** на ответ 200, иначе ретраит.
Наш `/tg/<secret>` endpoint должен быть быстрым (мы используем
async + классификатор-как-fire-and-forget). Если LLM занимает
больше — отвечай 200 сразу, обработку запускай в background task.

### G-9. Длинные операции → typing indicator

Если AI обрабатывает голосовое 5 секунд — **обязательно** шли
`bot.send_chat_action(chat_id, action="typing")` каждые ~5 секунд,
пока думаем. Иначе пользователь думает, что бот сдох.

aiogram удобный helper: `async with ChatActionSender.typing(...)`.

### G-10. `from`-параметр в API → `from_` в Python

aiogram переименовывает зарезервированное `from` в `from_`. Это
гочка которую часто пропускают — документация TG говорит `from`,
а в коде Python пишешь `from_`.

---

## Полезные методы для plan-app

| Метод | Когда использовать |
|---|---|
| `setWebhook(secret_token=...)` | Старт. Только в lifespan. |
| `deleteWebhook(drop_pending_updates=True)` | Локальная разработка с long-polling. |
| `sendMessage` | Самое частое. parse_mode=MarkdownV2. |
| `editMessageText` / `editMessageReplyMarkup` | После клика inline-кнопки — обнови сообщение, не шли новое. |
| `answerCallbackQuery` | **ОБЯЗАТЕЛЬНО** ответь после callback_query, иначе у юзера крутится спиннер. С пустым text — без visible toast. |
| `sendChatAction(action="typing")` | Перед длинной операцией. |
| `getFile + downloadFile` | Для voice / photo / document. |
| `sendVoice` / `sendAudio` | Если когда-то будем отвечать голосом. |
| `setMyCommands` | Регистрируем `/start`, `/today`, `/week`, `/settings` для меню рядом с полем ввода. |
| `setMyDescription` / `setMyShortDescription` | Описания в профиле бота. Важно для onboarding. |
| `setChatMenuButton(menu_button=MenuButtonWebApp(url=...))` | Phase 5: запуск Mini App из меню бота. |

---

## Что **не** делать

* **Не** хранить `bot_token` в коде. Только через `BOT_TOKEN`
  env / Pydantic Settings.
* **Не** использовать polling в продакшне. Webhook быстрее и
  дешевле. Polling — только для local dev.
* **Не** забывай `answerCallbackQuery` после клика на inline-кнопку.
  Иначе у юзера крутится спиннер ~30 секунд → плохой UX.
* **Не** парси update'ы вручную — aiogram уже делает это в типы.
  Если ловишь баг с `event.message`, скорее всего ты обращаешься
  к атрибуту, которого нет в этом типе update'а.
* **Не** блокируй webhook hand­ler синхронным IO. asyncio + httpx
  + aiosqlite. См. `python-best-practices/SKILL.md`.

---

## Полезные ссылки

* **Reference (вся API спека):** https://core.telegram.org/bots/api
* **Changelog:** https://core.telegram.org/bots/api-changelog
* **aiogram docs:** https://docs.aiogram.dev/en/latest/
* **aiogram source (для глубокого debug):** https://github.com/aiogram/aiogram
* **@BotNews channel:** https://t.me/BotNews — официальные анонсы.
* **@BotTalk:** https://t.me/BotTalk — community discussion.
* **bot.creator (бот для создания/управления ботами):** @BotFather
* **Stripe-style payments docs:** https://core.telegram.org/bots/payments
* **Mini App docs:** https://core.telegram.org/bots/webapps

## Связанные скиллы в репо

* `aiogram-3/SKILL.md` — паттерны кода в наших routers.
* `defensive-programming/SKILL.md` — гочки которые мы уже наловили
  (callback_data parsing, parse_mode, idempotency).
* `python-best-practices/SKILL.md` — async, типы, что НЕ делать.

## Когда обновлять этот файл

* Каждый раз, когда выходит новая мажорная версия Bot API
  (10.x → 11.0).
* Когда мы начинаем использовать ранее не использовавшуюся
  возможность (например, добавим payments → расписать здесь
  гочки payments).
* Раз в 3 месяца как минимум — обновить актуальную версию.
