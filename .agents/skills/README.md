# .agents/skills

Складываем сюда:
- скиллы Anthropic из `anthropics/skills` (code-review, pr-description, writing-plans, skill-creator);
- скиллы Obra/Superpowers;
- prompt-engineering канон (Anthropic prompt engineering, dair-ai/Prompt-Engineering-Guide и т.п.);
- собственные методички — best practices конкретно для plan-app.

Каждый скилл — папка с `SKILL.md` (frontmatter `name` + `description` обязательно) и любые вспомогательные файлы.

Скачивание скиллов сюда — отдельный PR в Phase 0+ (после смерджа этого PR), чтобы не раздувать базовый чистящий PR.

## Зачем нам это

Когда работа над задачей идёт в новой сессии (Devin, Claude Code, OpenCode), агент сначала смотрит сюда. Тут — наши лучшие практики, чтобы не повторять ошибки и не отходить от стиля проекта.

## Что точно туда положим

- `code-review/` — чек-лист для code review.
- `writing-prs/` — как писать PR (заголовок, описание, тесты, скриншоты).
- `prompt-engineering/` — выжимка best-practice для всех LLM-промптов проекта.
- `russian-nlp/` — заметки про парсинг русских дат, лемматизацию, граблях с pymorphy3 / dateparser.
- `aiogram-3/` — паттерны для FSM и хендлеров aiogram 3.
- `groq-tips/` — лимиты, ретраи, ключевые модели.
