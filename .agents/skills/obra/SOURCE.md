# Источник

Скиллы из репозитория `obra/superpowers` — кураторская подборка
Jesse Vincent (бывший VP Engineering в GitHub / разработчик Perl /
maintainer git-related тулинга).

* **Репо:** https://github.com/obra/superpowers
* **Лицензия:** см. `LICENSE` в верхнем каталоге upstream-репо
  (на момент бандла — публичный репо без явной лицензии в `LICENSE`-файле,
  но README трактует контент как open-source). При сомнении —
  используй идеи как референс, а не дословно копируй.
* **Commit на момент бандла:** `f2cbfbefebbfef77321e4c9abc9e949826bea9d7`
* **Дата бандла:** 2026-05-09

## Что внутри

| Папка | О чём |
|---|---|
| `brainstorming/` | Перед любой творческой задачей: спецификация требований через AB-варианты. |
| `dispatching-parallel-agents/` | Запуск нескольких суб-агентов параллельно. |
| `executing-plans/` | Как методично выполнять план без срезания углов. |
| `finishing-a-development-branch/` | Когда всё готово — куда мержить, в каком порядке. |
| `receiving-code-review/` | Как принимать ревью без подхалимажа и слепой реализации. |
| `requesting-code-review/` | Как просить ревью у sub-agent / fresh chat. |
| `subagent-driven-development/` | Делегировать sub-agent'у целые этапы. |
| `systematic-debugging/` | **МАСТ-ХЭВ при любом баге**: root-cause перед фиксом. |
| `test-driven-development/` | Red → Green → Refactor дисциплина. |
| `using-git-worktrees/` | Параллельная работа над несколькими ветками без stash. |
| `using-superpowers/` | Стартовый: как находить и применять остальные скиллы. |
| `verification-before-completion/` | Перед заявлением «готово» — реальная верификация. |
| `writing-plans/` | Как писать план задачи, чтобы он был исполняемым. |
| `writing-skills/` | Как писать новый скилл (формат + чек-лист). |

## Главные жемчужины (читай первыми)

1. `using-superpowers/SKILL.md` — точка входа.
2. `systematic-debugging/SKILL.md` — единственный правильный способ
   ловить баги. Адаптация уже лежит в `../systematic-debugging/`.
3. `verification-before-completion/SKILL.md` — антидот к «работает
   на моей машине».
4. `test-driven-development/SKILL.md` — TDD-чек-лист, не догма.

## Как обновить

```bash
cd /tmp && git clone --depth 1 https://github.com/obra/superpowers.git
cp -r superpowers/skills/* .agents/skills/obra/
# обнови commit hash выше
```
