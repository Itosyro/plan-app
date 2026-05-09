# Источник

Скиллы из официального репозитория Anthropic.

* **Репо:** https://github.com/anthropics/skills
* **Лицензия:** Apache 2.0 (см. `LICENSE.txt` в каждой подпапке)
* **Commit на момент бандла:** `f458cee31a7577a47ba0c9a101976fa599385174`
* **Дата бандла:** 2026-05-09

## Что добавлено в этот каталог

| Папка | Когда применять |
|---|---|
| `brand-guidelines/` | Если делаешь визуалку/брендинг для Mini App (Phase 5). |
| `claude-api/` | Если когда-нибудь будем дёргать Claude API напрямую (сейчас используем Groq). |
| `frontend-design/` | Phase 5: Mini App — production-grade UI без AI-щаблонности. |
| `web-artifacts-builder/` | Phase 5: сложные React/Tailwind/shadcn компоненты. |

## Что НЕ добавлено (намеренно)

* `canvas-design/` — 5.6 МБ шрифтов для постеров. Не нужно в Telegram-боте.
* `algorithmic-art/` — генеративная графика, не наша задача.
* `theme-factory/` — генеративные темы, не наша задача.
* `pdf/`, `docx/`, `pptx/`, `xlsx/` — работа с офисными форматами, не наша задача.
* `slack-gif-creator/`, `internal-comms/`, `doc-coauthoring/` — не наш use-case.

> Если когда-нибудь понадобится — клонируй из upstream и копируй в этот каталог.

## Как обновить

```bash
cd /tmp && git clone --depth 1 https://github.com/anthropics/skills.git
# выбери нужные папки и скопируй в .agents/skills/anthropic/
# обнови commit hash выше
```
