# PLAN App — Changelog

## Что это за проект

Telegram Mini App для планирования дня. Пользователь отправляет боту текст или голосовое — AI разбирает на задачи, заметки, проекты. В мини-апке можно смотреть и управлять задачами.

**Стек:** Node.js, TypeScript, Fastify, grammy, Prisma (PostgreSQL), Groq API (LLaMA 3.3 + Whisper), vanilla HTML/CSS/JS (frontend).

**Деплой:** Render.com (2 сервиса: bot + api).

---

## 2026-05-06 — Сессия 2: UI Redesign + Code Hardening

### Запрос пользователя
Доделать UI мини-апки: дизайн как у Todoist, режим колонок (как Google Calendar) с drag-and-drop, плавные анимации, всё быстро и без лагов. Подготовить к деплою на Render.

### Что сделано

**Frontend — полный редизайн `public/index.html`:**
- Шрифт Inter, Todoist-подобная палитра (красный акцент #dc4c3e, зелёный #058527, синий #2e7cf6)
- Список задач: складывающиеся секции по статусам, чекбоксы с цветом приоритета
- Круги: обзор количества задач по статусам (bubble chart)
- Колонки (Kanban): горизонтальный скролл, drag-and-drop через long press (300ms), ghost-элемент при перетаскивании
- FAB кнопка (+) внизу справа -> модалка создания задачи с выбором "Сегодня" / "Завтра"
- Модалка деталей задачи (bottom sheet): завершить, на завтра, удалить
- Skeleton loader при загрузке, toast-уведомления

**Backend — безопасность и стабильность:**
- Все POST/PATCH роуты теперь валидируют входные данные через Zod (CreateTaskSchema, UpdateTaskSchema, UpdateSettingsSchema, TaskStatusEnum)
- Правильные HTTP коды: 404 для "не найдено", 400 для невалидных данных
- Проверка ownership перед любым update/delete (нельзя редактировать чужие задачи)
- Body size limit: 256KB
- Global error handler: Prisma ошибки -> правильные HTTP ответы
- API роуты под префиксом /api (было без префикса)
- Статические файлы через @fastify/static
- CORS через @fastify/cors

**AI/STT — таймауты и лимиты:**
- Fetch timeout 30s на Groq API (chat completions)
- Fetch timeout 30s на download + 60s на STT (transcriptions)
- Лимит 20MB на аудио файлы

**Инфраструктура:**
- Graceful shutdown (SIGTERM/SIGINT) для API и бота
- Bot PORT fix: используется PORT от Render (а не HEALTH_PORT)
- columnViewEnabled добавлено в Prisma схему
- Зависимости: @fastify/static, @fastify/cors

### Найденные и исправленные проблемы
1. API роуты без /api префикса — фронтенд не мог достучаться
2. POST /tasks принимал произвольные поля (включая userId) — теперь whitelist через Zod
3. GET /tasks/:id возвращал 200 с `{error: "Not found"}` — теперь 404
4. Prisma errors (record not found) вызывали 500 — теперь обрабатываются
5. Fetch к Groq API мог висеть бесконечно — добавлены AbortController timeouts
6. Бот не слушал PORT от Render — фикс для healthcheck
7. Нет graceful shutdown — PrismaClient connections утекали

---

## 2026-05-05 — Сессия 1: Инициализация проекта

### Запрос пользователя
Создать Telegram бота для планирования дня. Голосовые и текст -> AI разбирает -> задачи. Mini App для управления.

### Что сделано
- Инициализация проекта (Node.js + TypeScript)
- Prisma schema: User, UserSettings, Task, Note, Project, InboxEntry, DailyPlan, Reminder, AiRun, TaskEvent
- Telegram Bot (grammy): команды, обработка сообщений
- AI Service: Groq API (LLaMA 3.3 70B) для парсинга + построения плана дня
- STT: Groq Whisper для голосовых
- Fastify API: CRUD задач, настройки, проекты, заметки
- Первая версия Mini App UI (базовая)
- render.yaml для деплоя на Render
