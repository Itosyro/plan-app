# PLAN — Telegram Bot + Mini App для планирования дня

Telegram-бот, который превращает хаотичные мысли и голосовые сообщения в структурированный план дня. Бот для быстрого захвата, Mini App для просмотра и управления.

## Стек

**Backend:** Node.js, TypeScript, grammY, Fastify, Prisma, PostgreSQL, Zod, Pino  
**Frontend (Mini App):** Next.js, React, TypeScript, Tailwind CSS, Zustand  
**AI / Speech:** Groq API (LLM), Groq Speech-to-Text (whisper-large-v3-turbo)  
**Инфраструктура:** Docker Compose, PostgreSQL

## Архитектура

```
plan-app/
├── src/                    # Backend (Bot + API)
│   ├── api/                # Fastify API сервер
│   │   ├── auth.ts         # Telegram init data валидация
│   │   ├── server.ts       # Точка входа API
│   │   └── routes/         # API маршруты
│   ├── bot/                # grammY бот
│   │   ├── main.ts         # Точка входа бота
│   │   ├── handlers.ts     # Обработчики команд
│   │   ├── message-handler.ts  # Обработка текста/голоса
│   │   └── format.ts       # Форматирование ответов
│   ├── ai/                 # AI сервис
│   │   ├── service.ts      # Groq API клиент
│   │   └── prompts.ts      # Промпт-шаблоны
│   ├── cron/               # Фоновые задачи
│   │   └── index.ts        # Дайджест, пинг зависших
│   ├── db/
│   │   └── seed.ts         # Тестовые данные
│   ├── shared/             # Общие модули
│   │   ├── schemas.ts      # Zod-схемы
│   │   ├── config.ts       # Валидация env
│   │   ├── logger.ts       # Pino логгер
│   │   ├── constants.ts    # Константы
│   │   └── date-utils.ts   # Утилиты дат
│   └── __tests__/          # Тесты
├── miniapp/                # Next.js Mini App
│   └── src/
│       ├── app/            # Страницы (App Router)
│       ├── components/     # UI компоненты
│       ├── lib/            # API клиент, store
│       └── types/          # TypeScript типы
├── prisma/
│   └── schema.prisma       # Схема БД
├── docker-compose.yml      # PostgreSQL
└── .env.example            # Переменные окружения
```

## Быстрый старт

### 1. Создать Telegram бота

1. Открыть [@BotFather](https://t.me/BotFather) в Telegram
2. Отправить `/newbot`, задать имя и username
3. Сохранить полученный токен (`TELEGRAM_BOT_TOKEN`)
4. Отправить `/mybots` → выбрать бота → Bot Settings → Menu Button
5. Указать URL Mini App (для локальной разработки используйте ngrok/cloudflared)

### 2. Получить Groq API Key

1. Зарегистрироваться на [console.groq.com](https://console.groq.com)
2. Создать API key в разделе API Keys
3. Сохранить ключ (`GROQ_API_KEY`)

### 3. Настроить окружение

```bash
# Клонировать репозиторий
git clone https://github.com/Itosyro/plan-app.git
cd plan-app

# Скопировать .env
cp .env.example .env
# Заполнить TELEGRAM_BOT_TOKEN, GROQ_API_KEY, JWT_SECRET
```

### 4. Поднять базу данных

```bash
docker-compose up -d
```

### 5. Установить зависимости и подготовить БД

```bash
# Backend
npm install
npx prisma db push
npx prisma generate

# Mini App
cd miniapp
npm install
cd ..
```

### 6. (Опционально) Заполнить тестовыми данными

```bash
npm run db:seed
```

### 7. Запустить

```bash
# Терминал 1 — Бот
npm run dev

# Терминал 2 — API сервер
npm run dev:api

# Терминал 3 — Mini App
cd miniapp && npm run dev
```

Или всё вместе:

```bash
npm run dev:all
# + в отдельном терминале: cd miniapp && npm run dev
```

## Тестирование

### Текстовый flow

1. Открыть бота в Telegram
2. Отправить `/start`
3. Написать текст, например: "Нужно сегодня допилить бота, завтра ответить клиенту, и когда-нибудь почитать про Kubernetes"
4. Бот разберёт на задачи и покажет summary

### Голосовой flow

1. Отправить голосовое сообщение (до 5 минут)
2. Бот отправит "Слушаю и разбираю..."
3. Транскрибирует через Groq STT
4. Разберёт на задачи
5. Покажет summary + кнопку Mini App

### Mini App

1. Нажать кнопку "Открыть планер" в боте
2. Увидеть задачи, секции "Сегодня", "Завтра", "Без даты"
3. Переключиться на вид "Круги"
4. Открыть задачу, изменить статус
5. Зайти в настройки

## Тесты

```bash
npm test
```

## API Endpoints

Все запросы к API требуют заголовок `x-init-data` с Telegram init data.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health check |
| GET | `/api/me` | Текущий пользователь |
| GET | `/api/tasks` | Список задач (фильтр: `?status=today,inbox`) |
| GET | `/api/tasks/:id` | Детали задачи |
| POST | `/api/tasks` | Создать задачу |
| PATCH | `/api/tasks/:id` | Обновить задачу |
| POST | `/api/tasks/:id/complete` | Завершить задачу |
| POST | `/api/tasks/:id/reopen` | Вернуть в работу |
| POST | `/api/tasks/:id/reschedule` | Перенести задачу |
| DELETE | `/api/tasks/:id` | Удалить задачу |
| GET | `/api/notes` | Список заметок |
| POST | `/api/notes` | Создать заметку |
| PATCH | `/api/notes/:id` | Обновить заметку |
| GET | `/api/projects` | Список проектов |
| POST | `/api/projects` | Создать проект |
| PATCH | `/api/projects/:id` | Обновить проект |
| GET | `/api/settings` | Настройки пользователя |
| PATCH | `/api/settings` | Обновить настройки |
| GET | `/api/daily-plan/today` | План на сегодня |
| POST | `/api/daily-plan/rebuild` | Пересобрать план |
| GET | `/api/inbox` | Входящие записи |

## Telegram Init Data Auth

Mini App аутентификация работает через штатный механизм Telegram:

1. Frontend получает `initData` из `window.Telegram.WebApp.initData`
2. Отправляет в заголовке `x-init-data` каждого запроса
3. Backend валидирует HMAC-подпись с использованием `TELEGRAM_BOT_TOKEN`
4. Проверяет `auth_date` (не старше 24 часов)
5. Извлекает пользователя и создаёт/находит его в БД

## Переменные окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `DATABASE_URL` | Да | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | Да | Токен Telegram бота |
| `GROQ_API_KEY` | Да | API ключ Groq |
| `GROQ_MODEL` | Нет | Модель LLM (default: llama-3.3-70b-versatile) |
| `GROQ_STT_MODEL` | Нет | Модель STT (default: whisper-large-v3-turbo) |
| `MINIAPP_URL` | Нет | URL Mini App (default: http://localhost:3000) |
| `PORT` | Нет | Порт API сервера (default: 3001) |
| `JWT_SECRET` | Нет | Секрет для JWT (default: dev-secret) |
| `NODE_ENV` | Нет | Окружение (development/production) |

## Деплой

### Backend (Railway / Render / Fly.io)

1. Собрать: `npm run build`
2. Запустить бота: `npm run start:bot`
3. Запустить API: `npm run start:api`
4. Указать все env-переменные
5. Подключить PostgreSQL

### Frontend (Vercel)

1. Подключить репо, указать root directory: `miniapp`
2. Указать `NEXT_PUBLIC_API_URL` на URL backend API
3. Задеплоить

### Настройка Mini App в Telegram

1. @BotFather → `/mybots` → выбрать бота → Bot Settings → Menu Button
2. Указать URL задеплоенного Mini App
3. Или: Bot Settings → Menu Button → Configure menu button

## Ограничения MVP

- Голосовые ограничены 5 минутами
- Один пользователь = один аккаунт (без команд)
- Часовой пояс по умолчанию: Europe/Moscow
- Напоминания на cron-основе (не realtime)
- Нет оффлайн-режима в Mini App
