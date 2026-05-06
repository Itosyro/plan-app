# PLAN App — Progress

## Phase 1: Backend + Bot Core
- [x] Prisma schema (User, Task, Note, Project, InboxEntry, DailyPlan, Reminder, AiRun, TaskEvent)
- [x] Telegram Bot (grammy): /start, /help, /settings, /today, /plan, /add
- [x] Message handler: text, voice, audio
- [x] AI service (Groq LLaMA 3.3 70B): parseInput, buildDayPlan, dailyReview
- [x] STT (Groq Whisper): voice-to-text
- [x] Fastify API server with auth (Telegram WebApp initData validation)
- [x] API endpoints: tasks CRUD, settings, notes, projects, daily-plan

## Phase 2: Mini App UI
- [x] Todoist-style redesign (Inter font, clean palette, red accent)
- [x] Task list view with collapsible sections (Today/Tomorrow/Upcoming/Inbox/Someday/Done)
- [x] Priority-colored checkboxes (red=high, orange=medium)
- [x] Circles view (status overview bubbles)
- [x] FAB button + add task modal
- [x] Task detail bottom sheet (complete/reschedule/delete)
- [x] Skeleton loading states
- [x] Toast notifications

## Phase 3: Kanban Column View
- [x] Horizontal scrollable columns per status
- [x] Long-press drag-and-drop between columns
- [x] Drag ghost with rotation/shadow
- [x] Column highlight on drag-over
- [x] Haptic feedback (navigator.vibrate)
- [x] Settings toggle to enable/disable column view
- [x] columnViewEnabled added to DB schema

## Phase 4: Code Review & Hardening
- [x] Input validation (Zod) on POST/PATCH tasks, settings, reschedule
- [x] Proper HTTP status codes (404 for not found, 400 for bad input)
- [x] Ownership checks before update/delete (prevents accessing other users' tasks)
- [x] Body size limit (256KB)
- [x] Global error handler (Prisma errors -> proper HTTP responses)
- [x] Fetch timeouts on Groq API calls (30s) and STT (60s)
- [x] Audio file size limit (20MB)
- [x] Graceful shutdown (SIGTERM/SIGINT) for both bot and API
- [x] Bot PORT fix for Render deployment

## Phase 5: Deploy
- [ ] Получить от пользователя: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, Render API Key
- [ ] Настроить PostgreSQL на Render
- [ ] prisma db push
- [ ] Deploy API service
- [ ] Deploy Bot service
- [ ] Установить MINIAPP_URL на URL API сервиса
- [ ] Проверить работу бота в Telegram

## Phase 6: Polish (будущее)
- [ ] Offline mode / optimistic updates
- [ ] Pull-to-refresh
- [ ] Swipe actions на задачах (swipe left = delete, right = complete)
- [ ] Фильтрация задач по проектам
- [ ] Поиск задач
- [ ] Dark mode
- [ ] PWA support
