# PLAN — Telegram бот для планирования дня

Превращай мысли и голосовые в структурированные задачи и план дня.

## Быстрый старт

### 1. Подготовка

```bash
# Клонировать и перейти в папку
cd telegram-day-planner

# Установить зависимости
npm install

# Скопировать пример .env
cp .env.example .env
```

### 2. Заполнить .env

```bash
# Обязательно заполнить:
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
GROQ_API_KEY=your_groq_api_key_from_console.groq.com

# По умолчанию:
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dayplanner
MINIAPP_URL=http://localhost:5173
```

### 3. Запустить PostgreSQL

```bash
# Вариант A: Docker
docker compose up -d postgres

# Вариант B: Локальный PostgreSQL
# Создать БД: dayplanner
```

### 4. Поднять Prisma

```bash
npm run db:push
```

### 5. Запустить бота

```bash
npm run dev:bot
```

### 6. (Опционально) Запустить API для Mini App

```bash
npm run dev:api
```

### 7. Mini App

Открой `public/index.html` через браузер или настрой webhook для Mini App.

## Создание Telegram бота

1. Напиши [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Следуй инструкциям, сохрани токен
4. Добавь токен в `.env` как `TELEGRAM_BOT_TOKEN`

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие + кнопка Mini App |
| `/help` | Справка |
| `/today` | План на сегодня |
| `/plan` | Пересобрать план |
| `/settings` | Быстрые настройки |

## Как работает

1. **Напиши или наговори** — отправь текст или голосовое боту
2. **AI разбирает** — Groq STT транскрибирует голос, затем LLM парсит в структуру
3. **Сохраняется** — задачи, заметки, проекты в PostgreSQL
4. **Summary** — бот отправляет краткий итог
5. **Mini App** — смотри и управляй задачами

## Структура проекта

```
day-planner/
├── src/
│   ├── bot/           # Telegram бот (grammy)
│   ├── api/           # API сервер (Fastify)
│   ├── ai/            # AI сервис (Groq)
│   └── shared/        # Общие схемы (Zod)
├── prisma/
│   └── schema.prisma  # Модели БД
├── public/
│   └── index.html     # Mini App
├── docker-compose.yml
└── .env.example
```

## Модели данных

- **User** — пользователь Telegram
- **Task** — задача (статусы: inbox, today, tomorrow, upcoming, someday, done)
- **Note** — заметка
- **Project** — проект
- **InboxEntry** — входящее сообщение (для отладки/истории)
- **DailyPlan** — план на день
- **AiRun** — лог AI операций

## Переменные окружения

| Переменная | Описание | Обязательно |
|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от BotFather | Да |
| `GROQ_API_KEY` | API ключ Groq | Да |
| `DATABASE_URL` | PostgreSQL connection string | Да |
| `MINIAPP_URL` | URL Mini App | Нет |
| `GROQ_STT_MODEL` | Модель STT (по умолчанию: whisper-large-v3-turbo) | Нет |
| `PORT` | Порт API сервера (по умолчанию: 3000) | Нет |

## Ограничения MVP

- Один пользователь на бота (monolithic)
- Groq API (можно заменить на OpenAI)
- Нет Push-уведомлений (только в планах)
- Mini App работает через iframe или webhook

## Деплой (позже)

Рекомендуемый стек:
- **Бот + API**: Railway / Render / Fly.io
- **БД**: Supabase / Neon / Railway Postgres
- **Mini App**: Vercel / Cloudflare Pages

Для деплоя:
1. Запусти `npm run build`
2. Деплой `dist/` папки
3. Подключи PostgreSQL
4. Настрой переменные окружения
5. Укажи webhook URL для Mini App в BotFather
