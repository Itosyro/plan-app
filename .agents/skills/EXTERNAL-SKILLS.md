# Внешние дизайн/качество скиллы (для Phase 7e и далее)

Эти скилл-паки установлены **глобально** в `~/.claude/skills/` (не в репо,
чтобы не раздувать клон тулингом и картинками). Контейнер веб-сессии
эфемерный — в новой сессии переустанови командой ниже, если они нужны для
UI-работы.

## Что и зачем

| Скилл | Репозиторий | Лицензия | Применять для |
|---|---|---|---|
| `gstack` (+ `design-review`, `design-consultation`, `design-html`, `ios-design-review`) | github.com/garrytan/gstack | MIT | Визуальный QA, дизайн-ревью с before/after скриншотами, headless-браузер для проверки Mini-App |
| `soft-skill` | github.com/Leonxlnx/taste-skill | MIT | «Дорогой» agency-уровень: тени, spacing, карточки, motion |
| `redesign-skill` | github.com/Leonxlnx/taste-skill | MIT | Апгрейд существующего UI без слома функциональности |
| `minimalist-skill` | github.com/Leonxlnx/taste-skill | MIT | Чистый editorial-минимализм, bento-сетки, без тяжёлых теней |
| `taste-skill` | github.com/Leonxlnx/taste-skill | MIT | Метрические правила вёрстки, компонентная архитектура, GPU-аккселерация CSS |
| `brandkit` | github.com/Leonxlnx/taste-skill | MIT | Брендовые борды/палитры (по необходимости) |
| `impeccable` | github.com/pbakaus/impeccable | Apache-2.0 | Аудит/полировка фронта: иерархия, IA, cognitive load, токены, анимации |
| `stop-slop` | github.com/hardikpandya/stop-slop | MIT | Чистка AI-штампов в текстах (PR-описания, UI-копи, docs) |

> **Важно:** эти скиллы дают *принципы* и инструменты. Наш дизайн —
> **свой**, Telegram-native (см. `webapp/DESIGN.md` после Workstream E
> плана 7e). Часть рекомендаций скиллов (напр., бан шрифта Inter в
> `soft-skill`) НЕ применяем — Inter намеренно используется, чтобы
> совпадать с клиентом Telegram. Берём из скиллов то, что усиливает
> Telegram/Mira-эстетику, остальное игнорируем.

## Переустановка в новой сессии (нужен egress к github.com)

```bash
mkdir -p ~/.claude/skills && cd /tmp && rm -rf _skills && mkdir _skills && cd _skills
git clone --depth 1 https://github.com/garrytan/gstack.git
git clone --depth 1 https://github.com/Leonxlnx/taste-skill.git
git clone --depth 1 https://github.com/pbakaus/impeccable.git
git clone --depth 1 https://github.com/hardikpandya/stop-slop.git
cp -r gstack ~/.claude/skills/gstack
for s in taste-skill soft-skill redesign-skill minimalist-skill brandkit; do
  cp -r "taste-skill/skills/$s" ~/.claude/skills/"$s" 2>/dev/null
done
cp -r stop-slop ~/.claude/skills/stop-slop
cp -r impeccable/skill ~/.claude/skills/impeccable
```

Дополнительно из ссылок юзера (пока НЕ установлены — поставить при надобности):
`github.com/multica-ai/andrej-karpathy-skills`, `github.com/mattpocock/skills`
(TS-инженерные паки — релевантны меньше для UI-полировки).
