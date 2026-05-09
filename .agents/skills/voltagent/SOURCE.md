# Источник

Кураторская подборка subagent'ов из самой популярной коллекции
(20K+ stars).

* **Репо:** https://github.com/VoltAgent/awesome-claude-code-subagents
* **Лицензия:** MIT (см. `LICENSE`)
* **Commit на момент бандла:** `6f804f0cfab22fb62668855aa3d62ee3a1453077`
* **Дата бандла:** 2026-05-09

## Что добавлено в этот каталог (релевантно нашему стеку)

### Language / framework specialists
* `python-pro.md` — Python: типы, async, pyproject, ruff, mypy.
* `fastapi-developer.md` — FastAPI: lifespan, dependency injection, Pydantic v2.
* `sql-pro.md` — продвинутый SQL.

### Core development
* `backend-developer.md` — общие практики backend разработки.
* `api-designer.md` — REST/GraphQL дизайн API.
* `frontend-developer.md` — Phase 5 mini-app.
* `fullstack-developer.md` — Phase 5 mini-app (FE + BE).

### Quality & security
* `code-reviewer.md` — детальный чек-лист для PR review.
* `architect-reviewer.md` — ревью архитектурных решений.
* `debugger.md` — debugger-как-роль.
* `error-detective.md` — root-cause analysis по логам/трейсам.
* `qa-expert.md` — QA планирование.
* `test-automator.md` — стратегии автоматизации тестов.
* `security-auditor.md` — security review с OWASP/CWE.
* `performance-engineer.md` — профайлинг и оптимизация.

### Data / AI
* `postgres-pro.md` — Postgres tuning, индексы, EXPLAIN.
* `database-optimizer.md` — запросы, индексы, кэширование.
* `ai-engineer.md` — LLM продакшн (RAG, vector DB, prompt eng).
* `llm-architect.md` — высокоуровневая архитектура LLM-приложений.
* `prompt-engineer.md` — техники промптинга (CoT, few-shot, etc).

### Infrastructure
* `docker-expert.md` — Docker best practices.
* `database-administrator.md` — backup, replication, monitoring.
* `security-engineer.md` — infra security (secrets, IAM, network).
* `devops-incident-responder.md` — инцидент-менеджмент.

### Developer experience
* `refactoring-specialist.md` — методы рефакторинга.
* `documentation-engineer.md` — техническая документация.

## Что НЕ добавлено

Из 130+ subagent'ов взяли только те, что релевантны нашему стеку
(Python / FastAPI / Postgres / Telegram / Groq). Не брали:
* Языки которые мы не используем (Rust, Go, Java, Scala, …).
* Frontend-фреймворки сверх React (Angular, Svelte, Vue, …).
* Облачные платформы которые мы не используем (AWS, Azure, GCP-specific).
* Бизнес/продукт (product manager и т.д.) — не наша роль.

> Если когда-нибудь понадобится — заходи в upstream и копируй.

## Как использовать

Эти subagent'ы написаны в формате Claude Code — у них есть YAML
frontmatter с `name`, `description`, `tools`. **В Devin они
работают как обычные SKILL.md-методички** — читай содержимое,
применяй принципы, не пытайся «вызывать» как отдельного агента.

Главное в них — **детальные чек-листы** по каждому домену. Когда
правишь FastAPI код — открой `fastapi-developer.md` и пройди по
секции «Pydantic v2 patterns» / «Lifespan». Когда делаешь PR review —
открой `code-reviewer.md`.

## Как обновить

```bash
cd /tmp && git clone --depth 1 \
  https://github.com/VoltAgent/awesome-claude-code-subagents.git
# выбери нужные .md файлы и скопируй
# обнови commit hash выше
```
