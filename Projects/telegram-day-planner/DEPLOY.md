# Деплой на Render

## Быстрый старт

### 1. Push в GitHub
```bash
cd telegram-day-planner
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/plan.git
git push -u origin main
```

### 2. Деплой на Render

**Вариант A: Через render.yaml (Blueprint)**

1. Зайди на [render.com](https://render.com) → Dashboard
2. Нажми **"New"** → **"Blueprint"**
3. Подключи GitHub репозиторий
4. Выбери файл `render.yaml` из репозитория
5. Нажми **"Apply"**

Render автоматически создаст:
- PostgreSQL базу данных
- API сервис
- Bot сервис

**Вариант B: Ручной**

1. Создай PostgreSQL: **New** → **PostgreSQL** → Free tier
2. Скопируй `DATABASE_URL` из Internal Connection String
3. Создай Web Service для API:
   - Root Directory: `api`
   - Build Command: `npm install && npm run build`
   - Start Command: `npm run start:api`
   - Environment: Node
4. Создай Web Service для Bot:
   - Root Directory: `bot`
   - Build Command: `npm install && npm run build`
   - Start Command: `npm run start:bot`
   - Environment: Node

### 3. Переменные окружения

Для обоих сервисов добавь:

| Ключ | Значение |
|------|----------|
| `DATABASE_URL` | Из PostgreSQL (созданного на шаге 2) |
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEY` | Ключ от console.groq.com |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` |
| `MINIAPP_URL` | URL Mini App (если есть) |
| `NODE_ENV` | `production` |

### 4. После деплоя

1. Проверь health endpoints:
   - API: `https://plan-api.onrender.com/health`
   - Bot: `https://plan-bot.onrender.com/health`

2. Установи webhook для Mini App (если нужно):
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://plan-api.onrender.com/webhook
   ```

## Структура на Render

```
plan-bot     → Telegram бот (polling)
plan-api     → REST API + Mini App
plan-db      → PostgreSQL
```

## Мониторинг

- Логи доступны в Dashboard Render
- Free tier: сервисы "спят" после 15 минут неактивности
- "Спящий" сервис просыпается за ~30 сек при первом запросе

## Команды Render CLI (опционально)

```bash
# Установить
npm install -g @render/cli

# Логи
render logs -s plan-bot
render logs -s plan-api
```

## Troubleshooting

**Bot не отвечает?**
- Проверь `TELEGRAM_BOT_TOKEN`
- Проверь логи на Render

**API ошибки?**
- Проверь `DATABASE_URL`
- Проверь подключение к БД через Render Dashboard

**Free tier limitations:**
- Сервисы "засыпают" без трафика
- 750 часов/month бесплатно
- Один PostgreSQL бесплатно
