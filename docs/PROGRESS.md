# PROGRESS

Хронологический лог сделанного. Каждая запись = один PR.

Обновляй этот файл в каждом PR в самом конце, перед коммитом.

---

## 2026-05-11 — feat: soft-delete trash bin with 24h retention (PR-D)

Мягкое удаление задач и заметок вместо физического. Удалённые записи
остаются в БД 24 часа, после чего воркер вычищает их. Пользователь может
восстановить или удалить навсегда через страницу «Корзина» в настройках.

**Backend**
- `app/db/models.py` — добавлено поле `deleted_at: datetime | None` к моделям
  `Task` и `Note`.
- `alembic/versions/0009_soft_delete.py` — миграция: `ADD COLUMN deleted_at` +
  partial-индексы `ix_tasks_active`, `ix_notes_active` (`WHERE deleted_at IS NULL`)
  для быстрых горячих SELECT.
- `app/bot/services/tasks.py::delete_task` — `session.delete(task)` →
  `task.deleted_at = utcnow_naive()`. Зависимые `TaskEvent` и `Reminder`
  остаются (CASCADE сработает при физическом удалении воркером).
- `app/api/routers/notes.py::delete_note` — аналогично, soft-delete.
- Все SELECT-пути добавляют `.where(Model.deleted_at.is_(None))`:
  `list_tasks`, `task_counts`, `list_notes`, `get_note`, `patch_note`,
  `get_tasks_by_horizon`, `get_all_notes`, `get_categories_with_counts`,
  `find_task_by_query`, `get_task_by_id`.
- `app/workers/scheduler.py` — `tick_reminders` не шлёт напоминания для
  soft-deleted задач; новая функция `purge_trash()` физически удаляет записи
  старше 24 ч (вызывается в `main_async`).
- `app/api/routers/trash.py` (НОВЫЙ):
  - `GET /api/trash` — список soft-deleted задач/заметок юзера.
  - `GET /api/trash/counts` — кол-во удалённых по типу (badge в UI).
  - `POST /api/trash/{kind}/{id}/restore` — восстановление (`deleted_at = None`).
  - `DELETE /api/trash/{kind}/{id}` — физическое удаление из корзины.
- `app/api/schemas.py` — `TrashItemOut`, `TrashCountsOut`, `TrashKind`.
- `app/main.py` — подключен `api_trash` router на `/api/trash`.

**Frontend**
- `webapp/src/types.ts` — `TrashItem`, `TrashCounts`, `TrashKind`.
- `webapp/src/api/client.ts` — `trash()`, `trashCounts()`, `restoreTrashItem()`,
  `hardDeleteTrashItem()`.
- `webapp/src/lib/router.ts` — маршрут `/trash`.
- `webapp/src/components/TrashPage.tsx` (НОВЫЙ) — страница корзины с секциями
  «Задачи» / «Заметки», кнопками восстановления (RotateCcw) и удаления навсегда
  (Trash2), timestamp «X ч назад». Empty state при пустой корзине.
- `webapp/src/components/SettingsPage.tsx` — секция «Данные» с строкой «Корзина»
  (IconTile slate Trash2) + badge с количеством удалённых элементов. Тап →
  navigate("/trash").
- `webapp/src/App.tsx` — рендер `<TrashPage />` при `route.path === "/trash"`.

**Tests** (+ 7 новых, всего 338 passed)
- `test_soft_delete_filters_lists` — DELETE 204, списки пустые, строки в БД
  с `deleted_at`.
- `test_purge_after_24h` — `purge_trash()` удаляет записи старше 24 ч.
- `test_purge_ignores_recent` — свежие записи не трогает.
- `test_restore_idempotent` — второй restore → 404.
- `test_trash_lists_only_users_own` — ownership isolation в корзине.
- `test_trash_counts` — `GET /api/trash/counts` корректные значения.
- `test_hard_delete_from_trash` — физическое удаление через API.
- `test_delete_task_fk` — обновлён под soft-delete + CASCADE при purge.

---

## 2026-05-11 — feat(webapp): Notes tab — list/detail/create UI (PR-C)

Заметки как отдельный таб в Mini-App. До этого `Note` модель + GET-эндпоинт
существовали в коде, но фронт показывал только задачи. Теперь:

**Frontend**
- `webapp/src/components/BottomNav.tsx` — 4-я вкладка `Заметки` (StickyNote icon),
  тип `NavTab` расширен `"notes"`.
- `webapp/src/components/NoteCard.tsx` (НОВЫЙ) — минималистичная карточка
  (title + first-paragraph preview + tone-coded category chip). Тап → detail.
- `webapp/src/components/NotesList.tsx` (НОВЫЙ) — полноэкранный список с
  substring-поиском (`Найти в заметках…`), empty state, error fallback,
  кнопка `×` для очистки поиска. Refresh-signal проп — пересчёт при мутациях.
- `webapp/src/components/NoteDetail.tsx` (НОВЫЙ) — editable title + body
  (textarea, blur-to-save), tone-coded категория-строка (тап → BottomSheetSelect),
  rose-tone «Удалить заметку» с ConfirmDeleteSheet. Поддерживает два режима:
  `view` (загружает существующую через `apiClient.note(id)`) и `create`
  (черновые поля → на первом blur заголовка делает POST + navigate на `/note/{id}`).
- `webapp/src/components/Header.tsx` — новые опциональные пропы `onCreate` /
  `createLabel`; рендерит синий `+` FAB справа от фильтра.
- `webapp/src/lib/router.ts` — добавлены маршруты `/note/new` и `/note/:id`.
  Порядок маршрутов важен: `/note/new` перед `/note/:id`, иначе `:id` съест.
- `webapp/src/App.tsx` — `noteRoute` `useMemo` извлекает `{ kind: "create" }` или
  `{ kind: "view", noteId }`; `notesRefresh` state-счётчик; `handleOpenNote`,
  `handleCreateNote`, `handleNoteMutated`; рендер `<NoteDetail />` поверх всего
  при активном noteRoute; рендер `<NotesList />` когда `activeTab === "notes"`.
- `webapp/src/api/client.ts` — `notes()`, `note(id)`, `createNote()`, `patchNote()`,
  `deleteNote()`. С типами из `webapp/src/types.ts` — `NoteCreate`, `NoteUpdate`.

**Backend**
- `app/api/schemas.py` — `NoteCreateIn` (title 1-256, body 0-8192 optional,
  category_id optional) + `NoteUpdateIn` (все поля Optional; `body=""` чистит).
- `app/api/routers/notes.py`:
  - `POST /api/notes` → `201 NoteOut`. Валидация ownership категории.
  - `PATCH /api/notes/{id}` → `200 NoteOut`. Полевая валидация (паттерн
    `TaskUpdateIn`, никакого `setattr`-цикла).
  - Существующие `GET /api/notes`, `GET /api/notes/{id}`, `DELETE /api/notes/{id}`
    не тронуты.

**Tests** (+ 8 новых, все зелёные)
- `test_notes_create_minimal` — POST с одним title.
- `test_notes_create_with_body_and_category` — body + category_name резолвится.
- `test_notes_create_rejects_empty_title` — 422.
- `test_notes_create_404_on_foreign_category` — категория чужого юзера → 404.
- `test_notes_patch_title_and_body` — PATCH обоих полей.
- `test_notes_patch_clears_body_with_empty_string` — `body=""` → `body: None`.
- `test_notes_patch_404_for_other_user` — ownership-isolation.
- `test_notes_patch_rejects_unknown_field` — `extra="forbid"` 422.

**Preview / скриншоты**
- `webapp/dist/preview.html` — заметки добавлены в фикстуру `fixtures.notes`,
  fetch-mock поддерживает POST/PATCH/DELETE для `/api/notes`.
- Скриншоты light + dark: list, detail, category picker, create (empty +
  filled), delete confirm.

**Baseline** (на момент мерджа PR-C):
- `uv run pytest -q` — **331 passed**, **0 failures**.
- `uv run ruff format --check . && uv run ruff check . && uv run mypy app` — зелёные.
- `cd webapp && npm run typecheck && npm run build` — зелёные.
  Bundle: 252 KB JS (+14 от PR-B), 25 KB CSS (+1).

См. `docs/HANDOFF-2026-05-10-v14.md` — там детали для следующего PR-D.

---

## 2026-05-10 — feat(webapp): UX-итерация Mini-App — упрощённая шапка, detail page, кастомные пикеры (PR-B, PR #85)

Полный второй заход на UX: убрать болтливость карточек, спрятать массовые
«пилюли» под скролл, заменить нативные `<select>` на bottom-sheets и переехать
на нормальный detail page вместо встроенных кнопок. См. PR #85 (squash-merge).

**Главные шаги:**
- `webapp/src/components/Header.tsx` — упрощён до display-title + кнопка-фильтр.
  Подзаголовок выводит «Привет, X» на Tasks, или контекстную подсказку.
- `webapp/src/components/HorizonTabs.tsx` — `scroll-snap-x` rail, активная пилюля
  автоцентрируется (`scrollIntoView({ inline: "center" })`).
- `webapp/src/components/CategoryFilter.tsx` — теперь bottom-sheet (открывается
  кнопкой в шапке), а не блок над списком.
- `webapp/src/components/TaskCard.tsx` — снесены `Перенести / Удалить`
  inline-кнопки. Карточка тапается, открывая detail page; checkbox остался
  слева, drag-handle на long-press.
- `webapp/src/components/BottomNav.tsx` — фикс-ширина каждой вкладки, иконка
  сверху + label всегда видимый снизу, активный = tone-color, без анимации
  ширины.
- `webapp/src/components/SettingsPage.tsx` — все `<select>` заменены на
  `<BottomSheetSelect />` (tz, дайджесты, response_style, courier_template_style,
  critic_mode, week_due_semantic).

**Новые примитивы:**
- `webapp/src/components/BottomSheet.tsx` — базовый bottom-sheet с focus trap,
  ESC/backdrop dismissal, slide-up animation, ARIA-роли.
- `webapp/src/components/BottomSheetSelect.tsx` — listbox c радио-маркером, scroll.
- `webapp/src/components/BottomSheetDate.tsx` — пресеты «Сегодня / Завтра /
  +Неделя / Своя дата», тайм-инпут, «Убрать дату».
- `webapp/src/lib/router.ts` — мини hash-router без `react-router-dom`:
  `useRoute()` подписывается на `hashchange`, `navigate(path)` пишет в hash.
  Маршруты: `/`, `/task/:id`.
- `webapp/src/components/TaskDetail.tsx` — большой detail page (editable title +
  description, tone-coded строки Дата / Горизонт / Категория / Приоритет,
  rose-tone «Удалить задачу» с confirm-sheet).

**Backend** (минимальный сдвиг):
- `app/api/routers/tasks.py::patch_task` — теперь патчит `description` тоже
  (раньше клиент не имел способа сменить description через API). Поле в
  `TaskUpdateIn` уже было.

**Baseline после PR-B:**
- 323 passed, ruff/mypy/typecheck/build зелёные.
- Bundle: 238 KB JS, 24 KB CSS (рост ~+20 KB за счёт BottomSheet-семьи).
- main HEAD: `b366d25`.

---

## 2026-05-10 — docs: mega-review v3 после мерджа bento-редизайна (PR-A)

Полное ревью репо после мерджа PR #83. Результат — отчёт
`docs/REVIEW-2026-05-10.md` (~7k слов): сверка всех находок из трёх
предыдущих ревью (всё закрыто, кроме `_pluralize`-«элемент»), плюс
~16 новых пунктов сгруппированных под roadmap PR-B → PR-F.

Кода не правил — это аналитический PR. Финальный baseline:
- `uv run ruff format --check . && uv run ruff check . && uv run mypy app`
  все зелёные.
- `uv run pytest -q` — 323 passed.
- `cd webapp && npm run typecheck && npm run build` — зелёные,
  bundle 219KB JS / 20KB CSS.

Ключевые выводы для следующих PR-ов:
- **PR-B (UX-итерация):** упрощение шапки, спрятать Move/Delete за
  detail page, кастомный bottom-sheet picker вместо нативных `<select>`,
  bottom nav в стиле «иконка сверху + подпись снизу», новая страница
  деталей задачи (бекенд уже готов, только фронт).
- **PR-C (Заметки UI):** модель `Note` и `/api/notes` уже есть, нужен
  только новый таб в BottomNav + страница `NotesPage` + детальный
  экран. Плюс `DELETE /api/notes/{id}` (отсутствует).
- **PR-D (Корзина):** новая колонка `deleted_at` на Task/Note/Reminder
  + миграция, partial-индекс, переписать 6 SELECT-путей под фильтр,
  worker `purge_trash` (24h), новый роутер `/api/trash`, страница
  `TrashPage` внизу настроек.
- **PR-E (Бот):** `build_summary` отдаёт структуру вместо строки;
  каждое сообщение — обычный текст + inline-keyboard с
  `☐ → ✅` тогглами вместо «бирок-пинов»; переписать тексты в
  `courier_templates.py` дружелюбнее; новое опциональное поле
  `first_step` в `ClassifierResult` (фича «make it concrete»);
  настройка `concretize_tasks` на `UserSettings`.
- **PR-F (NLU + multi-provider):** перерайт `splitter.md` с ≥6
  негативными примерами + регресс-тест; абстракция `LLMKeyRouter[P]`
  на провайдера (Groq + OpenRouter), per-stage маршрутизация через
  env (`PLAN_LLM_SPLITTER_ROUTING=…`); 3-стадийный critic-chain
  (semantic / temporal / dedup) на разных моделях; ротация
  N OpenRouter аккаунтов с graceful fallback на Groq.

См. `docs/HANDOFF-2026-05-10-v13.md` — там полный контекст для
следующего агента (запрос юзера, мой разбор, ответы юзера, детальные
acceptance criteria по каждому PR).

---

## 2026-05-10 — feat(webapp): bento redesign foundation (WIP, branch `…-miniapp-bento-redesign`)

**Статус: незавершено.** На ветке `devin/1778436411-miniapp-bento-redesign`
лежит черновой коммит — фундамент под Apple-Bento редизайн Mini-App.
Юзер попросил остановиться раньше, чем мы дошли до TaskCard / Settings /
CategoryFilter / EmptyState. Никто не мерджит — это база для следующего
агента.

Что уже есть:
- `webapp/package.json`: добавлена зависимость
  `@fontsource-variable/inter@^5.2.8` — единый Variable-файл с `opsz`-осью,
  отдаёт и Inter Text (опт.размер 14), и Inter Display (опт.размер 32),
  с кириллическим subset'ом. Self-hosted, без Google Fonts CDN.
- `webapp/src/index.css`: полностью переписан. Импорт `opsz.css`,
  переменные `--bento-bg` / `--bento-card` (берут значения из Telegram
  theme + iOS-fallback `#F2F2F7`/`#FFFFFF`), глобальное
  `font-feature-settings: "cv11", "ss01", "ss03"` + `font-optical-sizing: auto`.
  Утилиты `.font-display` (opsz=32, letter-spacing -0.02em),
  `.tabular`, `.ease-spring`, `.ease-apple`.
- `webapp/tailwind.config.js`: расширен `fontFamily.sans` (Inter Variable
  во главе стека), добавлены токены цвета `bento` / `bento-card`,
  borderRadius `2.5xl`/`4xl`, boxShadow `bento`/`bento-lg`/`island`.
  Цвет `tg-secondary` теперь по умолчанию `#f2f2f7` (был `#f4f4f5`),
  `tg-hint` — `#8e8e93` (iOS systemGray) вместо `#6b7280`.
- `webapp/src/components/IconTile.tsx` (НОВЫЙ): примитив для цветной
  rounded-square плашки с lucide-иконкой. 11 тонов
  (violet/indigo/blue/sky/teal/emerald/amber/orange/rose/pink/slate),
  3 размера (sm/md/lg). Tailwind видит литеральные имена классов
  через `TONE_BG`-словари → ничего не теряется при tree-shake.
- `webapp/src/components/BottomNav.tsx`: floating-island как на
  референсе Mira. Полупрозрачный bento-card фон, `backdrop-blur-xl`,
  `shadow-island`, `ring-1 ring-black/5`, активный таб — `bg-tg-button/10`
  с `text-tg-button`. Лейбл показывается только на активном табе.
  `transition-all duration-300 ease-apple active:scale-[0.96]`.
- `webapp/src/components/Header.tsx`: переписан — крупный display-заголовок
  (`font-display text-[28px]`), под ним hint-subtitle. Поддержан опц.
  пропс `greeting` (для будущего «Доброе утро, …»).
- `webapp/src/components/HorizonTabs.tsx`: pills с tone-coded активным
  состоянием (`HORIZON_TONE`: today=orange, tomorrow=amber, week=violet,
  month=indigo, year=blue, someday=slate). Активный pill — tinted
  background соответствующего тона + ring + shadow. Inactive — белая
  карточка с `ring-1 ring-black/5`. Бейдж счётчика — tabular-nums.

Что НЕ переделано (и нужно следующему агенту):
- `TaskCard.tsx` — старый стиль `rounded-2xl bg-tg-secondary/60`.
- `CategoryFilter.tsx` — старые пилюли с border'ами.
- `SettingsPage.tsx` — старый секционный layout, без icon-tile'ов.
- `EmptyState.tsx` — крупный emoji + текст, без bento-карточки.
- `App.tsx` — общий padding/spacing страницы.

Tests: 323 passing (как до правок — никаких python-изменений).
`npm run typecheck && npm run build` — зелёные. Bundle размер
+~120KB сырых woff2 (cyrillic+latin subsets), ~270KB уже сжатого
не считаем — браузер тянет только нужный subset.

См. `docs/HANDOFF-2026-05-10-v12.md` — там детали и пошаговый план.

---

## 2026-05-10 — Phase 8b: slash-команды для quick-input + Render keep-alive (PR #82)

Цель — закрыть две вещи одним PR'ом:
- **Quick-input через слэш-команды** (план §8b): `/add /done /del
  /move /postpone` — чтобы юзер мог писать `/done молоко` без
  открывания Mini-App.
- **Cold-start на Render Free**: если 15 минут не было трафика,
  dyno засыпает, и при открытии Mini-App юзер видит экран
  «Render запускает приложение…» на 30-60 секунд. Прокидываем
  GitHub Actions cron-ping каждые 10 минут.

Что сделано:
- `app/bot/routers/commands.py`: 5 новых хендлеров + парсер
  `parse_horizon` (HORIZON_ALIASES в RU/EN: сегодня/today,
  завтра/tomorrow, неделя/week, …) + `parse_move_args` (split
  args на query+horizon, validate). Обновлён `HELP`.
- `app/bot/routers/_pipeline.py`: вынесен `enqueue_text_pipeline`
  helper — общий код между catch-all-text и `/add` (одинаковый UX:
  reaction ack, ⏳ placeholder, streaming reply, success/error).
- `app/bot/routers/text.py`: остался тонкий wrapper, дёргает
  `enqueue_text_pipeline`. Сократился с 162 до 35 строк.
- `app/bot/courier_templates.py::HELP`: переписан, секция
  «⚡ Быстрый ввод» с новыми командами.
- `.github/workflows/keepalive.yml` (НОВЫЙ): cron `*/10 * * * *`,
  curl на `/healthz` и `/app/`. Concurrency-group `keepalive`,
  не cancel-in-progress, timeout 3 мин. Manual dispatch разрешён.
- `tests/test_commands.py`: +13 тестов (parse_horizon round-trip,
  Russian aliases, case-insensitivity, parse_move_args edge-cases,
  service-composition для done/del/move через find_task_by_query,
  cross-user isolation).
- `tests/test_voice_router.py`: обновлены docstring'и и assertions
  (читаем `_pipeline.py`, не `text.py`).

Tests: 323 → 334 passing, ruff/mypy clean, webapp build OK.

---

## 2026-05-10 — fix(reminders): «напомни в 12» actually creates a reminder row (PR #79)

Три бага в одном пользовательском сценарии («напоминания не работают»):

1. **`в 12` без минут не парсился** — `_TIME_PATTERNS` требовал
   `в HH:MM`, поэтому самая частая русская формулировка «обед в 12»
   возвращала `ResolvedTime=None`, и в БД ложилась задача без `due_at`.
2. **`ResolvedTime.is_reminder=True` никем не читалось** — поле
   существовало с Phase 2.2, но в pipeline никто на него не ветвился.
3. **`offset=0` фильтровалось как `<= 0`** — и в `_select_reminder_offsets`,
   и в `schedule_reminders`. Канонический «напомни ровно в 12:00»
   (offset=0 = «fire AT due_at») уезжал в /dev/null.

Что сделано:
- `app/ai/time_resolver.py`: добавлен `_BARE_HOUR_PATTERNS` —
  нормализация `в 12` / `в 12 часов` → `в 12:00` ДО основной таблицы
  замен (lookahead защищает от dotted-dates типа `в 12.05`). Расширен
  `_TIME_PATTERNS` под голое `в HH` и `в HH часов`. Расширен
  reminder-detector до `\b(?:напомн|напомина)` — теперь существительное
  «напоминание» тоже триггерит `is_reminder=True`.
- `app/bot/services/tasks.py::_select_reminder_offsets`: явный `[0]`
  сохраняется, дедупликация, отрицательные дропаются. Defaults
  по-прежнему по `> 0` (там `0` — мусор).
- `app/bot/services/tasks.py::schedule_reminders`: `offset == 0`
  создаёт строку с `fire_at == due_at`. Только negative дропаются.
- `app/bot/routers/_pipeline.py::_run_pipeline_inner`: если
  `resolved.is_reminder`, `cr.is_task`, `due_at` есть и классификатор
  не дал явных `reminder_offsets` — синтезируем `[0]` через
  `cr.model_copy(update=...)`.
- 8 новых тестов: 5 в `test_time_resolver.py` (`в 12`, `в 8`,
  «в 12 часов», noun-form `напоминание`, защита от `в 12:30`),
  3 в `test_reminders.py` (`offset=0`, `[0,30]`, drop negatives).
  Обновлён `test_select_offsets_drops_non_positive` под новый
  контракт (новое имя: `test_select_offsets_drops_negative_keeps_zero`).

Tests: 315 → 323 passing, ruff/mypy clean.

---

## 2026-05-10 — Phase 7c: Settings page в Mini-App (PR #78)

Заменили `<ComingSoon>`-плейсхолдер на вкладке «Настройки»
работающим экраном.

- `app/api/schemas.py`: новые `MeUpdateIn`, `UserSettingsUpdateIn`,
  `TimezoneOut`. Все поля опциональные, `extra="forbid"` на Pydantic.
- `app/api/routers/me.py`: добавлен `PATCH /api/me`. Валидация tz
  через `is_valid_timezone`, значений settings — через
  `ALLOWED_SETTING_VALUES` (allow-list). Возвращает свежий `MeOut`.
- `app/api/routers/timezones.py` (новый): `GET /api/timezones` —
  отдаёт `POPULAR_TIMEZONES` из `app/bot/onboarding.py`.
- `app/main.py`: `include_router` для нового роутера.
- `webapp/src/types.ts`: типы `UserSettingsUpdate`, `MeUpdate`, `Timezone`.
- `webapp/src/api/client.ts`: `apiClient.patchMe()`, `apiClient.timezones()`.
- `webapp/src/components/SettingsPage.tsx` (новый, 552 LOC): секции
  «Основные» (имя + tz), «Дайджест» (утро/вечер), «Ответы бота»
  (источник + тон), «Поведение» (критик + неделя). Стилистика
  Phase 7b: white palette, lucide-иконки, `rounded-2xl`, без рамок.
  Inline-редактирование имени и tz (popular dropdown + «указать
  другой»), select-row для остальных. Per-field pending state.
- `webapp/src/App.tsx`: вкладка `settings` теперь рендерит
  `<SettingsPage me={me} onUpdated={setMe} />`.
- 9 новых API-тестов в `tests/test_api_endpoints.py`.

Все мутации settings идут через тот же `update_user_settings`-сервис,
что и `/settings`-callbacks бота — две поверхности байт-идентичны.

Bundle: 202 → 213.95 KB raw / 65.6 → 68.31 KB gzip.

Tests: 306 → 315 passing, ruff/mypy clean.

---

## 2026-05-10 — Phase 7b: Mini-App design polish (PR #74)

Pure visual polish, никаких новых API/БД/бизнес-логики.

- Подключён `lucide-react@^0.460.0` (+~4 KB gzip, tree-shake
  работает: импортируем 11 иконок, бандл вырос только на это).
- Новый `webapp/src/lib/icons.ts` — централизованный mapping:
  `horizonIcon(slug)` → `Sun` / `Sunrise` / `CalendarDays` /
  `Sunset`; `priorityFlagColor(p)` → tailwind-цвет для `Flag`.
- Новый `webapp/src/components/BottomNav.tsx` — плавающая
  капсула с 3 табами (Задачи / Календарь / Настройки). Активный
  таб с лейблом, неактивные icon-only. Haptic-feedback при
  переключении. Только Tasks реально работает; Календарь/
  Настройки рендерят `ComingSoon` placeholder.
- Новый `webapp/src/components/ComingSoon.tsx` — minimal empty-
  state с иконкой + заголовком + описанием. Используется для
  не-готовых табов.
- `TaskCard.tsx` переписан под lucide: `Check` (галка в
  чекбоксе), `Clock` (due_at), `Flag` (priority high/low —
  medium-задачи флаг скрывают), `Move` / `Trash2` (action-row).
  Карточка теперь rounded-2xl с фоном `bg-tg-secondary/60` и
  `active:bg-tg-secondary` вместо border.
- `HorizonTabs.tsx`: leading icon перед лейблом; активный pill
  solid dark (`bg-tg-text` / `text-tg-bg`) вместо прежнего
  `bg-tg-button`.
- `Header.tsx`: упрощён до `План` h1 + `display_name` справа;
  убрана подпись «Привет, X 👋».
- `App.tsx`: добавлено `activeTab` state; Tasks tab рендерит
  существующий flow; Calendar/Settings tabs → `ComingSoon`.
  paddingBottom +5rem чтобы последняя карточка не уходила под
  плавающий bottom nav.
- Палитра НЕ изменена — оставлена белая Telegram-theme через
  CSS-переменные (--tg-theme-bg-color и т.д.).

Bundle: 193 → 202 KB raw / 62 → 65.6 KB gzip.

Tests: 306 passing (без новых — pure visual), ruff/mypy clean.

---

## 2026-05-10 — Phase 7a: bot onboarding redesign (PR #73)

- Новый `app/bot/onboarding.py` — `POPULAR_TIMEZONES` (12 пар
  Russian-label + IANA-tz: Москва / Минск / Киев / Калининград /
  Ереван / Тбилиси / Алма-Ата / Ташкент / Бишкек / Екатеринбург /
  Новосибирск / Владивосток), `tz_keyboard()`, `label_for_iana()`,
  `parse_tz_callback()`. Callback-формат `onb:tz:<iana>` или
  `onb:tz:custom`.
- `app/bot/routers/start.py`: новый callback-handler
  `onb_tz_callback`. `cmd_start` теперь шлёт inline-keyboard.
  FSM-state `Onboarding.timezone` сохранён как fallback (юзер тапает
  «Указать другой ✏️» → бот просит IANA в свободном тексте).
- Re-onboarding shortcut: если у user уже есть `display_name`,
  тап по новой tz-кнопке обновляет `user.tz` и пропускает
  повторный запрос имени. `complete_onboarding()` идемпотентен,
  поэтому существующие `UserSettings` не теряются.
- `app/bot/courier_templates.py`: переписаны короче — greeting,
  ask-name, ask-custom-tz, done, re-onboarding. Старый
  `ONBOARDING_BAD_TZ` сохранён как alias для backward compat.
- +10 unit-тестов (`tests/test_onboarding.py`):
  `test_popular_timezones_all_iana_valid`, `test_popular_timezones_no_duplicates`,
  `test_tz_keyboard_layout`, `test_tz_keyboard_callback_data_under_64_bytes`,
  `test_label_for_iana_*`, `test_parse_tz_callback_*`,
  `test_re_onboarding_preserves_name_and_settings`.
- Новый skill `.agents/skills/lazyweb-design/SKILL.md` — будущие
  сессии Devin самостоятельно установят Lazyweb MCP (curl
  install-token) и будут юзать его для UI-design references.

Tests: 296 → 306, ruff/mypy clean.

---

## 2026-05-09 (поздно вечер) — Phase 5.4b: drag-n-drop reorder

Добавлен `@dnd-kit/core@6.3` (38 КБ gzip → итоговый bundle 63 КБ).
В Mini-App теперь можно перенести задачу между горизонтами драг-н-дропом
без открытия меню «Перенести».

UX:
- Long-press на карточке задачи (250 мс) → drag activates →
  карточка приподнимается с тенью и кольцом обводки.
- При наведении на pill горизонта pill подсвечивается ring-2.
- Drop → optimistic update + PATCH (`horizon_slug`) +
  refresh counts.
- Tap < 250 мс на «Готово» / «Перенести» / «Удалить» работает как
  раньше (PointerSensor с `activationConstraint: { delay: 250 }`).
- На done-задачах drag отключен (`disabled: isDone`).

Реализация:
- `App.tsx`: `<DndContext sensors={sensors} onDragEnd={handleDragEnd}>`
  оборачивает весь main view. `handleDragEnd` валидирует `over.id`
  по allow-list горизонтов, нет ли совпадения с текущим, и зовёт
  `handleMove`.
- `TaskCard.tsx`: `useDraggable({ id: task.id })` →
  ref/listeners/attributes на корневой div + transform style.
- `HorizonTabs.tsx`: каждый pill вынесен в `<HorizonPill>` чтобы
  иметь свой `useDroppable({ id: slug })` ref.

Tests: 296 passing, ruff/mypy clean, webapp build green.

---

## 2026-05-09 (вечер, после 6.x) — Phase 5.4a: counts endpoint

`GET /api/tasks/counts` возвращает счётчики открытых задач по всем
горизонтам одним запросом. Schema: `TaskCountsOut` с шестью
полями-горизонтами (`today/tomorrow/week/month/year/someday`) +
`no_horizon` для legacy/notes-likes тасок. `done` и `cancelled`
исключены — они живут в архивных flow-ах, не в списке.

Реализация:
- SQL: один `GROUP BY horizons.slug` с outer join, чтобы тасочки без
  горизонта не пропадали тихо.
- Маршрут зарегистрирован **до** `/{task_id}` иначе FastAPI пытается
  скастовать `"counts"` в int → 422.
- Frontend (`webapp/`): `apiClient.taskCounts()`, `loadCounts()` в
  `App.tsx`, рефреш после каждой mutation (done/move/delete). Pill-табы
  HorizonTabs теперь показывают живые цифры рядом с названием горизонта.
- 3 новых интеграционных теста в `tests/test_api_endpoints.py`:
  group-by, auth required, cross-user isolation.

Тесты: 293 → **296 passing**, ruff/mypy clean, webapp build green.

---

## 2026-05-09 (вечер) — Phase 6.1-6.4 + ops: prod migrations + auto-deploy

**Phase 6.1 Reactions (PR #66):** `app/bot/reactions.py` — bot
ставит 👀 на полученное сообщение, 🎉 на успех, 😢 на ошибку
через `setMessageReaction` (Bot API 7.0+). Allow-list эмодзи,
best-effort: ошибки Telegram не валят пайплайн. 7 unit-тестов.

**Phase 6.2 Quote replies (PR #67):** `app/bot/quote_replies.py`
+ `app/bot/streaming.py`. Ответ бота прикрепляется к user
message с tap-to-jump стрелкой через `reply_parameters.quote`
(Bot API 7.0+). `safe_quote()` проверяет, что фрагмент
действительно substring оригинала (Telegram возвращает
`QUOTE_TEXT_INVALID` иначе). 7 unit-тестов.

**Phase 6.3 Pinned morning digest (PR #69):**
`app/bot/pinned_today.py`. Утренний дайджест пинится в чате,
в течение дня live-обновляется через `editMessageText` при
mark-done (callback ИЛИ Mini-App PATCH). Migration 0008
добавляет `pinned_morning_chat_id`/`message_id`/`date` на
`user_settings`. App.state.bot для cross-router доступа в
API. 7 unit-тестов.

**Phase 6.4 CloudStorage (PR #68):** `webapp/src/lib/storage.ts`
— unified async storage поверх `WebApp.CloudStorage` с откатом
на `localStorage`. Mini-App запоминает `last_horizon` /
`last_category` между сессиями и между Telegram-клиентами.

**Прод-операция:**
- **Migrations 0002-0008 накатаны на Neon** (раньше прод был
  на 0001, тiлько 5 базовых таблиц существовали; 7 таблиц из
  Phase 2-6 отсутствовали).
- **Render `startCommand`** обновлён до
  `uv run alembic upgrade head && uv run uvicorn ...` —
  изменение и в `render.yaml`, и в живом Render service через
  API. Свежие деплои теперь авто-мигрируют, дрифт
  невозможен.
- Удалены legacy Render services plan-bot и plan-api.

**Тесты:** 286 → 293 passing (+7 от 6.3).
ruff/mypy clean. CI green на всех 4 PR-ах.

**Доки:** `docs/HANDOFF-2026-05-09-v9.md`,
`docs/ROADMAP.md` (Phase 5 → DONE 5.1-5.3 / NEXT 5.4+,
Phase 6 → DONE по 4 фичам, Phase 7 → polish).

**Из Bot API 10.0 пользователь явно отказался от:** Stars,
Business Mode, Biometric auth — отложены в будущее.

**Что дальше:** Phase 5.4 (counts endpoint, drag-n-drop
reorder, calendar/kanban view).

---

## 2026-05-09 — Phase 5: Telegram Mini App + streaming bot replies

**Бэкенд (REST API под `/api/*`):**

* `app/api/auth.py` — middleware `current_user`: HMAC-SHA256
  верификация `X-Telegram-Init-Data` (Telegram WebApps spec, ключ
  `HMAC-SHA256("WebAppData", bot_token)`), отбрасывает скомпрометированные/
  устаревшие подписи (TTL 24 ч + grace), возвращает `User` через
  FastAPI Depends.
* `app/api/schemas.py` — Pydantic v2 модели (`TaskOut`, `NoteOut`,
  `CategoryOut`, `MeOut`, `TaskUpdateIn`, …) с `extra="forbid"` —
  никаких лишних полей в ответах/запросах.
* `app/api/routers/` — `me`, `tasks`, `notes`, `categories`,
  `horizons`, `inbox`. CRUD через переиспользование существующих
  bot-сервисов (`mark_task_done`, `update_task_horizon`,
  `update_task_category`, `delete_task`) — единый аудит-trail
  и общий код side-effect-ов между Mini-App и ботом.
* `app/main.py` — подключение роутеров, `StaticFiles` mount под
  `/app`, `setChatMenuButton(MenuButtonWebApp(...))` при старте
  (новинка из Bot API 10.0).
* `app/shared/config.py` — `Settings.miniapp_url` (deriv-property
  от `webhook_base_url`, override через `MINIAPP_URL_OVERRIDE`).

**Фронт (`webapp/`, React 18 + Vite 5 + Tailwind 3 + TypeScript):**

* Маленький, todoist-style mobile-first UI: горизонты как
  pill-табы (Сегодня / Завтра / Неделя / …), ниже — горизонтальный
  фильтр категорий, потом — карточки задач с круглым checkbox,
  цветным priority-индикатором, сроком и actions «Перенести / Удалить».
* `lib/telegram.ts` — тонкая обёртка над `window.Telegram.WebApp`:
  `WebApp.ready()`, `expand()`, applyTheme (через CSS vars
  `--tg-theme-*`), HapticFeedback, listener на `themeChanged`.
* `api/client.ts` — fetch-обёртка с авто-инжектом `X-Telegram-Init-Data`,
  типобезопасными вызовами и `ApiError` для ненулевых статусов.
* Optimistic UI: «Готово» / «Перенести» / «Удалить» сразу видны,
  при ошибке — откат через перезагрузку списка.
* Build-output `webapp/dist/` монтируется FastAPI как статика.

**Streaming-replies в боте (Bot API 10.0 «as-typed»):**

* `app/bot/streaming.py` — `stream_reply(placeholder, full_text, …)`:
  отправляем bubble-плейсхолдер сразу, потом построчно editText
  (rate-limit-aware: ловим `TelegramRetryAfter`, периодический
  `sendChatAction("typing")`).
* `app/bot/routers/text.py` и `voice.py` — переключены на
  `stream_reply` вместо одного `message.answer(reply)`.
  Пользователь видит ответ как будто бот печатает сейчас.

**Инфра:**

* `Dockerfile` — multi-stage (Node 20 → Python 3.12), фронт билдится
  один раз и копируется в финальный образ. В dev без билда
  StaticFiles mount просто отключается (`if WEBAPP_DIST.exists()`).
* `.github/workflows/ci.yml` — джоба `webapp build` (typecheck + build).
* `tests/test_api_auth.py` (8 тестов) — happy / bad signature /
  expired / future skew / empty / no user.
* `tests/test_api_endpoints.py` (15 тестов) — happy paths + 401 /
  404 / cross-user 404 для каждого endpoint.
* `tests/test_streaming.py` (4 теста) — progressive reveal,
  single-line, RetryAfter, empty.
* `tests/test_static_miniapp.py` (2 теста) — smoke `/app/` →
  `index.html` с `#root` + Telegram WebApp script.

Тесты: 272 passed (+29 новых). ruff / mypy: clean.

---

## 2026-05-09 — Plan audit + ROADMAP refresh + HANDOFF v8 (docs only)

**PR** — обновление планировочных документов после полного
аудита кода против изначальных планов
(`plan-python-detailed.md`, `docs/PLAN.md`, `ROADMAP.md`,
`ARCHITECTURE.md`).

* `docs/PLAN.md` — добавлен Status-блок в начало (фазы 0..4
  done, Phase 5 не начат, Phase 6 частично).
* `docs/ROADMAP.md` — все фазы 0..4 помечены ✅ DONE с
  деталями. Phase 4 — описано отклонение от плана (вместо
  отдельного Render Cron сделан in-process scheduler в web-сервисе).
  Phase 5 — детальный breakdown на 5.1..5.6. Phase 6 —
  что есть и что осталось.
* `docs/HANDOFF-2026-05-09-v8.md` (NEW) — мега-handoff на
  ~700 строк для следующего агента: super-review-first
  стратегия, поиск новых скиллов, multi-PR autonomous
  execution, грабли проекта, workflow для каждого PR,
  карта моделей, quick-reference. Цель — чтобы следующий
  агент использовал все 100% лимита сессии и закрыл много
  работы за раз без подтверждений.

**Не меняли:** код, тесты, миграции, prod config.

---

## 2026-05-09 — Important findings I-1..I-6, I-8 closed (PR #61)

**PR #61** — закрыты 7 из 8 Important findings из `docs/REVIEW-2026-05-09-v2.md`
одним коммитом-на-фикс в одной ветке. (I-7 уже был в PR #57.)

* **I-1** (`7bab98d`) — `parse_task_callback()` в `app/bot/routers/callbacks.py`.
  Все 7 callback-хендлеров теперь делают `try/except ValueError` через общий
  парсер вместо unguarded `int(parts[N])`. Битые/злоумышленные payloads
  отвечают «Неверный формат.» вместо 500.
* **I-2** (`e6d9a6d` + `82ae938`) — `get_or_create_category` /
  `get_or_create_horizon` через `INSERT ... ON CONFLICT DO NOTHING` (Core SQL,
  обходит ORM). Конкурентные webhook-доставки с одинаковыми category names
  больше не падают на UNIQUE-constraint. Работает и в Postgres, и в SQLite.
* **I-3** (`bb65899`) — `complete_onboarding` теперь делает SELECT-then-INSERT
  для `UserSettings`. Re-onboarding после `/start` больше не крашит на
  `UserSettings.user_id` PK. Существующие пользовательские настройки
  (`critic_mode`, `morning_digest_at`) сохраняются.
* **I-4** (`656a878`) — `tick_digests` использует catch-up семантику:
  fire when `local_now >= scheduled_time and not last_*_digest_on=today`.
  Дайджест больше не теряется при tick drift > 60 с (Render cold-start, GC
  pause). Day-1 safeguard: пользователь, онбординг которого закончился
  *после* slot-time сегодня, не получает мгновенно «доброе утро» в 21:00.
* **I-5** (`f542ef4`) — claim-pattern в `tick_reminders`. Атомарный
  `UPDATE ... SET status='processing' WHERE status='pending' AND id=:id`
  плюс per-row commit. Crash mid-batch (SIGTERM/OOM) больше не приводит к
  duplicate-sends на следующем tick. Stuck `processing`-rows требуют ручной
  triage — задокументировано.
* **I-6** (`f6f5c72`) — `/today` (и siblings: `/tomorrow`, `/week`, ...)
  теперь шлёт **одно** сообщение вместо N+1 (1 summary + N task rows).
  Inline-keyboard с 4 emoji-only кнопками на задачу (`N ✅ N 🔄 N 🗑 N 🏷`),
  page cap 20 задач. Callback_data unchanged — все хендлеры работают
  без изменений.
* **I-8** (`9ccf7ea`) — `asyncio.Semaphore` backpressure вокруг `run_pipeline`:
  per-user limit = 1 (строгая сериализация), global limit = 8.
  Pipeline contention логируется. Pipeline body вынесен в `_run_pipeline_inner`
  для тестируемости.

Тесты: **243 passed** (было 217 → +26: 7 для I-1, 5 для I-2, 1 для I-3,
6 для I-4, 3 для I-5, 4 для I-6, 7 для I-8). ruff format + ruff check + mypy
clean. Squash-merge без миграций.

Прод после мержа: https://plan-app-t6nx.onrender.com/healthz → деплой
auto-triggered.

**НЕ закрыто в этой сессии (для следующего агента):**
* Все Minor `M-1 .. M-9` из v2 review.
* Phase 5 (mini-app) — не начат.

---

## 2026-05-09 — Skills bundle expansion + полный merge train

**PR #60 (этот)** — расширение `.agents/skills/` для будущих агентов.
**PR'ы #50..#59** — все смержены в main (см. предыдущую запись).

* Добавлен `.agents/skills/voltagent/` — кураторская подборка из
  [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)
  (20K+ stars, MIT, commit `6f804f0c`). 26 .md файлов под наш стек:
  python-pro, fastapi-developer, sql-pro, code-reviewer,
  architect-reviewer, debugger, error-detective, qa-expert,
  test-automator, security-auditor, performance-engineer,
  postgres-pro, database-optimizer, ai-engineer, llm-architect,
  prompt-engineer, backend-developer, api-designer, frontend-developer,
  fullstack-developer, docker-expert, database-administrator,
  security-engineer, devops-incident-responder, refactoring-specialist,
  documentation-engineer.
* Добавлен `tg-bot-api/SKILL.md` — выжимка по актуальной (Bot API 10.0,
  8 мая 2026) Telegram Bot API: что есть, что используем, что НЕ
  используем, наши гочки G-1..G-10 для бота, ссылки на core.telegram.org/bots/api.
* Добавлен `python-best-practices/SKILL.md` — 12 секций конкретных
  правил для Python в этом проекте: async/await, типы (нет Any/getattr),
  Pydantic v2, SQLAlchemy 2.0 async, pytest async, ruff/mypy, uv,
  structlog, naive UTC, security, perf, CI.
* Полностью переписан `docs/PROMPT-FOR-NEXT-SESSION.md`: 730+ строк
  вместо 400. Главные правила первыми (в т.ч. «ты делаешь всё сам:
  мержишь, пушишь, обновляешь docs»), ASCII-диаграмма архитектуры,
  workflow A/B/C/D для разных типов задач, расширенные грабли
  (G-1..G-18), шаблоны HANDOFF и PR описаний, контрольные чек-листы.
* Обновлён `.agents/skills/CATALOG.md`: добавлены строки для новых
  custom skills и целая новая секция voltagent/ (5 подкатегорий).
* Создан `docs/HANDOFF-2026-05-09-v6.md` (этот хэндофф).
* CI: ruff format + check clean, mypy 0 errors, **217 tests passed**.
* Прод после мержа: https://plan-app-t6nx.onrender.com/healthz → 200 OK.

Размер `.agents/skills/`: ~600 КБ → ~2.6 МБ. SKILL.md файлов: 17 → 35+.

---

## 2026-05-09 — Super-review v2: 6 critical findings closed

**PRs #50 .. #58** — глубокое второе ревью поверх первого + фиксы.

* **PR #50** — `docs/REVIEW-2026-05-09-v2.md`. 14 новых находок:
  6 critical, 8 important, 9 minor. Каждая critical с repro.
  Документация — без кода.
* **PR #51** — промежуточный `HANDOFF v4` (черновик).
* **PR #52 — C-5: webhook idempotency TOCTOU race.**
  `mark_update_processed` теперь делает атомарный INSERT и ловит
  `IntegrityError` вместо паттерна SELECT-then-INSERT. Параллельные
  webhook-запросы с одинаковым `update_id` больше не попадают на 500
  (и Telegram перестаёт retry'ить).
* **PR #53 — C-1: settings UI `split(":")` parser.**
  `cb_settings_set` теперь использует `parse_set_callback`, который
  делает `split(":", 3)` — `"settings:set:morning_digest_at:08:00"`
  парсится правильно. Все 8 кнопок утреннего/вечернего времени в
  `/settings` снова работают.
* **PR #54 — C-4: classifier user_categories.**
  `_pipeline.run_pipeline` подгружает существующие категории через
  `get_user_categories` и передаёт их в классификатор. Дубли вида
  «Работа / работа / Рабочее» больше не плодятся.
* **PR #55 — C-6: voice handler reminder offsets.**
  Voice-handler грузит `default_reminder_offsets` из `UserSettings`,
  как text-handler. Голосовые юзеры получают свои reminder presets,
  а не глобальный default.
* **PR #56 — C-2: time-resolver «сегодня в HH:MM».**
  `+7d` rollover больше не срабатывает, если в исходном тексте
  явно сказано «сегодня/сейчас/today». «во вторник» во вторник
  по-прежнему уезжает на следующий вторник.
* **PR #57 — C-3 + I-7: ON DELETE policies (alembic 0007).**
  `delete_task` больше не FK-violate'ит на Postgres. Migration
  `0007_fk_on_delete_policies` ставит CASCADE / SET NULL на ВСЕ
  FK-констрейнты (`task_events.task_id`, `reminders.task_id`,
  `*.user_id`, soft-references). Модели обновлены так, что
  `create_all` в тестах тоже производит CASCADE — позволяет
  писать тесты с `PRAGMA foreign_keys = ON`.
* **PR #58** — `docs/HANDOFF-2026-05-09-v5.md` + обновление этого
  PROGRESS-файла.

Тесты: **207 passed** (был 204; +13 новых регрессий — webhook race,
settings keyboard round-trip, classifier categories, voice reminder
offsets, time-resolver «сегодня», delete_task FK).

**НЕ закрыто в этой сессии (для следующего агента):**
* Important `I-1 .. I-6`, `I-8` из v2 review.
* Все Minor `M-1 .. M-9` из v2 review.
* Phase 5 (mini-app) — не начат.

См. `docs/REVIEW-2026-05-09-v2.md` для полного списка
и `docs/HANDOFF-2026-05-09-v5.md` для рекомендованного порядка
работы.

---

## 2026-05-09 — M-4: drop format_exc_info + code review cleanup

**PR #49** — M-4 + code review fix.

1. **M-4** — Drop `format_exc_info` from structlog processor chain.
   - **Root cause**: When `configure_logging()` is not called before test
     code, structlog falls back to defaults — Rich's `ConsoleRenderer`
     with `show_locals=True`. Rich inspects all local variables in
     traceback frames; `InstructorRetryException` carries references to
     `AsyncGroq` / `httpx` transports whose repr hangs indefinitely.
   - **Fix (a)**: `tests/conftest.py` now calls `configure_logging()` at
     module level so structlog never uses the Rich default.
   - **Fix (b)**: `app/shared/logging.py` — removed `format_exc_info`
     from the processor chain; `ConsoleRenderer` now uses
     `structlog.dev.plain_traceback` (stdlib-based, no `show_locals`).
   - All 204 tests pass. No warnings, no hangs.

2. **Code-review fix**: `app/ai/router.py` — replaced
   `getattr(exc, "status_code", None)` with direct `exc.status_code`
   access (type-safe; `APIStatusError.__init__` sets the attribute).

Tests: **204 passed**. Lints / mypy clean.

---

## 2026-05-09 — M-6 + M-3: per-user time anchors + services split

**PR #47** — два коммита:

1. **M-6** — `UserSettings.morning_anchor` / `evening_anchor` (HH:MM strings).
   - Alembic migration `0006` — two `String(5)` columns with `server_default`.
   - `time_resolver.py::resolve_time()` accepts `morning_anchor` / `evening_anchor` kwargs;
     `_preprocess()` overrides the static «утром»=09:00 / «вечером»=19:00 replacements.
   - Wired through `_pipeline.py → text.py / voice.py` from `UserSettings`.
   - 2 new tests: `test_vecherom_custom_anchor`, `test_utrom_custom_anchor`.

2. **M-3** — split `app/bot/services.py` (739 LOC) into `app/bot/services/` package:
   - `users.py` — User CRUD + onboarding
   - `inbox.py` — InboxEntry + TelegramUpdate idempotency
   - `settings.py` — UserSettings queries, mutations, allow-lists
   - `tasks.py` — Task/Note/Category/Horizon CRUD + classification + reminders
   - `ai.py` — AiRun logging
   - `__init__.py` re-exports all public names → zero changes to import sites.

Tests: **204 passed** (202 + 2 new). Lints / mypy clean.

---

## 2026-05-09 (вечер) — Snapshot после I-fixes + 5/8 Minor: pause + handoff v2

**Контекст:**
После snapshot-PR #44 юзер согласовал план «закрыть все 7 Important
findings одним PR с отдельными коммитами и пушить по мере готовности
для раннего CI feedback». В одной сессии сделаны и Important, и
половина Minor. Сейчас работа поставлена на паузу: юзер попросил
зафиксировать состояние, написать мега-handoff v2 для следующей
нейросети (детальнее v1) и не продолжать M-6 / Phase 5 без
согласования.

**Сделано в этой части сессии:**

PR #45 — **Fix Important findings I-1..I-7** (squash-merged в main как
`1036145`, 6 коммитов независимы и читаемы):

  - **I-5** (`f059505`): удалён dead code `app/ai/reminder_extractor.py`
    + `tests/test_reminder_extractor.py` (160 LOC прода + 5 тестов).
    Был superseded `time_resolver` + `classifier.due_at` ещё в
    Phase 2.4, но остался в репо.
  - **I-6** (`4d19068`): убрал `parse_mode="Markdown"` из 4 callback'ов
    в `app/bot/routers/settings.py`. Категории и task labels —
    user-controlled, любая будущая категория с `*`/`_`/`[`/`` ` ``
    сломала бы Telegram parser. Плюс regression-test
    `test_settings_panel_no_markdown_parse_mode`.
  - **I-7** (`4d233a0`): `webhook.received` теперь populates
    `TelegramUpdate.user_id`. Был лукап `User.id` по `telegram_id`
    в `_persist_telegram_update`. До этого все строки в таблице
    `telegram_updates` имели `user_id=NULL` — не аналитическое
    табло, а просто баг. Плюс 2 теста в `tests/test_webhook.py`.
  - **I-4** (`8e0baad`): извлёк `_get_router`, `_log_task_exception`,
    `_run_pipeline` из `app/bot/routers/text.py` в новый модуль
    `app/bot/routers/_pipeline.py` под публичными именами
    (`get_groq_router`, `log_task_exception`, `run_pipeline`).
    `voice.py` и `text.py` теперь оба импортят из `_pipeline`.
    Никаких приватных импортов между братскими модулями. `text.py`
    усох с 289 LOC до 121.
  - **I-1** (`d6acf91`): оживил `GroqKeyRouter.advance()`. Добавил
    `call_with_rotation[T](router, fn)` хелпер в `app/ai/router.py`,
    обернул им все 6 Groq call-site'ов (splitter / classifier /
    critic / courier / reorder / whisper). На `RateLimitError` и
    `InternalServerError` / 5xx `APIStatusError` — `router.advance()`
    и retry. На 4xx — propagate. Если все ключи в пуле упали —
    `GroqKeysExhaustedError`. 6 новых тестов в
    `tests/test_groq_router.py` (success / 429 / 5xx / 4xx /
    pool-exhaust / unexpected). Используется PEP-695 generic-syntax
    `[T]` (Python 3.12+).
  - **I-2** (`0ae8af6`): включил mypy в CI на `app/`. Починил все
    30 предсуществующих ошибок: aiogram-3 `InaccessibleMessage`
    narrowing (`isinstance(callback.message, Message)` вместо
    `is not None`) в callbacks.py — 7 мест; `# type: ignore[union-attr]`
    → `[attr-defined]` в services.py (где речь шла о SQLModel
    column expressions); `zi: ZoneInfo | timezone` annotation в
    `time.py` и `digest.py` (Python `UTC` — это `timezone`, не
    `ZoneInfo`); типизированный `scheduler_handle:
    tuple[asyncio.Task[None], asyncio.Event] | None` в `main.py` —
    убрал `# type: ignore[arg-type]`. В `pyproject.toml` —
    `[tool.mypy] files = ["app"]` (тесты с моками сейчас не покрыты).
    В `.github/workflows/ci.yml` — шаг «Mypy (app/)» между ruff и
    pytest.

I-3 (README refresh) был сделан раньше в snapshot-PR #44 / `bdeb884`.

PR #45 итог: 197 → 202 теста (+5 чистых; I-1 +6, I-7 +2, I-6 +1,
I-5 −5, M-3/M-6 не трогаем). mypy 0 errors. ruff чисто. CI ✅
(ruff + mypy + pytest). Squash-merge в main.

PR #46 (in-flight, not merged) — **Minor cleanup**, ветка
`devin/1778320409-minor-fixes`, 5 коммитов из 8 запланированных:

  - **M-1 + M-2** (`9135e47`): выпилил `pymorphy3`, `razdel`,
    `asyncpg` из `[project] dependencies` в `pyproject.toml`.
    `pymorphy3` и `razdel` — никогда не импортились (только в
    `russian-nlp/SKILL.md`). `asyncpg` напрямую противоречил
    `app/db/base.py::_to_async_url`, который явно нормализует на
    `+psycopg`. `uv.lock` усох на 6 транзитивных deps.
  - **M-5** (`3c885cd`): заменил `getattr(logging, ...)` на
    explicit `_LOG_LEVELS` mapping в `app/shared/logging.py`. Это
    был последний `getattr` в `app/` (по
    `defensive-programming/SKILL.md` style).
  - **M-7** (`055a946`): обогащён docstring пустого
    `app/api/__init__.py`. Поясняет что namespace зарезервирован
    под Phase 5 mini-app JSON API. Без code change.
  - **M-8** (`44e2ef5`): починен медленный тест
    `test_e2e_partial_classify_failure_does_not_kill_batch`.
    2.78s → 1.54s. Mock-ответ для классификатора #2 поменян с 429
    на 400 — Groq SDK не делает internal retries на 4xx,
    `call_with_rotation` тоже propagate'ит 4xx сразу. Test intent
    («один classifier failed → survivor is persisted») сохранён.

  - **M-3** (services.py 723 LOC split на 5 модулей): **отложен**
    в отдельный PR. Слишком большой для cleanup-PR, риск
    сломать import surface в десятке других модулей.
  - **M-4** (drop `format_exc_info` из structlog chain): **отложен**.
    Удаление вызывает hang в
    `test_e2e_partial_classify_failure_does_not_kill_batch`
    (повторяющиеся retry-loop'ы в groq SDK + структура chained
    exceptions). Пока в `app/shared/logging.py` оставлен с
    NB-комментарием. Корневая причина не до конца понята — нужно
    разбираться отдельно.
  - **M-6** (morning_anchor / evening_anchor settings + Alembic 0006):
    **отложен**. Требует миграции и 2 тестов; следующая нейросеть
    может это закрыть как отдельный коммит в этом же PR или новым
    PR.

PR #46 НЕ замерджен. Ветка `devin/1778320409-minor-fixes` запушена
с 5 коммитами; следующая нейросеть может либо доделать M-3/M-4/M-6,
либо смерджить как-есть с пометкой о неполноте, либо закрыть PR
без мерджа.

**Итог сессии:**
- 2 PR'а в main (`1036145` = I-fixes; PR #44 = snapshot/handoff)
- 1 PR in-flight на `devin/1778320409-minor-fixes` (5 of 8 minor)
- Тестов: 202 (стабильно зелёных)
- mypy: 0 errors (теперь гейтит CI)
- ruff: чисто
- Открытые findings: M-3, M-4, M-6 (3 Minor) + Phase 5

**Артефакты для следующего агента:**
- `docs/HANDOFF-2026-05-09.md` (v1, post-PR #44, актуален до момента
  открытия PR #45) — высокоуровневый обзор
- `docs/HANDOFF-2026-05-09-v2.md` (v2, **этот snapshot**, 700+ строк) —
  мега-детальный передаточный документ для следующей нейросети,
  включая:
    - точное состояние main (SHA, тесты, mypy)
    - PR #46 in-flight: каждый коммит, что сделано / что отложено
    - детальный разбор каждого M-fix (включая deferred с root cause)
    - конкретные команды для возобновления работы
    - архивный список секретов / git workflow / CI / уроки

---

## 2026-05-09 — Snapshot после мерджа PR #42 + #43 + handoff для следующей нейросети

**Контекст:**
В этот день была долгая сессия: сначала Phase 4c (PR #40), потом
супер-ревью (PR #42, документ-only) с 22 находками (3 Critical / 7
Important / 8 Minor / 6 Positive). Юзер дал команду закрыть все
3 Critical в одном PR с отдельными коммитами на каждый баг и пушем
после каждого, чтобы CI отстреливал ошибки рано. Это и было
сделано в PR #43.

**Сделано:**
- PR #42 (super-review docs, `a54bedf`) и PR #43 (C-1/C-2/C-3 fixes,
  `5702605`) squash-merged в `main`, ветки удалены.
- Создан `docs/HANDOFF-2026-05-09.md` (~600 строк) — единый snapshot
  для передачи проекта другой нейросети: TL;DR, история всех фаз,
  детальное описание трёх фиксов (что был баг, какой был симптом,
  как починили), список из 7 Important + 8 Minor открытых находок,
  env-инструкции (uv, secrets, git workflow с PAT), тестовый базис
  по файлам, чек-лист «первые 30 минут».
- Обновлён `README.md`: вывод из «Phase 0 — placeholder» в актуальное
  состояние «Phase 4c-fixed, 197 tests, prod live».

**Состояние main после мерджа:**
- `uv run pytest -q` → **197 passed** (172 база + 5 Phase 4c +
  3 C-1 + 13 C-2 + 4 C-3).
- `uv run ruff format --check` чисто, `uv run ruff check` чисто.
- 5 Alembic миграций (последние две — 0004 `courier_template_style`
  и 0005 `digest_idempotency_guards`).
- `app/` 4422 LOC, `tests/` 4473 LOC, 23 тест-файла.

**Что починено в этой сессии:**
- **C-1** (`1d26374`) — `response_style_source` vocab fix:
  UI шёл `formal/casual/mix`, courier ждал
  `template_only/llm_only/mix` → 2 из 3 кнопок «Стиль ответа» были
  мертвы. Плюс новый сеттинг `courier_template_style`
  (тон шаблона, 6 опций — был захардкожен в `"neutral"` в
  text.py:239 и voice.py:68). Alembic 0004 + UPDATE legacy
  `formal/casual → template_only`. +3 теста.
- **C-2** (`6ca9d41`) — `Task.due_at` UTC normalisation:
  `dateparser` отдавал aware-MSK, SQLAlchemy дропал tz при insert →
  naive-MSK в naive-UTC колонке. Новый
  `app/shared/time.format_due_local()` рендерит naive-UTC в HH:MM
  в локальной TZ юзера; `to_naive_utc()` нормализует `due_at` перед
  persist. Все 4 display-сайта обновлены. +13 тестов
  (новый файл `tests/test_shared_time.py`).
- **C-3** (`f647415`) — digest double-send guard:
  `tick_digests` без guard'а задвоил бы дайджест при
  `SCHEDULER_TICK_INTERVAL_SECONDS < 60`. Добавлены колонки
  `last_morning_digest_on` / `last_evening_digest_on` (date NULL),
  гвард по user-local дате. Alembic 0005. +4 теста.

**Не сделано (вынесено за рамки):**
- 7 Important и 8 Minor находок из ревью — отложены до следующего PR.
- Phase 5 (mini-app) — следующий блок, разблокирован починкой C-2.

---

## 2026-05-09 — Super-review всего репо перед Phase 5

**Контекст:**
Юзер попросил сделать «супер-ревью» всего проекта по чек-листу из
`.agents/skills/code-review/SKILL.md` перед тем как стартовать Phase 5
(mini-app). Прошлое мега-ревью было 2026-05-08
(`docs/REVIEW-findings.md`, PR #37) — все его C/I пункты починены и
закрыты. Этот PR — **только документ с новыми находками**, никакого
production-кода не правит.

**Сделано:**
- Прогнал по всем 10 категориям из `code-review/SKILL.md`: соответствие
  плану, архитектура, БД/миграции, AI-код, безопасность, качество кода,
  тесты, документация, UX, перформанс.
- Собрал findings в `docs/REVIEW-2026-05-09.md` в стиле
  `docs/REVIEW-findings.md`: severity ladder C-x / I-x / M-x / P-x,
  каждая запись с `path:line` ссылками и конкретным fix-sketch'ем.
- Verifications прогнал: `uv run ruff format --check` чисто,
  `uv run ruff check` чисто, `uv run pytest -q` → 177 passed,
  `uv run mypy app` → **35 errors в 9 файлах** (I-2).

**Сводка findings (всего 22):**
- **3 Critical**:
  - **C-1** — `response_style_source` setting silently inert: UI шлёт
    `formal/casual/mix`, courier ждёт `template_only/llm_only/mix` →
    две из трёх кнопок не работают, `courier_style` захардкожен в
    `"neutral"` в обоих роутерах.
  - **C-2** — `Task.due_at` хранится в local-time юзера, а не в UTC
    (dateparser возвращает aware-MSK, SQLAlchemy strip'ит tz при
    insert'е → naive-MSK в naive-UTC колонке). `Reminder.fire_at`
    защищён через `_to_naive_utc`, `Task.due_at` — нет.
  - **C-3** — `tick_digests` может задвоить отправку, если
    `SCHEDULER_TICK_INTERVAL_SECONDS` < 60 секунд: нет ни
    `last_morning_digest_on`, ни эквивалента
    `Reminder.status='pending'→'sent'` гварда.
- **7 Important**: `GroqKeyRouter.advance()` нигде не вызывается (key
  rotation мёртв), mypy не в CI и даёт 35 ошибок, `voice.py` импортит
  `_get_router` / `_run_pipeline` / `_log_task_exception` из `text.py`,
  `app/ai/reminder_extractor.py` — dead code, доки протухли (README в
  Phase 0, HANDOFF в 172 passed, `.env.example` рекомендует +asyncpg
  при том что код требует +psycopg), `parse_mode="Markdown"` ещё в
  `settings.py` (пока безопасно, но fragile), `record_update` всегда
  пишет `user_id=None`.
- **8 Minor**: unused deps (pymorphy3, razdel, asyncpg), services.py
  723 LOC, structlog warning про format_exc_info, единственный
  `getattr` в `app/shared/logging.py`, hard-coded `вечером`/`утром` в
  `time_resolver`, `app/api/__init__.py` пустая папка-заглушка, slow
  test (2.78s).
- **6 Positive**: naive-UTC discipline, parse_mode discipline,
  allow-list validation, reminder retry/failure semantics, double-secret
  webhook idempotency, fast & isolated tests.

**Верификация:**
- `uv run ruff format/check` — чисто (документ-only PR).
- `uv run pytest -q` — 177 passed без регрессий.

**Не сделано (вынесено за рамки PR):**
- Сами правки кода — это следующий PR (или серия PR), порядок
  предложен в `docs/REVIEW-2026-05-09.md::Suggested fix order`. Юзер
  решит, какие findings берём в работу первыми.
- Phase 5 (mini-app) ждёт пока починим C-1/C-2/C-3 — иначе они
  всплывут в JSON-API.

---

## 2026-05-09 — Phase 4c: e2e-тесты сквозной цепочки сообщение → Task → Reminder → Digest

**Контекст:**
В `main` 172 теста — каждый компонент покрыт изолированно: пайплайн
(`test_e2e_pipeline.py`), persist→Reminder (`test_reminders.py`), tick
(`test_scheduler.py`), digest (`test_digest.py`), runner-loop (`test_runner.py`).
Не было теста, который сшивает их воедино: пользовательское сообщение
становится Task'ом, Task порождает Reminder, scheduler его шлёт, тот же Task
позднее показывается в утреннем дайджесте. Этот PR закрывает пробел.

**Сделано:**
- `tests/test_e2e_phase4.py` (новый файл, 351 LOC) — пять сценариев:
  - `test_full_chain_persist_then_reminder_then_morning_digest` — основной поток:
    `persist_classification` → 2 `Reminder` (default `same_day = [60, 15]`) →
    `tick_reminders(now=naive_due)` отправляет оба сообщения FakeBot'у →
    `build_morning_digest` всё ещё включает открытый Task.
  - `test_morning_digest_tick_isolated_by_user_timezone` — два онбордженных
    юзера в `Europe/Moscow` и `America/New_York` с одинаковым `morning="08:00"`;
    в `05:00 UTC` это `08:00 MSK` (match) и `01:00 EDT` (no match) — `tick_digests`
    шлёт ровно одному (Москве).
  - `test_morning_digest_excludes_tasks_completed_after_persist` — задача,
    переведённая в `status='done'` после `persist_classification`, выпадает
    из `build_morning_digest`.
  - `test_reminder_marked_failed_after_max_attempts_then_skipped` — три провала
    подряд (`MAX_REMINDER_ATTEMPTS=3`) переводят `Reminder.status='failed'`;
    последующий тик с восстановившимся ботом не трогает «мёртвую» строку.
  - `test_reminder_send_uses_plain_text_no_markdown_parse_mode` — регрессия
    C-2 из `defensive-programming/SKILL.md`: title с `*` / `_` / `[` уходит
    plain-text'ом; в `bot.send_message(...)` нет `parse_mode`, символы
    сохраняются дословно.
- Хелперы в файле: `_RecordingBot` (захватывает все kwargs, включая
  `parse_mode`), `_classifier_result` фабрика, `_onboard_user` (run
  `complete_onboarding` + override digest slots).

**Верификация:**
- `uv run ruff format .` — чисто
- `uv run ruff check .` — чисто
- `uv run pytest -q` — **177 passed** (172 + 5 новых, без регрессий)

**Не сделано (вынесено за рамки PR):**
- Не пишем «полный e2e через `_run_pipeline` + respx-моки Groq» — это
  заметно раздуло бы тесты и продублировало `test_e2e_pipeline.py` (там
  уже 8 респ-ксенарев). Phase 4c специально про звено
  `persist → reminder → digest`, а не «message → persist» (его уже хватает).
- Phase 5 (Telegram Mini App) и сбор скиллов под mini-app SDK — отдельные PR.

---

## 2026-05-08 — Snapshot: Phase 4 закрыта, перед Phase 4c делаем sanity-check + handoff

**Контекст:**
Юзер попросил остановиться, сверить текущее состояние с детальным планом
(`docs/PLAN.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`) и подтвердить, что
мы движемся в нужном направлении. Этот PR — только документация: фиксируем
актуальное состояние и обновляем `docs/HANDOFF.md` под следующего AI-агента.

**Где мы сейчас (2026-05-08, после `b79dce8`):**

- **Smoke / lint / test:** `uv run ruff format/check` чисто, `uv run pytest -q` —
  **172 passed**.
- **main:** `b79dce8 Phase 4: skills bundle — 5 new SKILL.md (#38)`.
- **Деплой:** один Render Free web-service. `app/workers/runner.py` крутит
  `tick_reminders` + `tick_digests` каждые 60 сек прямо в FastAPI-процессе;
  `/healthz` пинается извне (cron-job.org / GitHub Actions cron) — см.
  `docs/RENDER.md`. Cron-сервис из `render.yaml` удалён, апгрейд до Starter+
  описан в комментарии того же файла.

**Карта по фазам (что в `main`):**

| Фаза | Статус | Где смотреть |
|---|---|---|
| Phase 0 / 0.5 (cleanup + skills) | done | PR #3, `41b43c8` |
| Phase 1 (webhook + БД + onboarding) | done | PR #6 |
| Phase 1.5 (CI: ruff + pytest) | done | PR #7 |
| Phase 4 (early: deploy + e2e живого бота) | done | PR #8–#11 |
| Phase 2.1 (Splitter + GroqKeyRouter + instructor) | done | PR #12, #13 |
| Phase 2.2a (Classifier + time_resolver + reminder_extractor) | done | PR #14 |
| Phase 2.2b (DB models + persist) | done | PR #17 |
| Phase 2.3a (Whisper voice) | done | PR #18 |
| Phase 2.3b (Critic) | done | PR #19 |
| Phase 2.3c (Courier) | done | PR #21 |
| Phase 2.3d (Reorder голосом) | done | PR #23 |
| Phase 2 e2e (8 сквозных тестов) | done | PR #25 |
| Phase 3a (view-команды `/today` … `/categories`) | done | PR #27 |
| Phase 3b (inline-кнопки на карточке задачи) | done | PR #28 |
| Phase 3c (`/settings`) | done | PR #29 |
| Phase 3 finish (4-я кнопка + tz/reminder в /settings) | done | PR #31 |
| Code review + skills (early) | done | PR #33 |
| **Phase 4a** (Reminder model + миграция + persist) | done | **PR #34** |
| **Phase 4b** (Scheduler + Digest + render.yaml cron) | done | **PR #35** |
| **Render fix** (in-process scheduler, free-tier) | done | **PR #36** |
| **Mega review** (C-1, C-2, I-1, I-2 + REVIEW-findings.md) | done | **PR #37** |
| **Skills bundle** (5 новых SKILL.md + CATALOG) | done | **PR #38** |
| **Этот PR** (snapshot + HANDOFF) | in-flight | docs only |

**Что НЕ сделано (в порядке приоритета):**

1. **Phase 4c — e2e тесты для дайджеста + reminders end-to-end** (следующее).
   Существующие тесты покрывают компоненты по отдельности (172 шт.):
   `test_e2e_pipeline.py` — message → task; `test_scheduler.py` — reminder
   tick; `test_digest.py` — digest tick; `test_runner.py` — loop lifecycle.
   Пробел: нет тестов всей цепочки «сообщение пользователя → task в БД →
   reminder сработал → задача появляется в morning digest».
2. Phase 5 (Telegram Mini App — React + Vite + Tailwind, 3 вкладки).
3. Phase 6 (наблюдаемость, эвалы, DSPy).
4. M-1..M-5 из `docs/REVIEW-findings.md` (webhook idempotency race, asyncio
   strong-ref, прочее) — низкий приоритет, можно в Phase 6.

**Соответствие детальному плану (sanity-check vs `docs/PLAN.md`):**

- §2.1 (утренний поток мыслей) — пайплайн split → time → classify → critic →
  persist + courier-reply работает (Phase 2.1–2.3 + e2e PR #25).
- §2.2 (заметки) — `Note` модель есть, persist различает task/note (Phase 2.2b).
- §2.3 (напоминание из текста) — extractor + reminder_offsets + Reminder model
  работают (Phase 4a).
- §2.4 (перестановка задач голосом) — `app/ai/reorder.py` + `update_task_horizon`
  (Phase 2.3d).
- §2.5 (утренний/вечерний дайджест) — `build_morning_digest`/`build_evening_digest`
  + `tick_digests` строгий HH:MM матч (Phase 4b).
- §2.6 (ручной ввод/редактирование) — view-команды + inline-кнопки + /settings
  (Phase 3a/b/c).
- §2.7 (Mini App) — отложено в Phase 5.
- §4 (стиль курьера) — courier_templates + LLM 50/50, настраивается в /settings
  (Phase 2.3c).

Главные сценарии из `PLAN.md` покрыты по коду; не покрыты по интеграционным
тестам — это и есть Phase 4c.

**Не сделано (вынесено за рамки этого PR):**
- Phase 4c (отдельный PR от следующего агента).
- Перевыкладка bot, проверка боевого пинга `/healthz`.

---

## 2026-05-08 — Skills bundle: 5 новых SKILL.md (PR C)

**Контекст:**
После mega-review (PR B) добавляем недостающие методички в `.agents/skills/`, чтобы в будущих сессиях агент сразу видел паттерны, которые мы вычистили в PR B, и не повторял те же ошибки. Цель — закрыть пробелы в существующем бандле, не дублируя то, что уже есть.

**Сделано:**
- `.agents/skills/systematic-debugging/SKILL.md` — адаптация из [obra/superpowers](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) (MIT). Iron Law «no fixes without root cause», 4 фазы (root cause → pattern → hypothesis → fix), red flags, антипаттерны. Внизу — таблица plan-app-specific симптомов и где искать (Markdown 400, naive-UTC, idle spin-down, dateparser «во вторник», Groq 429 в тестах, `kind=Update`).
- `.agents/skills/defensive-programming/SKILL.md` — выжимка из `docs/REVIEW-findings.md`. 10 правил, каждое с конкретным кейсом из репо: allow-list (I-1), parse_mode discipline (C-2), naive-UTC (C-1), idempotency guard (M-1), LIKE-escape, callback-data parse, HH:MM matcher, exception isolation в loop, PII в логах, type-checker. Чек-лист в конце.
- `.agents/skills/testing-async-python/SKILL.md` — паттерны из существующих 172 тестов: pytest-asyncio (`asyncio_mode = "auto"`), in-memory SQLite, `now=...` параметр вместо monkeypatch, `respx.mock` для Groq, `FakeBot.sent`, SQLite vs Postgres квирки, что НЕ тестировать (aiogram-роутеры, live Groq), верификация перед push, типичные ошибки.
- `.agents/skills/migrations-safely/SKILL.md` — Alembic + SQLModel: iron rule «models.py change ↔ alembic revision in same PR», как читать autogenerate (false-positives), безопасный column drop (2-step), не-nullable + `server_default`, JSON-колонки, naive-UTC `DateTime`, локальное round-trip тестирование, prod rollback, антипаттерны.
- `.agents/skills/using-uv/SKILL.md` — cheat-sheet: `uv sync --frozen`, `uv add`, `uv lock --upgrade-package`, `uv run`, что коммитить (`uv.lock`), Python 3.12 pinning, Docker prod-install с `--no-dev`, частые ошибки CI (out-of-date lockfile, missing module).
- `.agents/skills/CATALOG.md` — обновил таблицу custom-скиллов: добавил 7 новых строк (5 новых + 2 ранее не залистанных: `requesting-code-review`, `socraticode-principles`).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто (никаких code-изменений, только Markdown).
- `uv run pytest -q` — 172 passed (без регрессий).
- Все 5 новых SKILL.md имеют валидный YAML-frontmatter (`name` + `description`) — проверено вручную.

**Не сделано (вынесено за рамки PR):**
- Reload `mcp-builder/` snapshot — текущая версия Anthropic-снэпшота достаточна для Phase 5.
- Скиллы для Phase 5 (Telegram Mini App / Web frontend) — отложены, будут добавлены вместе с фронтом.

---

## 2026-05-08 — Mega review: critical & important fixes (PR B)

**Контекст:**
Сквозное ревью кода/тестов/доков перед Phase 4c (e2e). Нашли 2 critical (UTC inconsistency + Markdown injection в командах) и 2 important (`getattr(settings,...)` + `type(update).__name__` всегда `"Update"`). Все четыре правки в одном PR ≤180 LOC, минорные вынесены в `docs/REVIEW-findings.md::Minor`.

**Сделано:**
- `app/shared/time.py` — новый хелпер `utcnow_naive()`: `datetime.now(UTC).replace(tzinfo=None)`. Один источник правды для всех DB-write сайтов на naive-UTC колонках. Заменил три call-сайта:
  - `app/db/models.py::_utcnow` теперь делегирует в `utcnow_naive()` (раньше возвращал tz-aware → silent strip on insert).
  - `app/bot/services.py::complete_onboarding` (`onboarded_at`) и `schedule_reminders` (`now`).
  - `app/workers/scheduler.py::tick_reminders` (`cutoff` и `sent_at`). Заодно убраны `noqa: DTZ003` / `noqa: BLE001` — теперь чистые без подавлений.
- `app/bot/routers/commands.py` (C-2) — убраны все `parse_mode="Markdown"` и `*Title*` декорации в `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday`, `/notes`, `/categories`. `task.title` / `note.title` приходят от пользователя и могут содержать `*`/`_`/`[`/`` ` `` — Telegram возвращал бы `400 Bad Request: can't parse entities`. Тот же фикс уже применён к callback-хендлерам, плюс есть регрессия в `test_callbacks.py` — `commands.py` мимо неё проскочил.
- `app/bot/routers/settings.py::_setting_value` (I-1) — заменил `getattr(settings, field, None)` на явный if-маппинг по `SETTING_LABELS`-полям (`critic_mode`, `morning_digest_at`, `evening_digest_at`, `response_style_source`, `week_due_semantic`). Теперь field-allow-list — единственный путь к колонке, и type-checker видит каждую ветку.
- `app/main.py::_classify_update` (I-2) — выделил функцию-классификатор: ветвится по `update.message`, `edited_message`, `callback_query`, `inline_query`, `channel_post`, `edited_channel_post` → `"other"`. Старое `type(update).__name__` всегда было `"Update"` (бесполезный лог).
- `docs/REVIEW-findings.md` — итоговый отчёт ревью: 2 Critical (исправлены), 2 Important (исправлены), 5 Minor (M-1..M-5: race на webhook, `asyncio.create_task` без strong-ref, `_utcnow` алиас, singleton groq router, free-tier idle) — задокументированы для follow-up. Плюс блок Positive patterns (N+1 avoidance, exception isolation, graceful shutdown, PII discipline, idempotency, HH:MM matcher, allow-list, LIKE escape).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 172 passed.
- LOC ≤180 (включая фикс-сайты + докментацию в коде).

**Не сделано (вынесено в `docs/REVIEW-findings.md::Minor`):**
- M-1: webhook idempotency race (catch `IntegrityError` на `record_update`).
- M-2: pending tasks set в `text.py`/`voice.py` чтобы избежать GC-окна.
- M-4: groq router singleton — приемлемо для production, документ.

---

## 2026-05-08 — Render fix: in-process scheduler loop (free-tier deploy)

**Контекст:**
Render Free **не поддерживает** standalone Cron Jobs (нужен Starter+ ~$1/мес). Чтобы остаться на бесплатке и при этом гонять «будильник» каждую минуту, переезжаем с отдельного cron-сервиса на фоновый `asyncio`-loop в самом FastAPI-процессе. Free-тир засыпает через 15 мин неактивности — её пинаем извне (`cron-job.org` или GitHub Actions cron на `/healthz`).

**Сделано:**
- `app/workers/runner.py` — новый модуль с тремя функциями:
  - `run_scheduler_loop(bot, stop_event, *, interval=60.0)` — крутится до сигнала, на каждой итерации зовёт `tick_reminders` + `tick_digests`, ловит и логирует исключения (один сбой не убивает loop), спит через `asyncio.wait_for(stop_event.wait(), timeout=interval)` чтобы корректно прерываться.
  - `start_inproc_scheduler(bot, *, interval)` → `(task, stop_event)`.
  - `stop_inproc_scheduler(task, stop_event, *, grace=10.0)` — ставит флаг, ждёт graceful shutdown, при таймауте `task.cancel()` + `contextlib.suppress`.
- `app/main.py` — `lifespan` теперь поднимает scheduler после `init_engine` + `setWebhook`, если `bot is not None`, есть `database_url` и `scheduler_inproc_enabled=True`. На shutdown — `stop_inproc_scheduler` перед `bot.session.close()`.
- `app/shared/config.py` — поля `scheduler_inproc_enabled: bool = True` и `scheduler_tick_interval_seconds: float = 60.0`.
- `app/workers/__init__.py` — обновлённый docstring (два потока: `scheduler.main` для внешнего cron / `runner.run_scheduler_loop` для in-proc).
- `render.yaml` — удалён `cron`-сервис `plan-app-scheduler`. В web envVars добавлены `SCHEDULER_INPROC_ENABLED=true` и `SCHEDULER_TICK_INTERVAL_SECONDS=60`. В верхнем комментарии — рецепт перехода на real-cron при апгрейде до Starter+.
- `docs/RENDER.md` — новый документ: топология free-тира, инструкции по cron-job.org и GitHub Actions cron keep-alive, описание SLO интервала тика, рецепт апгрейда.
- `tests/test_runner.py` — 4 теста: loop вызывает tick-функции и останавливается по флагу, исключение в одной итерации не убивает loop, `start_inproc_scheduler` + `stop_inproc_scheduler` пара, `stop_inproc_scheduler` для уже завершённой таски — no-op.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 172 passed (+7 новых: 4 runner + 3 побочных от lifespan/cfg/exports).
- LOC основной правки (без тестов и доков): ~140.

**Замечание по эксплуатации (для деплоя):**
- После выкатки задать в Render dashboard внешний пинг на `/healthz` каждые 5–10 минут (см. `docs/RENDER.md`).
- При апгрейде до Starter+ — `SCHEDULER_INPROC_ENABLED=false` и поднять обратно cron-сервис, который дёргает `python -m app.workers.scheduler`.

---

## 2026-05-08 — Phase 4b: Scheduler + Digest + render.yaml cron

**Сделано:**
- `app/workers/scheduler.py` — реальная имплементация cron-воркера:
  - `_format_reminder(task)` — текст напоминания: «⏰ Напоминаю: {title}» + «— в HH:MM» если `due_at` задан и не равен 00:00.
  - `tick_reminders(bot, *, now=None)` — выбирает `pending` напоминания с `fire_at <= now` (батч 100, сортировка по `fire_at`), отправляет в Telegram. На успех → `status='sent'`, `sent_at=now`, `last_error=None`. На ошибку → `attempts++`, `last_error=str(exc)[:512]`, при `attempts >= 3` → `status='failed'`. Возвращает `{"sent","retry","failed"}`.
  - `main_async()` — entrypoint: `configure_logging` → `init_engine(database_url)` → `Bot(token)` → `tick_reminders` → `tick_digests` → закрытие сессии Bot и `dispose_engine`.
  - `main()` — sync-обёртка `asyncio.run(main_async())` для `python -m app.workers.scheduler`.
- `app/bot/digest.py` — daily digest builders + cron tick:
  - `_user_local_now(tz, now_utc)` — UTC → локальное время через `ZoneInfo`, фолбэк UTC при битой tz.
  - `_matches_hhmm(local_dt, hhmm)` — строгое сравнение `HH:MM` (zero-padded), без слэка.
  - `_format_task_line(task)` — единая строка `🔴/🟡/🟢 {title} — в HH:MM`.
  - `_open_tasks_for_horizon(session, user_id, horizon_kind)` — задачи в горизонте, исключая `done`/`cancelled`, сортировка по `due_at NULLS LAST, created_at`.
  - `build_morning_digest(session, user)` — список задач `today` или приветствие при пустом списке.
  - `build_evening_digest(session, user)` — итоги (что осталось today + завтрашний пик), либо «Сегодня всё закрыто 🎉».
  - `tick_digests(bot, *, now=None)` — для каждого онбордженного пользователя сравнивает локальное HH:MM с `morning_digest_at` / `evening_digest_at`, шлёт соответствующий дайджест. Изоляция ошибок одного пользователя через `try/except`.
- `render.yaml` — добавлен новый сервис:
  - `type: cron`, `name: plan-app-scheduler`, `runtime: python`, `region: frankfurt`, `plan: starter`, `branch: main`, `schedule: "*/1 * * * *"`.
  - `buildCommand: rm -rf .agents docs tests && uv sync --frozen`, `startCommand: uv run python -m app.workers.scheduler`.
  - `envVars`: `ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12`, `TELEGRAM_BOT_TOKEN` (sync: false), `DATABASE_URL` (sync: false).
- `tests/test_scheduler.py` — 7 тестов: форматтер с/без времени и при `00:00`, отправка просроченных, пропуск будущих, пропуск уже `sent`, retry-семантика, переход в `failed` после `MAX_REMINDER_ATTEMPTS`, батч из нескольких записей.
- `tests/test_digest.py` — 13 тестов: helpers (`_matches_hhmm`, `_user_local_now`), morning empty/полный/без `done`, evening combined/empty-today, `tick_digests` morning local-match, off-minute skip, skip unonboarded, изоляция падений по чату.

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 165 passed (145 Phase 4a + 20 новых).
- PR ~390 LOC (код Phase 4b без тестов).

**Замечание по Render:**
- Free-план не поддерживает cron. Поэтому `plan-app-scheduler` объявлен на `plan: starter`. Web-сервис остаётся на `free` без изменений.

---

## 2026-05-08 — Phase 4a: Reminder model + migration + persist extension

**Сделано:**
- `app/db/models.py` — модель `Reminder` (table=`reminders`):
  - `id`, `user_id` (FK→users.id, indexed), `task_id` (FK→tasks.id, indexed), `fire_at` (DateTime UTC, indexed), `status` (`pending|sent|failed|cancelled`, default `pending`, indexed, max_length 16), `attempts` (default 0), `last_error`, `sent_at`, `created_at`.
- `alembic/versions/2026_05_08_2015-0003_phase_4_reminders.py` — миграция: `CREATE TABLE reminders` + 4 индекса (`user_id`, `task_id`, `fire_at`, `status`).
- `app/bot/services.py`:
  - `DEFAULT_REMINDER_OFFSETS = {"same_day": [60, 15], "multi_day": [1440, 60]}` — фолбэк, если у пользователя нет своих.
  - `_select_reminder_offsets(cr, defaults)` — explicit `cr.reminder_offsets` побеждают defaults; иначе `same_day` для today/tomorrow, `multi_day` для остальных горизонтов.
  - `_to_naive_utc(dt)` — нормализация tz (DateTime в БД хранится без offset).
  - `schedule_reminders(...)` — создаёт `Reminder` rows, пропуская офсеты, у которых `fire_at <= now`.
  - `persist_classification(...)` теперь принимает `default_reminder_offsets` и после `Task.flush()` планирует `Reminder` rows, если `due_at is not None`.
- `app/bot/routers/text.py` — `_run_pipeline` пробрасывает `default_reminder_offsets` (читается из `UserSettings.default_reminder_offsets`) в `persist_classification`.
- `tests/test_reminders.py` — 13 новых тестов: офсетная логика (5), `schedule_reminders` rows/skip-past/empty (3), `persist_classification` create/no-due_at/notes/explicit/multi-day (5).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 145 passed (132 + 13 новых).
- PR ~340 LOC.

**Не сделано (Phase 4b, отдельный PR):**
- `app/workers/scheduler.py` (cron tick: shipping pending reminders, retry/fail mark).
- `app/bot/digest.py` (morning/evening daily digest builders).
- `render.yaml` cron job для tick'ов раз в минуту.
- e2e Phase 4 (digest + reminders end-to-end).

---

## 2026-05-08 — Code review: critical & important fixes + skills bundle

**Сделано:**
- `code-review-findings.md` — глубокое ревью на 3 Critical / 6 Important / 10 Minor findings (с file:line и severity).
- `.agents/skills/requesting-code-review/` — адаптированный obra superpowers скилл (SKILL.md + code-reviewer.md), плюс `.agents/skills/socraticode-principles/SKILL.md` — методология SocratiCode (hybrid search + dependency graphs + blast radius). В Render-деплой не попадает: `render.yaml.buildCommand` теперь `rm -rf .agents docs tests && uv sync --frozen` — на free tier чистый рантайм, в GitHub видно всё.
- `app/bot/routers/callbacks.py` (C-1): убран `parse_mode="Markdown"` из всех `edit_text` с пользовательскими `task.title`. Не падаем на названиях с `*`, `_`, `[`.
- `app/bot/services.py`:
  - C-2: `update_user_settings()` теперь валидирует `value` против `ALLOWED_SETTING_VALUES` (frozenset на поле). Никаких `setattr(settings, field, arbitrary_string)`.
  - I-1: `get_categories_with_counts()` — один LEFT JOIN + GROUP BY вместо 1+N запросов.
  - I-2: новая утилита `_escape_like()` + `Task.title.ilike(pattern, escape="\\")` для безопасного поиска по подстроке.
  - I-5: импорт `AsyncSession` теперь из `sqlmodel.ext.asyncio.session` (а не `sqlalchemy.ext.asyncio`) — соответствует фактическому типу из `session_scope()`.
  - I-6: `get_or_create_user()` обновляет `lang_code`, если Telegram прислал новый (раньше навсегда оставался первый).
- `app/bot/routers/text.py` (C-3 + I-3): `asyncio.gather(..., return_exceptions=True)` + явный `_log_task_exception` callback вместо лямбды, которая молча проглатывала ошибки. Один сбойный classify не убивает весь батч; критик в `try/except` — ошибка критика не трогает уже хорошие классификации.
- `app/bot/routers/voice.py` (I-3): тот же `_log_task_exception` импортирован из text.py.
- `tests/test_callbacks.py` — регрессии для C-1 (не должно быть `parse_mode="Markdown"` рядом с `task.title`) и I-2 (LIKE-метасимволы экранируются).
- `tests/test_settings.py` — регрессия для C-2 (отвергаем неизвестное `value`).
- `tests/test_e2e_pipeline.py` — регрессия для C-3 (один Groq 429 на втором юните — выживший юнит сохраняется и попадает в ответ).

**Верификация:**
- `uv run ruff format .` + `uv run ruff check .` — чисто.
- `uv run pytest -q` — 132 passed (128 + 4 новых).
- Скиллы и docs в Render-деплой не попадают (`buildCommand` сначала их удаляет).

---

## 2026-05-08 — Phase 3 finish: change-category button + tz/reminder в /settings (PR #31)

**Сделано:**
- `app/bot/routers/callbacks.py`:
  - 4-я кнопка «🏷 Категория» во второй строке `task_action_keyboard`.
  - `category_picker_keyboard(task_id, categories)` — сетка 2×N с кнопкой «↩ Назад».
  - Хендлеры `task:pick_category:<id>` (показать пикер) и `task:set_category:<id>:<cat_id>` (применить).
- `app/bot/services.py`:
  - `get_user_categories_full()` — возвращает `Category[]` (а не только имена).
  - `update_task_category()` + `TaskEvent(kind="recategorized")`.
  - `REMINDER_PRESETS = {"minimal","default","extra"}` + `reminder_preset_from_offsets()`.
  - `update_user_settings()` маршрутизирует виртуальные поля: `tz` → `User.tz` (валидация через `is_valid_timezone()`), `reminder_preset` → `UserSettings.default_reminder_offsets`.
- `app/bot/routers/settings.py`:
  - Поля `tz` (8 пресетов IANA: Москва, Калининград, Самара, Екатеринбург, Алматы, Ташкент, Владивосток, UTC) и `reminder_preset` (3 пресета) в SETTING_LABELS / SETTING_OPTIONS.
  - `_setting_value(field, settings, user)` — резолвит виртуальные поля.
  - `_format_settings(settings, user)` — принимает `User` для отображения tz и текущего пресета.
- `tests/test_callbacks.py` — обновлена проверка структуры кнопок; добавлены тесты пикера и `update_task_category`.
- `tests/test_settings.py` — добавлены тесты на tz/reminder_preset (валидация, expand to offsets, обратная мапа, fallback без user).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 128 passed (119 + 9 новых).
- PR ~396 LOC.

**Phase 3 закрыта.** Следующее — Phase 4 (cron worker для напоминаний и daily/weekly digest).

---

## 2026-05-08 — Phase 3c: /settings command with inline buttons (PR #29)

**Сделано:**
- `app/bot/routers/settings.py` — полный `/settings` роутер:
  - `cmd_settings` — показывает текущие настройки с кнопками редактирования.
  - `cb_settings_edit` — показывает варианты для конкретной настройки.
  - `cb_settings_set` — применяет выбранное значение.
  - `cb_settings_back` — возврат к обзору настроек.
  - 5 редактируемых настроек: critic_mode, morning_digest_at, evening_digest_at, response_style_source, week_due_semantic.
- `app/bot/services.py` — `update_user_settings()`: валидация поля + обновление.
- `app/bot/__init__.py` — регистрация settings_router.
- `app/bot/courier_templates.py` — `/settings` добавлен в HELP.
- `tests/test_settings.py` — 11 тестов (клавиатуры, форматтер, сервис).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 119 passed (108 + 11 новых).
- PR ~410 LOC.

---

## 2026-05-08 — Phase 3b: Inline buttons on task cards (PR #28)

**Сделано:**
- `app/bot/routers/callbacks.py` — callback-роутер для inline-кнопок:
  - `task:done:<id>` — отметить задачу выполненной (зачёркнутый текст).
  - `task:delete:<id>` — удалить задачу.
  - `task:pick_move:<id>` — показать клавиатуру выбора горизонта.
  - `task:move:<id>:<horizon>` — перенести задачу на выбранный горизонт.
  - `task:cancel:<id>` — отменить перенос, вернуть кнопки действий.
- `task_action_keyboard(task_id)` — 3 кнопки: ✅ Готово, 🔄 Перенести, 🗑 Удалить.
- `horizon_picker_keyboard(task_id)` — 6 горизонтов + кнопка «Назад».
- `app/bot/routers/commands.py` — view-команды теперь отправляют inline-кнопки под каждой задачей.
- `app/bot/__init__.py` — регистрация callbacks_router.
- `tests/test_callbacks.py` — 6 тестов (структура клавиатур, service-level операции).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 108 passed (102 + 6 новых).
- PR ~380 LOC.

---

## 2026-05-08 — Phase 3a: View commands (/today, /week, /notes, /categories) (PR #27)

**Сделано:**
- `app/bot/routers/commands.py` — 8 команд просмотра:
  - `/today`, `/tomorrow`, `/week`, `/month`, `/year`, `/someday` — задачи по горизонту.
  - `/notes` — последние 20 заметок.
  - `/categories` — категории с количеством активных задач.
- `app/bot/services.py` — 7 новых функций:
  - `get_tasks_by_horizon()`, `get_all_notes()`, `get_categories_with_counts()`.
  - `mark_task_done()`, `delete_task()`, `get_task_by_id()`.
- `_format_task_list()`, `_format_note_list()` — форматтеры с иконками приоритетов.
- `app/bot/__init__.py` — регистрация commands_router.
- `app/bot/courier_templates.py` — HELP обновлён со списком новых команд.
- `tests/test_commands.py` — 11 тестов (сервисы + форматтеры).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 102 passed (91 + 11 новых).
- PR ~550 LOC.

---

## 2026-05-08 — e2e Pipeline Tests (PR #25)

**Сделано:**
- `tests/test_e2e_pipeline.py` — 8 end-to-end тестов, проверяющих полный pipeline (reorder detect → split → time → classify → persist → courier reply) с мокнутыми LLM-вызовами и in-memory БД.
- Тест-кейсы:
  1. Одна задача: «утром пробежка» → 1 task Здоровье/today.
  2. Две задачи: «купить хлеб и молоко, записаться к врачу» → 2 tasks.
  3. Задача + заметка: «позвонить Олегу, книга про AI» → 1 task + 1 note.
  4. Рабочие дедлайны: «до пятницы отчёт, в 11 совещание» → 2 tasks Работа.
  5. Филлер: «ну так, окей» → 0 задач.
  6. Три элемента: «йога, ужин, идея про стартап» → 2 tasks + 1 note.
  7. Одна заметка: «мысль про архитектуру» → 1 note.
  8. Срочная задача: «срочно! позвонить в банк» → 1 high-priority task.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 91 passed (83 + 8 новых).
- PR ~500 LOC (только тесты).

---

## 2026-05-08 — Phase 2.3d: Reorder — detect and execute task rescheduling (PR #23)

**Сделано:**
- `app/ai/reorder.py` — `detect_reorder()`: определяет, является ли сообщение запросом на перенос задачи. LLM (`llama-3.1-8b-instant`) через `instructor` (JSON mode, temperature 0.0). Короткие сообщения (<3 символов) пропускаются без LLM.
- `app/ai/prompts/reorder.md` — системный промпт для детекции переноса: примеры фраз, формат вывода (`is_reorder`, `task_query`, `target_horizon`, `target_raw`).
- `app/ai/schemas.py` — `ReorderRequest` (is_reorder, task_query, target_horizon, target_raw).
- `app/bot/services.py` — `find_task_by_query()` (ILIKE-поиск по title, исключает done), `update_task_horizon()` (смена горизонта + TaskEvent kind=reordered).
- `app/bot/routers/text.py` — `_try_reorder()`: перед обычным pipeline проверяет reorder-интент. Если найден — ищет задачу и обновляет горизонт, отвечает «✅ Перенёс «X» → Y.». Если задача не найдена — сообщает об этом.
- `app/bot/routers/voice.py` — наследует reorder из `_run_pipeline()` text.py.
- `tests/test_reorder.py` — 9 тестов: schema (2), detect_reorder LLM mock (2), short text (1), find_task DB (3), update_task_horizon DB (1).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 83 passed (74 старых + 9 новых).
- PR ~470 LOC.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- e2e тесты — отдельный PR.
- due_at обновление при переносе — пока только horizon, без пересчёта даты.

---

## 2026-05-08 — Phase 2.3c: Courier — confirmation + summary replies (PR #21)

**Сделано:**
- `app/ai/courier.py` — модуль Courier:
  - `TEMPLATES` — 6 стилей × 6 фраз = 36 шаблонов подтверждений (neutral, formal_master, friendly, playful, terse, respectful).
  - `generate_courier_reply()` — выбирает шаблон или генерирует через LLM (`llama-3.1-8b-instant`) в зависимости от `mode` (mix/template_only/llm_only).
  - `build_summary()` — детерминированное резюме из `ClassifierResult[]` (📌 задача / 📝 заметка: title [category]).
  - `courier_respond()` — полный ответ: подтверждение + резюме.
  - `_pluralize()` — русское склонение «элемент/элемента/элементов».
- `app/ai/prompts/courier.md` — системный промпт для LLM-генерации подтверждений: описание 6 стилей, правила (русский, без markdown, без перечисления задач).
- `app/bot/routers/text.py` — заменён inline-reply на `courier_respond()`. Из UserSettings читается `response_style_source` → `courier_mode`. Удалена неиспользуемая `_pluralize_elements()`.
- `app/bot/routers/voice.py` — аналогичная интеграция: `courier_mode` и `courier_style` пробрасываются в `_run_pipeline()`.
- `tests/test_courier.py` — 11 тестов: шаблоны (2), build_summary (3), generate_courier_reply template_only (2), LLM mock (1), courier_respond full (3).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 74 passed (63 старых + 11 новых).
- PR ~400 LOC (418 строк).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Voice task reordering — Phase 2.3d.
- e2e тесты — после Phase 2.3d.

---

## 2026-05-08 — Phase 2.3b: Critic — conditional review of classifier output (PR #19)

**Сделано:**
- `app/ai/critic.py` — `critique_classification()` через `qwen-qwq-32b` (instructor, temperature=0.0), `should_run_critic()` (два режима: `confidence` / `always`), `apply_verdict()` (подмена результата при `approved=False`).
- `app/ai/prompts/critic.md` — системный промпт для критика: проверяет is_task, category_name, horizon, priority, title, reminder_offsets.
- `app/ai/schemas.py` — `CriticVerdict` (approved, reason, corrected ClassifierResult | None).
- `app/bot/services.py` — `get_user_settings()` для чтения critic_mode / confidence_threshold из `UserSettings`.
- `app/bot/routers/text.py` — интеграция критика в `_run_pipeline()`: после classify, до persist. Параметры `critic_mode` и `confidence_threshold` пробрасываются из UserSettings.
- `app/bot/routers/voice.py` — аналогичная передача critic-настроек из UserSettings в pipeline.
- `tests/test_critic.py` — 9 тестов: should_run_critic (4 кейса), apply_verdict (3 кейса), critique_classification с мокнутым Groq (2 кейса).

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 63 passed.
- PR ~400 LOC (344 строк кода + 63 строк промпта).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Courier — Phase 2.3c.
- Voice reordering — Phase 2.3d.

---

## 2026-05-08 — Phase 2.3a: Whisper — голосовые сообщения (PR #18)

**Сделано:**
- `app/ai/whisper.py` — `transcribe_voice()`: whisper-large-v3 через Groq, language=ru, temperature=0.0, response_format=verbose_json. Логирование latency и key_id через structlog.
- `app/bot/routers/voice.py` — хендлер голосовых: проверка онбординга → скачивание файла → транскрипция → сохранение в inbox (kind=voice) → запуск text-pipeline в фоне (`asyncio.create_task`). Лимит 20 МБ.
- `app/bot/services.py` — `store_inbox_voice()` (kind="voice", transcript в raw_text).
- `app/bot/__init__.py` — регистрация voice-роутера.
- `tests/test_whisper.py` — 5 тестов с мокнутым Groq через respx.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 54 passed.
- PR 279 LOC.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Critic — Phase 2.3b.
- Courier — Phase 2.3c.

---

## 2026-05-08 — Phase 2.2b: DB models + persistence + pipeline integration

**Сделано:**
- `app/db/models.py` — 6 новых SQLModel-таблиц: `Category`, `Horizon`, `Task`, `Note`, `AiRun`, `TaskEvent`. Все с FK на `users`, индексами по `user_id`, `_utcnow` default.
- `alembic/versions/0002_phase_2_2_models.py` — миграция: создаёт 6 таблиц + индексы, downgrade дропает в обратном порядке.
- `app/bot/services.py` — 5 новых функций: `get_or_create_category`, `get_or_create_horizon`, `get_user_categories`, `persist_classification`, `log_ai_run`.
- `app/bot/routers/text.py` — полная цепочка: split → time_resolver → classify → persist → ответ с резюме. GroqKeyRouter — singleton (lazy init). Ответ юзеру: «Разобрал на N элемент(ов): 📌 задача / 📝 заметка: title [category]».
- `tests/test_persistence.py` — 7 тестов: category CRUD, horizon CRUD, user_categories, persist task + events, persist note, ai_run log, category reuse.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 47 passed (24 старых + 16 Phase 2.2a + 7 новых).
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Critic — Phase 2.3.
- Whisper — Phase 2.3.
- `call_with_retry` — перенесён в Phase 2.3 (пока хватает одного ключа).

---

## 2026-05-08 — Phase 2.1: Splitter + AI infrastructure (PR #12)

**Сделано:**
- `app/ai/router.py` — `GroqKeyRouter`: round-robin пул API-ключей Groq с методами `advance()` и `async_client()`.
- `app/ai/schemas.py` — Pydantic-модели `IntentUnit` и `SplitterResult` для структурированного вывода LLM.
- `app/ai/splitter.py` — `split_message()`: вызывает `llama-3.1-8b-instant` через `instructor` (structured output, temperature 0.0). Сообщения < 2 символов пропускаются без вызова LLM.
- `app/ai/prompts/splitter.md` — системный промпт по структуре ROLE → TASK → CONSTRAINTS → OUTPUT → EXAMPLES. 3 few-shot примера на русском.
- `app/bot/routers/text.py` — интеграция: после сохранения в inbox splitter запускается в фоне (`asyncio.create_task`), результат логируется. Задачи пока не сохраняются (Phase 2.2).
- `tests/test_groq_router.py` — 5 тестов на ротацию ключей.
- `tests/test_splitter.py` — 5 тестов с мокнутым Groq через `respx`.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 24 passed (14 старых + 10 новых).
- PR ≤ 400 LOC (361 строк), одна тема.
- Нет секретов, нет `print()`, нет `Any`/`getattr`.

**Не сделано (намеренно):**
- Classifier, Critic, Whisper — Phase 2.2 / 2.3.
- Сохранение задач/заметок в БД — Phase 2.2 (нужны модели Task/Note).
- `call_with_retry` с retry/backoff — добавится в Phase 2.2 когда появится Classifier.

---

## 2026-05-08 — Phase 4: e2e-проверка живого бота (`@daylirobot`)

**Сделано:**
- Юзер прошёл онбординг в Telegram: `/start` → имя «Юсуф» → таймзона `Europe/Moscow` → бот ответил блоком дефолтов (08:00/21:00, `[60,15]`/`[1440,60]`, critic=`confidence@0.7`, courier=`mix`, `deadline_sunday`).
- Свободный текст («Так, сегодня написать… Олег…», «окей») и команда `/settings` корректно проваливаются в text-роутер и возвращают плейсхолдер «AI-разбор подключу в Phase 2».
- Сверка с Neon-БД (5 таблиц после миграции) показала ожидаемое состояние:
  - `users` — 1 строка (`telegram_id=2007532633`, `display_name='Юсуф'`, `tz='Europe/Moscow'`, `onboarded_at` заполнен).
  - `user_settings` — 1 строка (все дефолты совпадают с обещанным боту блоком).
  - `inbox_entries` — 3 строки (две произвольных реплики + `/settings`, все `kind='text'`, `telegram_message_id` заполнены).
  - `telegram_updates` — 7 строк, `update_id` идут подряд без разрывов и дубликатов; идемпотентность отрабатывает.
- Render-логи на момент проверки: `/healthz` отвечает 200 каждые 5 сек (Render-пинг), стартап и `setWebhook` прошли в lifespan.
- Workspace-«Cile Simme's workspace» подтверждён юзером как его собственный второй Render-аккаунт — никаких пересозданий сервиса не требуется.

**Подмечено в backlog (отдельные PR):**
- `/settings` сейчас проваливается в catch-all text-роутер (нет хендлера) — это запланированный Phase 3, фиксируем как известную «фичу до тех пор».
- В `telegram_updates.user_id` пишется `NULL` (по дизайну Phase 1 — webhook не делает lookup `User.id` по `telegram_id`). Не блокер; в Phase 2 (где появится сложная маршрутизация по юзерам) подтянем.
- Голосовых сообщений не тестировали — это Phase 2 (Whisper).

**Верификация:**
- Юзер-визуал — переписка в чате (`/start`, имя, tz, дефолты, два свободных текста, `/settings`).
- `SELECT count(*)` по 4 таблицам Phase 1 → ожидаемые числа.
- `SELECT update_id … ORDER BY update_id DESC` — последовательные ID, идемпотентность не сломана.

**Что после этого PR:**
- Решение по фазе 2 (AI-пайплайн на Groq + русский NLP) или точечные фиксы — за юзером.

---

## 2026-05-08 — Phase 4 (out-of-order): первый Render-деплой + живой webhook

**Сделано:**
- `render.yaml` переписан под текущий Python-стек (PR #8): один web-сервис `plan-app`, `runtime: python`, `region: frankfurt`, `plan: free`, `buildCommand: uv sync --frozen`, `startCommand: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /healthz`, `autoDeployTrigger: commit`. Старая (TS-эпохи, два Node-сервиса с prisma/npm и захардкоженным MINIAPP_URL на мёртвый домен) удалена.
- Сервис создан через Render REST API (`POST /v1/services`) на user-предоставленном `RENDER_API_KEY`: `srv-d7uohcf7f7vs73crmk3g`, dashboard `https://dashboard.render.com/web/srv-d7uohcf7f7vs73crmk3g`. Workspace — «Cile Simme's workspace» (`tea-d7tr6vugvqtc73bsjka0`); это тот же физический Render-аккаунт, что у юзера, просто с другим email-логином (зафиксировано как факт, не баг).
- Public URL — `https://plan-app-t6nx.onrender.com`. ENV-переменные проставлены через REST API: `ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12` + 5 секретных (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_BASE_URL`, `DATABASE_URL`, `GROQ_API_KEYS`). В git ничего из секретов не попало.
- Telegram webhook зарегистрирован: `getWebhookInfo` отдаёт `url=https://plan-app-t6nx.onrender.com/tg/<secret>`, `pending_update_count=0`, `ip_address=216.24.57.7`. `setWebhook(drop_pending_updates=True, secret_token=...)` срабатывает в lifespan FastAPI'я при старте.
- `/healthz` отвечает HTTP 200 за ~250 мс с прода (free-tier холодный старт ~3 мин, прогретый — мгновенно).
- Карта проекта (`.agents/skills/plan-app-internal/SKILL.md`): добавлен §15 «Live deploy (Render)» с ID-сервиса, URL, ownerId, копипастными API-командами для будущих сессий. Старый §14 переименован в §16, §13 — в §14.

**Верификация:**
- `curl https://plan-app-t6nx.onrender.com/healthz` → `{"status":"ok"}` HTTP 200.
- `curl https://api.telegram.org/bot<token>/getWebhookInfo` → URL заполнен, ошибок нет.
- Render Deploy → `live` статус через ~3.5 мин (build_in_progress 1.5 мин + update_in_progress 2 мин).
- Юзер-визуал: переписка с `@daylirobot` (PLAN) — отдельным шагом / скрином в чате.

**Не сделано (намеренно):**
- AI-пайплайн (Splitter / Classifier / Critic), голос/Whisper — Phase 2.
- Cron-воркер для напоминаний — Phase 4 (вторая часть).
- FSM на Postgres-storage (сейчас MemoryStorage) — Phase 4.
- Pooled connection-string Neon (сейчас direct) — потребуется только при росте нагрузки.

**Замечание по workspace:**
RENDER_API_KEY от юзера привязан к workspace «Cile Simme's workspace» (email `city.cile.simme@gmail.com`), а не к основной почте Юсуфа (`po.muhidinovusuf54@gmail.com`). Юзер подтверждает / опровергает в чате. Если это посторонний аккаунт — пересоздадим сервис в нужном workspace отдельным шагом.

---

## 2026-05-08 — Phase 1.5: GitHub Actions CI + driver hotfix

**Сделано:**
- `.github/workflows/ci.yml` — pipeline на каждый push в `main` и на каждый PR: чекаут → `astral-sh/setup-uv` (с кэшом по `uv.lock`) → `uv sync --frozen` → `ruff format --check` → `ruff check` → `pytest -q`. Concurrency: новая попытка отменяет предыдущую на той же ветке.
- БД-драйвер: бэквард-совместимая нормализация URL в `app/db/base.py` и `alembic/env.py` — голый `postgresql://` (вид Neon copy-paste) теперь автоматически становится `postgresql+psycopg://`. Это снимает требование вручную править connection-string и даёт использовать один драйвер (psycopg v3) и для async-движка приложения, и для синхронного раннера Alembic. SQLite URL получает суффикс `+aiosqlite`.
- `tests/test_smoke.py` — `monkeypatch`-фикстура `_clean_env`, чтобы тесты дефолтных настроек не падали на дев-машинах с уже экспортированными `TELEGRAM_BOT_TOKEN`/`DATABASE_URL`/`GROQ_API_KEYS`.
- Карта проекта (`.agents/skills/plan-app-internal/SKILL.md`): добавлены §11 «Merge-workflow» и §12 «PR tooling» — фиксируют, что мердж делает AI-агент через REST API + user-PAT, а не юзер через GitHub UI.

**Верификация:**
- `uv run ruff format/check` — чисто.
- `uv run pytest -q` — 14 passed.
- `uv run alembic upgrade head` против настоящей Neon-БД — 5 таблиц созданы.

**Не сделано (намеренно):**
- Никаких бизнес-изменений в коде бота / API.
- Render-деплой и e2e-проверка живого бота — отдельным шагом.

---

## 2026-05-08 — Phase 1: Minimal bot (webhook + DB + onboarding)

**Сделано:**
- Конфиг (`app/shared/config.py`): добавлено свойство `webhook_url`, `get_settings()` теперь кэшируется через `lru_cache`.
- Структурное логирование (`app/shared/logging.py`): `structlog` с JSON-рендером в проде и консольным — в dev. PII-правило: логи никогда не содержат `message.text`/transcripts.
- БД-слой (`app/db/`): четыре модели Phase 1 — `User`, `UserSettings`, `InboxEntry`, `TelegramUpdate`. Async engine + sessionmaker (`init_engine` / `get_sessionmaker` / `session_scope`). `BigInteger` для Telegram-ID, JSON для `default_reminder_offsets`.
- Alembic подключён к `SQLModel.metadata` и `DATABASE_URL` (online-мode конвертирует `+asyncpg`/`+aiosqlite` в синхронный драйвер). Первая миграция `0001_init` создаёт все четыре таблицы + индексы.
- Бот (`app/bot/`):
  - `routers/start.py` — `/start`, `/help`, FSM-онбординг (имя → IANA-tz → дефолты). Записывает `User`/`UserSettings` с дефолтами: `confidence` (0.7), 08:00/21:00, `[60,15]`/`[1440,60]`, `mix`, `deadline_sunday`.
  - `routers/text.py` — catch-all для текстов: пишет в `inbox_entries`, отвечает заглушкой «AI подключим в Phase 2».
  - Роутеры — фабрики (`create_router()`), чтобы каждое `build_dispatcher()` собирало свежий граф (aiogram запрещает повторное прикрепление одного `Router` к двум диспетчерам — это иначе ломает тесты).
  - FSM-storage = `MemoryStorage` (Phase 4 переключим на Postgres-storage).
- FastAPI (`app/main.py`): lifespan c `set_webhook(drop_pending_updates=True, secret_token=...)`, `POST /tg/<secret>` с двойной валидацией (path-secret + `X-Telegram-Bot-Api-Secret-Token`), идемпотентность по `update_id` через таблицу `telegram_updates`. `/healthz` сохранился.
- Тесты:
  - `tests/test_services.py` — unit-тесты сервисов (`get_or_create_user`, `complete_onboarding`, `is_valid_timezone`, идемпотентность, inbox).
  - `tests/test_webhook.py` — секьюрити (плохой path / плохой header) + идемпотентность POST-а; aiogram-сессия замокана через `BaseSession.make_request`.
  - `tests/conftest.py` — общие фикстуры (in-memory SQLite, `Settings`, TestClient).
- Dev-зависимости: добавлены `aiosqlite` (тестовая БД) и `respx` (на будущее, для Phase 2 Groq-моков).
- Ruff: глобально игнорим `RUF001/002/003` (постоянные false positives на кириллических глифах).

**Не сделано (намеренно):**
- AI-пайплайн (Splitter / Classifier / Critic), `GroqKeyRouter`, голос/Whisper — это Phase 2.
- Inline-кнопки, `/today`, `/week`, `/settings` — Phase 3.
- Cron-воркер для напоминаний — Phase 4.
- Деплой на Render и подключение Neon — отдельным шагом после ручной проверки бота локально.

---

## 2026-05-07 — Phase 0: Cleanup + Python skeleton

**Сделано:**
- Удалены остатки прошлой реализации: `Vault/`, `Projects/`, `.hermes-backup/`, `AGENTS.md`, `PROJECTS.md`, весь TypeScript (`src/`, `prisma/`, `public/`, `package.json`, `tsconfig.json`, старый `README.md`).
- TS-история сохранена в git до коммита `6cc851d` на `main`.
- Создан новый `README.md`.
- Создана `docs/` с PLAN / ARCHITECTURE / ROADMAP / PROGRESS / IDEAS.
- Создана `.agents/skills/` (placeholder с описанием для будущего наполнения).
- Создан Python-скелет: `pyproject.toml` (uv-совместимый), `.python-version`, `ruff.toml`, `Dockerfile`, `.dockerignore`, `.env.example`.
- Структура папок: `app/{bot,api,ai,db,workers,shared}/`, `tests/`, `alembic/versions/`, `memory/`.
- Smoke-тест в `tests/test_smoke.py`.
- `render.yaml` обновлён под Python, без авто-деплоя.
- Обновлён `.gitignore`.

**Не сделано (намеренно):**
- Никакой бизнес-логики, никаких хендлеров, никаких LLM-вызовов — это Phase 1+.

**Закрытые вопросы по дороге (юзер ответил):**
- «На этой неделе» = комбо A+B (дедлайн воскресенье 23:59 + переключатель в `/settings`).
- «Через 5 минут пойти бегать» = AI решает по контексту (вариант C).
- Дефолтное смещение напоминания: внутри дня — за 1ч + 15мин; через N дней — за 1д + 1ч.
- Critic = тумблер в `/settings` с дефолтом `confidence` (порог 0.7).
- Утренний дайджест — 08:00, вечерний — 21:00 (настраиваемо).
- Курьер = микс шаблонов и LLM (≥30 шаблонов, ≥5 на стиль; рандом 50/50 per-reply).
- Critic-модель = `qwen-qwq-32b` (reasoning), резервы — Llama 4 Scout/Maverick.

---
