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
| `ponytail` (+ `ponytail-audit`, `ponytail-review`) | github.com/DietrichGebert/ponytail | MIT | «Ленивый сеньор»: YAGNI, stdlib-first, минимальный root-cause дифф. Юсуф просил применять ВСЕГДА |
| `emil-design-eng` (+ `review-animations`, `improve-animations`, `find-animation-opportunities`, `animation-vocabulary`, `apple-design`) | github.com/emilkowalski/skills | MIT | Скиллы Эмиля Ковальского: анимации, моушен-ревью, полировка UI. Применять при любой работе над webapp |
| `creator-vibe` | github.com/bish-x/creator-vibe | (лицензия не указана — используем как методичку, не вендорим) | Понимать интент Юсуфа за неидеальной формулировкой; «работает, но не радует» = не готово |

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
git clone --depth 1 https://github.com/DietrichGebert/ponytail.git
git clone --depth 1 https://github.com/emilkowalski/skills.git emil-skills
git clone --depth 1 https://github.com/bish-x/creator-vibe.git
cp -r gstack ~/.claude/skills/gstack
for s in taste-skill soft-skill redesign-skill minimalist-skill brandkit; do
  cp -r "taste-skill/skills/$s" ~/.claude/skills/"$s" 2>/dev/null
done
cp -r stop-slop ~/.claude/skills/stop-slop
cp -r impeccable/skill ~/.claude/skills/impeccable
for s in ponytail ponytail-audit ponytail-review; do
  cp -r "ponytail/skills/$s" ~/.claude/skills/"$s" 2>/dev/null
done
for s in emil-design-eng review-animations improve-animations find-animation-opportunities animation-vocabulary apple-design; do
  cp -r "emil-skills/skills/$s" ~/.claude/skills/"$s" 2>/dev/null
done
mkdir -p ~/.claude/skills/creator-vibe && cp creator-vibe/SKILL.md ~/.claude/skills/creator-vibe/SKILL.md
```

Дополнительно из ссылок юзера (пока НЕ установлены — поставить при надобности):
`github.com/multica-ai/andrej-karpathy-skills`, `github.com/mattpocock/skills`
(TS-инженерные паки — релевантны меньше для UI-полировки).
