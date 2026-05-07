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

---

## Скиллы из `anthropics/skills` (бандл)

Снепшоты официальных скиллов Anthropic. Лицензия Apache 2.0. Источник + commit указаны в `SOURCE.md` каждой папки.

| Скилл | Применимость |
|---|---|
| [`skill-creator/`](./skill-creator/SKILL.md) | Когда создаёшь новый собственный скилл — следуй этому шаблону + spec. |
| [`mcp-builder/`](./mcp-builder/SKILL.md) | На будущее: если решим интегрировать MCP-серверы (Phase 5+). |
| [`webapp-testing/`](./webapp-testing/SKILL.md) | Phase 5: тестирование Telegram Mini App. |

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

Итого ~600 КБ. Норм.

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
