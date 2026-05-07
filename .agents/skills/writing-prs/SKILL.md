---
name: writing-prs
description: Шаблон описания PR в plan-app. Используй при создании любого PR в этот репозиторий.
---

# Как писать PR в plan-app

PR — это не просто «коммит». Это **разговор** с тем, кто будет ревьюить (человеком или AI).

---

## 1. Заголовок

Формат: `<Phase X | Bugfix | Refactor>: <короткое описание>`

Примеры:
- `Phase 1: minimal bot with webhook + DB`
- `Phase 2: AI splitter (Groq llama-3.1-8b-instant)`
- `Bugfix: courier picks template_only when source=mix`
- `Refactor: extract Groq client into app/ai/groq.py`

Заголовок ≤ 80 символов. Никаких эмодзи (правила репо).

---

## 2. Описание — 5 секций

### Why (зачем)
1–3 предложения. Почему вообще делаем эту работу. Какую проблему решает / какую фазу закрывает.

### What (что)
Маркированный список изменений. **Глаголами** в прошедшем времени.
- Добавил `app/bot/handlers/start.py` с onboarding-визардом
- Завёл миграцию `0002_user_preferences.py`
- Обновил `docs/PROGRESS.md`

### How to test
Конкретные команды для ревьюера / для будущего себя:
```bash
uv run pytest tests/test_onboarding.py -v
# или
uv run uvicorn app.main:app
# отправить /start через Telegram-бот
```

### Risk / rollback
- Что может сломаться
- Как откатить (обычно: `git revert <SHA>` + `alembic downgrade -1` если есть миграция)

### Out of scope
Что **сознательно не делаем** в этом PR (фронт мини-аппки, AI-критик и т.п.) — чтобы ревьюер не искал.

---

## 3. Чек-лист в конце

```markdown
## Checklist
- [x] `uv run ruff format .` — clean
- [x] `uv run ruff check .` — clean
- [x] `uv run pytest -q` — все тесты зелёные
- [x] Миграция (если применимо) проверена локально
- [x] `docs/PROGRESS.md` обновлён
```

---

## 4. Размер PR

- **Хорошо:** ≤ 400 LOC изменений, одна логическая тема
- **Плохо:** > 1000 LOC, мешает ревью, легко пропустить ошибки
- **Очень плохо:** изменения сразу из 2-3 фаз — отдельные PR на каждую

Если PR разбухает — **режь**. Лучше 3 PR по 200 LOC, чем 1 на 600.

---

## 5. Связанные PR / стек

Если PR зависит от другого (не вмёрженного):

```
Зависит от: #N
```

И ставим `base_branch` в head того PR. После мерджа базового — GitHub автоматически перетянет на main.

---

## 6. Скриншоты / GIF (если касается UX)

- Telegram-бот: скриншот диалога (мобильный или web)
- Мини-аппка: GIF с typical-flow

GIF делать через `peek` / `kazam` / `obs` под Linux, или `quicktime` на маке.

---

## 7. Шаблон (копипастить)

```markdown
## Why
<1-3 предложения, какую проблему решает>

## What
- <изменение 1>
- <изменение 2>
- <изменение 3>

## How to test
\`\`\`bash
<команды>
\`\`\`

## Risk / rollback
- <риск 1>
- Rollback: \`git revert <SHA>\`

## Out of scope
- <что не делаем>

## Checklist
- [x] ruff format
- [x] ruff check
- [x] pytest
- [x] миграция (n/a)
- [x] docs/PROGRESS.md
```

---

## 8. Что НЕ делать

- ❌ Заголовок «WIP» / «test» — конкретизируй
- ❌ Описание из одной строки «обновил код»
- ❌ Скриншот с PII (имена/контакты юзеров — замазать)
- ❌ Force-push после первого review-комментария (теряется контекст обсуждения)
- ❌ Мерджить свой PR без хотя бы одного approval (даже AI-агента)

---

## Источники

- [Conventional Commits](https://www.conventionalcommits.org/)
- [How to Write a Git Commit Message (Chris Beams)](https://cbea.ms/git-commit/)
- [Anthropic Skills `pr-description`](https://github.com/anthropics/skills) — идея «why-what-how-risk»
