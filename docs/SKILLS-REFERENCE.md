# Skills & plugins reference (curated, sourced)

> Зачем этот файл: вместо слепого копирования сотен чужих скилл-файлов в репо
> (лицензии, мусор, bloat) — курированный, проверенный по лицензиям индекс
> официальных скиллов с командами установки. Будущие сессии читают этот файл
> и ставят нужное точечно. Проектные скиллы под plan-app лежат в
> `.claude/skills/` (их пишем сами, лицензий нет).
>
> Данные собраны ресёрч-агентом (июнь 2026), каждый пункт со ссылкой-источником.

## Формат и расположение скиллов (официально)

- Проектные скиллы: **`.claude/skills/<name>/SKILL.md`** (имя папки = имя
  `/команды`). Версионируются с репо, видны всем на `git pull`.
- Персональные: `~/.claude/skills/<name>/SKILL.md`.
- `SKILL.md` — markdown + YAML-frontmatter. Единственное по-настоящему важное
  поле — `description` (по нему Claude авто-вызывает скилл). Прочее опционально:
  `name`, `allowed-tools`, `disable-model-invocation`, `user-invocable`,
  `model`, `effort`, `context: fork`, `agent`, `paths`, `hooks`.
- Источник: [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)

## Наши проектные скиллы (в этом репо)

| Скилл | Что делает |
|---|---|
| `.claude/skills/gates` | Прогон всех гейтов (ruff/mypy/pytest + webapp tsc/build) как в CI |
| `.claude/skills/deploy-check` | Проверка прод-деплоя на Render: /healthz, какие модели живы, диагностика |

Добавляй сюда новые по мере надобности (например `release`, `e2e-miniapp`).

## Официальные коллекции (ставить точечно, НЕ вендорить целиком)

### Anthropic — `anthropics/skills` (Apache 2.0, кроме 4 doc-скиллов)
[github.com/anthropics/skills](https://github.com/anthropics/skills) — 17 скиллов.
**13 под Apache 2.0** (вендорятся свободно с NOTICE), **4 проприетарных**
(`docx`/`pdf`/`pptx`/`xlsx` — лицензия запрещает копирование, НЕ трогать).

Релевантное для Python+React+Telegram-бота (Apache 2.0):
| Скилл | Польза |
|---|---|
| `webapp-testing` | Playwright + Python, тестит фронт+бэк вместе — прямой фит |
| `frontend-design` | Качество React-компонентов, режет «generic AI» паттерны |
| `mcp-builder` | Если делать MCP-интеграции (FastMCP / TS SDK) |
| `claude-api` | Паттерны Anthropic SDK, кэширование, актуальные model-id |
| `doc-coauthoring` | PRD / RFC / decision-доки |
| `skill-creator` | Мета-скилл: писать новые скиллы |

Вендорить: скопировать папку скилла в `.claude/skills/<name>/` + положить рядом
`NOTICE` с URL-источником и «Apache-2.0, Copyright Anthropic PBC» (требование
лицензии).

### OpenAI — `openai/skills` (лицензия per-skill, проверять `LICENSE.txt`)
[github.com/openai/skills](https://github.com/openai/skills) — каталог для Codex.
Минимальный формат frontmatter (только `name` + `description`).
| Скилл | Польза |
|---|---|
| `gh-fix-ci` | Чинит упавшие GitHub Actions через CLI (есть Python-скрипт) |
| `gh-address-comments` | Автоответы на review-комментарии PR |
⚠️ У каждого свой `LICENSE.txt` — проверить перед вендором.

### obra/superpowers (MIT) — лучшая community-коллекция
[github.com/obra/superpowers](https://github.com/obra/superpowers) — принята в
официальный маркетплейс Anthropic (янв 2026), MIT, свободно вендорится.
14 скиллов: `test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `writing-plans`, `executing-plans`,
`dispatching-parallel-agents`, `using-git-worktrees`,
`subagent-driven-development`, `requesting/receiving-code-review` и др.
Прямо применимо к Python+React.

Установка как маркетплейс:
```bash
/plugin marketplace add obra/superpowers
```

## Плагины (ставить рантайм, НЕ вендорить JSON-реестр)

Официальный маркетплейс: [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official).
```
/plugin install github@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official      # Python LSP типы
/plugin install typescript-lsp@claude-plugins-official   # TS/React LSP
/plugin install sentry@claude-plugins-official           # когда подключим Sentry
```
Плагины с MCP-серверами / системными бинарями (LSP, GitHub, Sentry) — только
рантайм-установка, в репо не копируются.

## НЕ вендорить
- `docx`/`pdf`/`pptx`/`xlsx` из anthropics/skills — проприетарная лицензия.
- `VoltAgent/awesome-agent-skills` (1000+) — лицензия на уровне коллекции неясна.
- Любые community-наборы без явной MIT/Apache лицензии — аудит каждого перед копией.

---
_Источники: [Claude skills docs](https://code.claude.com/docs/en/skills),
[anthropics/skills](https://github.com/anthropics/skills),
[openai/skills](https://github.com/openai/skills),
[obra/superpowers](https://github.com/obra/superpowers),
[claude-plugins-official](https://github.com/anthropics/claude-plugins-official)._
