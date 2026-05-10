---
name: lazyweb-design
description: Используй при дизайн-задачах в Mini-App (webapp/) — поиск UI-референсов в базе из 257k+ скриншотов реальных приложений через Lazyweb MCP. Применять перед любой нетривиальной правкой UI: выбор паттерна карточки задачи, layout календаря, onboarding, settings, etc.
---

# lazyweb-design

[Lazyweb](https://www.lazyweb.com/) — бесплатный MCP-сервер с базой
из 257k+ скриншотов реальных мобильных и web-приложений. Используем
для поиска UI-референсов до того, как лезть в Figma или гуглить.

## Когда применять

- Перед любой нетривиальной правкой UI в `webapp/` (TaskCard, Calendar,
  HorizonTabs, новые экраны).
- Когда нужны примеры паттернов: inline edit, swipe actions, FAB,
  bottom sheet, calendar grid, settings rows, onboarding.
- Когда юзер ссылается на «как у Todoist / TickTick / Amie / Akiflow».

**НЕ использовать** для backend, миграций, AI-промптов, логики.

## Установка в **новой** сессии Devin

> Каждая новая сессия Devin стартует с чистым окружением. Сам MCP
> у тебя НЕ подключён — ты ходишь в Lazyweb через прямой HTTP
> (см. ниже). Пошаговая «установка» = просто получить токен и
> положить его в env. Если в org-secrets уже есть
> `LAZYWEB_MCP_TOKEN` — `secrets.list filter=org` его покажет, и
> можно сразу использовать. Иначе:

```bash
# 1. Получить новый бесплатный токен (no billing, no auth needed):
TOKEN=$(curl -s -X POST https://www.lazyweb.com/api/mcp/install-token \
  -H "content-type: application/json" -d '{}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 2. Сохранить в env текущего шелла (для curl-вызовов ниже):
export LAZYWEB_MCP_TOKEN="$TOKEN"

# 3. Healthcheck:
curl -s -X POST https://www.lazyweb.com/mcp \
  -H "Authorization: Bearer $LAZYWEB_MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"lazyweb_health","arguments":{}}}' \
  | python3 -m json.tool
```

> Если эта **первая** сессия в org, которая использует Lazyweb —
> предложи юзеру сохранить токен как org-secret через
> `secrets.suggest_save(env_var_name="LAZYWEB_MCP_TOKEN", save_scope="org")`,
> чтобы будущие сессии не тратили на это время.

Токен низко-чувствительный (free, no billing), но не коммить
публично — анонимный bearer без rate-limit разъедет.

## Вызов через прямой HTTP (как мы делаем в plan-app)

В Devin нет нативного UI для добавления HTTP-MCP, поэтому в каждой
сессии вызываем напрямую через curl. `mcp_tool` тут не работает —
там нет лазивеба в `list_servers`. Используй curl:

```bash
# LAZYWEB_MCP_TOKEN должен быть уже в env после шага установки выше.
curl -s -X POST https://www.lazyweb.com/mcp \
  -H "Authorization: Bearer $LAZYWEB_MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"lazyweb_search","arguments":{
      "query":"task list inline edit white minimal mobile",
      "platform":"mobile",
      "limit":8
    }}
  }'
```

## Доступные инструменты

| Tool | Назначение |
| ---- | ---------- |
| `lazyweb_search` | Natural-language поиск. Args: `query` (str), `limit` (int, default 5), `platform` ("mobile"/"desktop"/null). |
| `lazyweb_compare_image` | Найти похожие на загруженную картинку. Args: `image_base64` или `image_url`. |
| `lazyweb_find_similar` | Похожие на конкретный screenshotId. |
| `lazyweb_list_categories` | Категории компаний. |
| `lazyweb_list_collections` | Куратские подборки (сейчас только `best-pricing-pages`). |
| `lazyweb_health` | Healthcheck. |

## Workflow для дизайн-задачи

1. **Сформулируй UX-проблему** одним предложением: "карточка задачи
   с inline-edit", "weekly calendar mobile minimal".
2. **Прогони 2-3 поиска** с разными формулировками (RU не работает —
   только en). Сохрани top-5 image URLs.
3. **Покажи юзеру ссылки** — пусть подтвердит, какие референсы
   нравятся. Не догадывайся вкус.
4. **Только потом меняй CSS/JSX**. Бери конкретные паттерны
   (spacing, typography, иконки) из референсов, не "по своему вкусу".

## Известные триггеры в plan-app

- **TaskCard** → `query="todoist task card mobile clean"`,
  фокус на checkbox + due-date pill + priority indicator.
- **Calendar** → `query="planner calendar weekly view mobile"`,
  смотрим Amie / Akiflow / Cal.com / Sunsama.
- **Empty state** → `query="empty state task app illustration"`.
- **Onboarding** → `query="todo app onboarding 3 screens"`.

## Anti-patterns

- ❌ Делать UI по описанию без визуальных рефов — кончится generic
  Material-look.
- ❌ Запускать поиск по-русски — индекс на английском.
- ❌ Брать только desktop-референсы, у нас mobile-first.
- ❌ Коммитить токен в git (`.cursor/mcp.json`, `secrets.json`,
  ENV-файлы).
