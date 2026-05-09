# Skills catalog — что лежит в `.agents/skills/`

Этот файл — **карта** всех методичек проекта. AI-агент / новый разработчик читает сначала его, потом — нужный SKILL.md.

---

## Внутренние методички plan-app (custom)

| Скилл | Когда читать |
|---|---|
| [`plan-app-internal/SKILL.md`](./plan-app-internal/SKILL.md) | **Перед любой работой в репо.** Карта проекта, стек, gotchas. |
| [`prompt-engineering/SKILL.md`](./prompt-engineering/SKILL.md) | Перед написанием любого LLM-промпта (Splitter / Classifier / Critic / Courier). |
| [`code-review/SKILL.md`](./code-review/SKILL.md) | Перед approve PR (своего или чужого). Чек-лист на 30 пунктов. |
| [`writing-prs/SKILL.md`](./writing-prs/SKILL.md) | Перед открытием PR. Шаблон описания. |
| [`russian-nlp/SKILL.md`](./russian-nlp/SKILL.md) | Перед правкой парсинга русских дат / категорий / морфологии. |
| [`aiogram-3/SKILL.md`](./aiogram-3/SKILL.md) | Перед правкой `app/bot/` (хендлеры, роутеры, FSM). |
| [`groq-tips/SKILL.md`](./groq-tips/SKILL.md) | Перед правкой `app/ai/` (Groq API, ротация ключей, retry). |
| [`defensive-programming/SKILL.md`](./defensive-programming/SKILL.md) | Перед любой правкой user-facing кода. Allow-lists, naive-UTC, parse_mode discipline — выжимка из mega-review. |
| [`systematic-debugging/SKILL.md`](./systematic-debugging/SKILL.md) | При **любом** баге / упавшем тесте. Сначала root-cause, потом фикс. Адаптировано из obra/superpowers (MIT). |
| [`testing-async-python/SKILL.md`](./testing-async-python/SKILL.md) | Перед написанием тестов. pytest-asyncio, in-memory SQLite, respx-моки Groq, fake-bot, `now=...`. |
| [`migrations-safely/SKILL.md`](./migrations-safely/SKILL.md) | Перед любой правкой `app/db/models.py`. Alembic + SQLModel, autogenerate gotchas, безопасный drop column. |
| [`using-uv/SKILL.md`](./using-uv/SKILL.md) | Cheat-sheet по uv: sync / add / lock / run, что коммитить, как чинит CI. |
| [`requesting-code-review/SKILL.md`](./requesting-code-review/SKILL.md) | Перед отправкой работы на review (sub-agent или fresh chat). |
| [`socraticode-principles/SKILL.md`](./socraticode-principles/SKILL.md) | Перед навигацией по незнакомому коду / большим рефактором. Hybrid search + dependency graph + blast-radius. |
| [`tg-bot-api/SKILL.md`](./tg-bot-api/SKILL.md) | Перед добавлением новой Telegram-фичи. Что есть в Bot API 10.0, чего раньше не было. |
| [`python-best-practices/SKILL.md`](./python-best-practices/SKILL.md) | Перед написанием/правкой Python кода. Async, типы, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, pytest, ruff, mypy. |

---

## Скиллы из `anthropics/skills` (бандл)

Снепшоты официальных скиллов Anthropic. Лицензия Apache 2.0.
Источник + commit зафиксированы в `anthropic/SOURCE.md`.

| Скилл | Применимость |
|---|---|
| [`skill-creator/`](./skill-creator/SKILL.md) | Когда создаёшь новый собственный скилл — следуй этому шаблону + spec. |
| [`mcp-builder/`](./mcp-builder/SKILL.md) | На будущее: если решим интегрировать MCP-серверы (Phase 5+). |
| [`webapp-testing/`](./webapp-testing/SKILL.md) | Phase 5: тестирование Telegram Mini App с Playwright. |
| [`anthropic/brand-guidelines/SKILL.md`](./anthropic/brand-guidelines/SKILL.md) | Phase 5 Mini App: визуалка/брендинг. |
| [`anthropic/claude-api/SKILL.md`](./anthropic/claude-api/SKILL.md) | На будущее: если будем дёргать Claude API (сейчас Groq). |
| [`anthropic/frontend-design/SKILL.md`](./anthropic/frontend-design/SKILL.md) | Phase 5 Mini App: production-grade UI без AI-щаблонности. |
| [`anthropic/web-artifacts-builder/SKILL.md`](./anthropic/web-artifacts-builder/SKILL.md) | Phase 5 Mini App: сложные React/Tailwind/shadcn компоненты. |

## Скиллы из `obra/superpowers` (бандл)

Кураторская подборка Jesse Vincent (obra). Источник + commit
зафиксированы в `obra/SOURCE.md`. Все 14 скиллов про процесс
разработки: дебаг, ревью, планирование, TDD.

| Скилл | Применимость |
|---|---|
| [`obra/using-superpowers/SKILL.md`](./obra/using-superpowers/SKILL.md) | **Точка входа** — как находить и применять остальные скиллы. |
| [`obra/systematic-debugging/SKILL.md`](./obra/systematic-debugging/SKILL.md) | **При любом баге.** Сначала root-cause, потом фикс. (Уже адаптирован в `systematic-debugging/`, но оригинал тут для референса.) |
| [`obra/verification-before-completion/SKILL.md`](./obra/verification-before-completion/SKILL.md) | Перед заявлением «готово» — реальная верификация. Антидот к «работает у меня». |
| [`obra/test-driven-development/SKILL.md`](./obra/test-driven-development/SKILL.md) | Red → Green → Refactor дисциплина. |
| [`obra/writing-plans/SKILL.md`](./obra/writing-plans/SKILL.md) | Как писать исполняемый план задачи. |
| [`obra/executing-plans/SKILL.md`](./obra/executing-plans/SKILL.md) | Как методично выполнять план без срезания углов. |
| [`obra/brainstorming/SKILL.md`](./obra/brainstorming/SKILL.md) | Перед любой творческой задачей: спецификация требований через AB-варианты. |
| [`obra/writing-skills/SKILL.md`](./obra/writing-skills/SKILL.md) | Чек-лист для нового скилла (формат + содержание). |
| [`obra/receiving-code-review/SKILL.md`](./obra/receiving-code-review/SKILL.md) | Как принимать ревью без подхалимажа. |
| [`obra/requesting-code-review/SKILL.md`](./obra/requesting-code-review/SKILL.md) | Как просить ревью у sub-agent / fresh chat. |
| [`obra/finishing-a-development-branch/SKILL.md`](./obra/finishing-a-development-branch/SKILL.md) | Когда всё готово — куда мержить, в каком порядке. |
| [`obra/dispatching-parallel-agents/SKILL.md`](./obra/dispatching-parallel-agents/SKILL.md) | Запуск нескольких суб-агентов параллельно. |
| [`obra/subagent-driven-development/SKILL.md`](./obra/subagent-driven-development/SKILL.md) | Делегировать sub-agent'у целые этапы. |
| [`obra/using-git-worktrees/SKILL.md`](./obra/using-git-worktrees/SKILL.md) | Параллельная работа над несколькими ветками без stash. |

---

## Скиллы из `VoltAgent/awesome-claude-code-subagents` (бандл)

Кураторская подборка из самой популярной коллекции subagent'ов
(20K+ stars). Лицензия MIT. Источник + commit зафиксированы в
`voltagent/SOURCE.md`.

26 файлов под наш стек. Эти .md написаны как Claude Code subagent'ы
с YAML frontmatter, но в Devin читай их **как обычные методички**.

### Language / framework
| Скилл | Применимость |
|---|---|
| [`voltagent/python-pro.md`](./voltagent/python-pro.md) | Глубокий Python: типы, async, packaging, ruff, mypy. |
| [`voltagent/fastapi-developer.md`](./voltagent/fastapi-developer.md) | FastAPI deep-dive: lifespan, DI, Pydantic v2. |
| [`voltagent/sql-pro.md`](./voltagent/sql-pro.md) | Сложный SQL: оконные функции, CTE, оптимизация. |

### Quality & security
| Скилл | Применимость |
|---|---|
| [`voltagent/code-reviewer.md`](./voltagent/code-reviewer.md) | Расширенный чек-лист для PR review. |
| [`voltagent/architect-reviewer.md`](./voltagent/architect-reviewer.md) | Ревью архитектурных решений. |
| [`voltagent/debugger.md`](./voltagent/debugger.md) | Подходы к дебагу как у профи. |
| [`voltagent/error-detective.md`](./voltagent/error-detective.md) | Root-cause analysis по логам/трейсам. |
| [`voltagent/qa-expert.md`](./voltagent/qa-expert.md) | QA-планирование, тест-стратегии. |
| [`voltagent/test-automator.md`](./voltagent/test-automator.md) | Автоматизация тестов на разных уровнях. |
| [`voltagent/security-auditor.md`](./voltagent/security-auditor.md) | Security review с OWASP/CWE. |
| [`voltagent/performance-engineer.md`](./voltagent/performance-engineer.md) | Профайлинг и оптимизация. |

### Data / AI
| Скилл | Применимость |
|---|---|
| [`voltagent/postgres-pro.md`](./voltagent/postgres-pro.md) | Postgres tuning, индексы, EXPLAIN. |
| [`voltagent/database-optimizer.md`](./voltagent/database-optimizer.md) | Оптимизация запросов и схем. |
| [`voltagent/ai-engineer.md`](./voltagent/ai-engineer.md) | LLM продакшн (RAG, vector DB, prompt eng). |
| [`voltagent/llm-architect.md`](./voltagent/llm-architect.md) | Высокоуровневая архитектура LLM-приложений. |
| [`voltagent/prompt-engineer.md`](./voltagent/prompt-engineer.md) | Техники промптинга (CoT, few-shot, etc). |

### Core development
| Скилл | Применимость |
|---|---|
| [`voltagent/backend-developer.md`](./voltagent/backend-developer.md) | Backend паттерны общего назначения. |
| [`voltagent/api-designer.md`](./voltagent/api-designer.md) | REST/GraphQL дизайн. |
| [`voltagent/frontend-developer.md`](./voltagent/frontend-developer.md) | Phase 5 mini-app. |
| [`voltagent/fullstack-developer.md`](./voltagent/fullstack-developer.md) | Phase 5 mini-app FE+BE. |

### Infrastructure
| Скилл | Применимость |
|---|---|
| [`voltagent/docker-expert.md`](./voltagent/docker-expert.md) | Docker best practices. |
| [`voltagent/database-administrator.md`](./voltagent/database-administrator.md) | Backup, replication, monitoring. |
| [`voltagent/security-engineer.md`](./voltagent/security-engineer.md) | Infra security (secrets, IAM, network). |
| [`voltagent/devops-incident-responder.md`](./voltagent/devops-incident-responder.md) | Инциденты и постмортемы. |

### Developer experience
| Скилл | Применимость |
|---|---|
| [`voltagent/refactoring-specialist.md`](./voltagent/refactoring-specialist.md) | Методы рефакторинга. |
| [`voltagent/documentation-engineer.md`](./voltagent/documentation-engineer.md) | Техническая документация. |

---

## Внешние референсы

| Реф | Лежит | Источник |
|---|---|---|
| Brex Prompt Engineering Guide | [`brex-prompt-engineering/REFERENCE.md`](./brex-prompt-engineering/REFERENCE.md) | https://github.com/brexhq/prompt-engineering |
| Anthropic Prompt Engineering Tutorial | (онлайн) | https://github.com/anthropics/prompt-eng-interactive-tutorial |
| Anthropic Cookbook | (онлайн) | https://github.com/anthropics/anthropic-cookbook |
| dair-ai Prompt Engineering Guide | (онлайн) | https://www.promptingguide.ai/ |
| awesome-chatgpt-prompts | (онлайн) | https://github.com/f/awesome-chatgpt-prompts |

> Решено **не бандлить** эти репо в `.agents/skills/` — они весят 100+ МБ из-за изображений / переводов / ноутбуков. Достаточно ссылок: дёшево обновлять, не раздувает наш репо.

---

## Как использовать (для AI-агента)

1. **Открыл репо первый раз?** → читай [`plan-app-internal/SKILL.md`](./plan-app-internal/SKILL.md) и `docs/`.
2. **Делаешь PR?** → смотри [`writing-prs/SKILL.md`](./writing-prs/SKILL.md).
3. **Ревьюишь PR?** → пройди по [`code-review/SKILL.md`](./code-review/SKILL.md).
4. **Пишешь промпт?** → [`prompt-engineering/SKILL.md`](./prompt-engineering/SKILL.md) + при сомнениях [`brex-prompt-engineering/REFERENCE.md`](./brex-prompt-engineering/REFERENCE.md).
5. **Парсишь русский?** → [`russian-nlp/SKILL.md`](./russian-nlp/SKILL.md).
6. **Правишь бота?** → [`aiogram-3/SKILL.md`](./aiogram-3/SKILL.md).
7. **Дёргаешь Groq?** → [`groq-tips/SKILL.md`](./groq-tips/SKILL.md).
8. **Создаёшь новый скилл?** → следуй [`skill-creator/SKILL.md`](./skill-creator/SKILL.md) + спека [Agent Skills](https://agentskills.io).

---

## Как использовать (для разработчика)

Открой нужный SKILL.md, прочти, **примени**. Если нашёл устаревшее / неверное — открой PR с правкой. Скиллы должны жить вместе с кодом, не залетать в архив.

---

## Размер каталога

```
.agents/skills/
├── CATALOG.md                          (этот файл)
├── README.md                           (вводный, что и зачем)
├── aiogram-3/SKILL.md                  ~6 KB
├── brex-prompt-engineering/            80 KB  (бандл)
│   ├── REFERENCE.md
│   ├── LICENSE
│   └── SOURCE.md
├── code-review/SKILL.md                ~5 KB
├── groq-tips/SKILL.md                  ~7 KB
├── mcp-builder/                        160 KB (Anthropic snapshot)
├── plan-app-internal/SKILL.md          ~7 KB
├── prompt-engineering/SKILL.md         ~7 KB
├── russian-nlp/SKILL.md                ~6 KB
├── skill-creator/                      280 KB (Anthropic snapshot)
├── webapp-testing/                     50 KB  (Anthropic snapshot)
└── writing-prs/SKILL.md                ~5 KB
```

Итого ~2.6 МБ после бандлинга anthropic/, obra/, voltagent/.
35+ SKILL.md файлов на момент 2026-05-09.

---

## Спецификация Agent Skills

Каждый SKILL.md имеет YAML-frontmatter:
```yaml
---
name: skill-name-kebab-case
description: Когда применять этот скилл (1–2 предложения).
---
```

Это позволяет инструментам типа Claude Code, Devin, OpenCode индексировать скиллы и предлагать их автоматически в нужный момент.

Полная спека: https://agentskills.io
