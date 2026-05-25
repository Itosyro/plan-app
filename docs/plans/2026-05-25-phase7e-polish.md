# Phase 7e — Polish: Kanban, Calendar, Completed-tasks, Telegram-native design

> **Для исполнителя (агент или человек):** это master-план из независимых
> рабочих потоков (workstreams). Каждый поток = отдельная ветка + PR,
> доводится до зелёного CI и мержится самостоятельно. Внутри потока шаги
> идут чекбоксами `- [ ]`. Применяй скиллы из «Скиллы и инструменты» ниже
> ПЕРЕД тем как трогать UI.

**Goal:** довести Mini-App до уровня Todoist по функциональности/плавности и
до Telegram-native по визуалу (ориентир — клиент Telegram и бот Mira):
рабочий drag-n-drop канбан по **категориям**, календарь уровня Google
Calendar, экран «Выполненные», и единый дизайн-язык (ховеры, обводки,
bottom-sheet, сегмент-контролы, анимации).

**Архитектура:** фронт — React + Vite + Tailwind + @dnd-kit + Telegram WebApp
SDK (всё уже в стеке). Бэк — FastAPI + SQLModel. Изменения БД: `Task.completed_at`,
и опционально пользовательские колонки канбана. Дизайн строим **свой**,
Telegram-native, вдохновляясь паттернами Todoist/Mira — не копируя ассеты
1:1, а воспроизводя ощущение (скругления, мягкие тени, blur, плавные
spring-переходы).

**Дизайн-референсы от юзера (для вдохновения, не для 1:1-копии):**
скрины бота **Mira** (Telegram-native: профиль/настройки, плавающий
bottom-nav-«остров», карточки) и **Todoist** (доска с кастомными разделами
`+ Добавить раздел`, карточки-задачи с чекбоксом, поповер «Раскладка»:
Список/Доска/Календарь + тумблер «Выполненные» + Группировка/Сортировка/
Фильтр). Ориентир ощущения: визуал — Telegram/Mira, функциональность и
плавность — Todoist.

**Tech Stack:** React 18, TypeScript, Tailwind, @dnd-kit/core, lucide-react,
Telegram WebApp CloudStorage; FastAPI, SQLModel, Alembic, pytest.

---

## 0. Скиллы и инструменты (применять обязательно)

Доступны локально в `.agents/skills/`:

- **`lazyweb-design`** — MCP-база из 257k+ скриншотов реальных приложений.
  Применять ПЕРЕД каждой нетривиальной UI-правкой (календарь, канбан-карточка,
  bottom-sheet, settings-row). Нужен `LAZYWEB_MCP_TOKEN` в env — проверить
  `secrets.list filter=org`, если нет — получить токен (инструкция в
  `.agents/skills/lazyweb-design/SKILL.md`). Запрос-референсы:
  «kanban board mobile», «google calendar month view», «telegram settings»,
  «bottom sheet picker iOS», «segmented control».
- **`webapp-testing`** — Playwright-скрипты (`scripts/with_server.py`). Каждую
  UI-правку проверять в браузере: golden-path + скриншоты до/после. Запускать
  `--help` у скриптов, не читать исходники.
- **`obra/brainstorming`** — для развилок дизайна (какие колонки канбана по
  умолчанию, как ведёт себя completed-таймер). Прогнать перед каждым потоком,
  где есть продуктовая неоднозначность.
- **`obra/writing-plans`, `obra/executing-plans`, `obra/subagent-driven-development`**
  — этот файл создан по `writing-plans`; исполнять по `executing-plans`.
- **`obra/test-driven-development`** + **`testing-async-python`** — тесты бэка
  пишем первыми (failing → green).
- **`obra/systematic-debugging`** — для канбан-бага (Iron Law: root cause до фикса).
- **`tg-bot-api`, `aiogram-3`** — если правки заденут бот-рендер.
- **`defensive-programming`, `python-best-practices`, `code-review`** — на ревью.

### gstack и внешние скилл-репозитории

Юзер дал ссылки: `stop-slop`, `andrej-karpathy-skills`, `taste-skill`,
`gstack`, `mattpocock/skills`, `impeccable`. Это **локальные** скилл-паки:
устанавливаются клонированием в `~/.claude/skills/<name>/` (глобально) или
`.agents/skills/<name>/` (в репо, едет с проектом). Требуется сетевой egress
к github.com — зависит от network policy окружения.

- [ ] Setup-задача (отдельно, до дизайн-работы): склонировать нужные паки в
  `.agents/skills/`, добавить запись в `.agents/skills/CATALOG.md`, проверить
  лицензии (MIT/Apache — ок, проприетарное — нельзя). `gstack` — поставить
  первым, как просил юзер. Если egress закрыт — отложить, сообщить юзеру.
  **Не** коммитить скиллы, которые не используем в этом плане.

---

## Workstream A — Починить и переосмыслить Канбан

**Симптомы от юзера:** карточка «зажимается, отображается», но не
перетаскивается на другие колонки; колонки сейчас = горизонты (Сегодня/Завтра/…),
а должны быть **категории/кастомные колонки** — горизонтам на доске не место.

### A0. Root-cause диагностика (`obra/systematic-debugging`)

Текущая реализация: `webapp/src/components/KanbanView.tsx` (колонки=горизонты,
`useDroppable id=slug`), `webapp/src/App.tsx::handleDragEnd` (App-level
`DndContext`, `PointerSensor` delay 250/tol 5, **без** `collisionDetection`,
**без** `DragOverlay`). Три причины, почему drop не срабатывает:

1. **`touch-action`**: карточка имеет `touch-manipulation` (= `touch-action:
   manipulation`). Для тач-DnD внутри горизонтального скролл-контейнера
   (`overflow-x-auto`) браузер забирает жест на пан скролла — dnd-kit не
   получает pointermove. Нужно `touch-action: none` на draggable-хэндле.
2. **Нет `DragOverlay`**: карточка двигается CSS-трансформом, физически
   оставаясь в исходной колонке. При дефолтной коллизии исходная колонка
   почти всегда выигрывает как `over` → дроп резолвится в ту же колонку →
   no-op. Нужен `DragOverlay` (карточка рендерится в портале-оверлее) +
   `collisionDetection={closestCorners}`.
3. **Горизонтальный скролл vs drag**: контейнер скроллит и перехватывает
   жест. Решение: `touch-action: none` на карточках + опционально автоскролл
   dnd-kit при подносе к краю.

- [ ] Подтвердить каждую причину через Playwright (`webapp-testing`):
  скрипт, который эмулирует pointer-drag карточки в соседнюю колонку и
  ассертит, что `PATCH /tasks/{id}` ушёл. Зафиксировать в PR-описании.

### A1. Архитектура: колонки = категории/разделы (не горизонты)

**Контекст от юзера (скрины Todoist):** на доске Todoist колонки — это
**кастомные «разделы»** (`+ Добавить раздел`), которые юзер создаёт сам, а
не горизонты. Это совпадает с просьбой «на канбане мы уже сами выбираем».

**Решение (вынести в `brainstorming` для финального подтверждения):**
- **Старт (этот поток):** колонки = **категории юзера** (`Category`) +
  служебная «Без категории». Данные уже есть (`Task.category_id`,
  `GET /categories`), создание категории = `apiClient.createCategory`. Дроп
  карточки → `PATCH /tasks/{id} {category_id}`. «+ Раздел» = создать
  категорию. Это даёт юзеру кастомные колонки без миграции и работает
  сразу.
- **Если категории != разделы по смыслу** (юзер хочет разделы отдельно от
  категорий) — завести модель `BoardSection` (таблица `board_sections` +
  `Task.section_id`, миграция, drag-reorder колонок). Это **отдельный план**
  Phase 7f, не раздувать 7e. Решить в brainstorming: хватает ли категорий
  как «разделов».

**Files:**
- Modify: `webapp/src/components/KanbanView.tsx` — колонки строить из
  `categories` (проп), группировать `tasks` по `category_id`; колонка
  «Без категории» для `category_id === null`.
- Modify: `webapp/src/App.tsx` — `handleDragEnd`: для канбан-дропа слать
  `category_id` (не `horizon_slug`); добавить `handleSetCategory(id, catId)`
  → `apiClient.patchTask(id, { category_id })` + bump `boardRefresh` +
  `refreshCategories`. Drag payload карточки несёт текущий `category_id`.
- Modify: `webapp/src/api/client.ts` — `patchTask` уже умеет `category_id`
  (проверить `TaskUpdate`).
- Бэкенд правок не требует (`PATCH /tasks` уже принимает `category_id`,
  см. `app/api/routers/tasks.py:366`).

- [ ] Колонки из категорий + «Без категории».
- [ ] Дроп меняет `category_id`, не `horizon_slug`.
- [ ] Кнопка «+ колонка» = создать категорию (`apiClient.createCategory`),
  inline-инпут в хвосте доски.

### A2. Рабочий DnD (`DragOverlay` + collision + touch-action)

**Files:**
- Modify: `webapp/src/App.tsx` — в `DndContext` добавить
  `collisionDetection={closestCorners}`; рядом с провайдером отрисовать
  `<DragOverlay>` с «снимком» перетаскиваемой карточки (хранить `activeTask`
  в стейте через `onDragStart`).
- Modify: `webapp/src/components/KanbanView.tsx` — на карточке
  `style={{ touchAction: "none" }}` (или утилита), убрать `scale` из transform
  (оверлей берёт визуал); колонка-дроп подсвечивается через `isOver`.

- [ ] `onDragStart` сохраняет активную задачу; `DragOverlay` рендерит её.
- [ ] `closestCorners` + `touch-action:none` → дроп в соседнюю колонку
  коммитит `category_id`.
- [ ] Playwright-тест: drag из колонки A в B меняет категорию (зелёный).
- [ ] Тач-проверка в Telegram (ручная) — карточка тянется пальцем, скролл
  доски не мешает.

### A3. Визуал канбана (Todoist-like, Telegram-native)

Референсы через `lazyweb-design` («kanban board mobile», «todoist board»).
Наш стиль: колонка — лёгкая карточка `bg-bento` со скруглением `rounded-3xl`,
заголовок категории + счётчик-пилюля + `⋯` меню; карточки внутри — `bento-card`
с тенью, приоритет-флажок, чип подзадач `N/M`, due-чип. Горизонтальный скролл
со snap (`snap-x snap-mandatory`), колонка фикс-ширины. Плавный лифт карточки
при захвате (spring), плейсхолдер-«дырка» на месте перетаскиваемой.

- [ ] Колонки и карточки приведены к дизайн-системе (см. Workstream E).
- [ ] Скриншоты до/после в PR.

---

## Workstream B — Календарь уровня Google Calendar

**Симптом:** текущий календарь (`CalendarView.tsx`) — простая месячная сетка
с точками; юзер хочет «как Google Calendar», настраиваемый и красивый.

### B1. Режимы: Месяц / Неделя / День(агенда)

Сегмент-контрол вверху (переиспользовать редизайн `ViewToggle` из E),
выбор сохраняется в CloudStorage (`StorageKeys.lastCalendarView`).

- **Месяц** — текущая сетка, но: задачи показываются «таблетками» прямо в
  ячейке (до 2-3 шт + «ещё N»), а не только точкой; цвет таблетки = цвет
  категории.
- **Неделя** — 7 колонок-дней с временной шкалой слева (часы), события-блоки
  по `due_at`; задачи без времени — в строке «весь день» сверху.
- **День/Агенда** — вертикальный список выбранного дня с временными слотами.

**Files:**
- Modify: `webapp/src/components/CalendarView.tsx` — вынести режимы в
  под-компоненты `CalendarMonth`, `CalendarWeek`, `CalendarAgenda`
  (новый файл `webapp/src/components/calendar/` — раздробить, файл уже растёт).
- Reuse: `lib/format.ts::localDateKey/localTime`.
- Цвет категории: добавить детерминированную палитру по `category_id`
  (`lib/format.ts::categoryColor(id)`), либо хранить цвет в `Category`
  (бэк-правка, опционально — вынести в brainstorming).

- [ ] Месяц с таблетками-событиями + цветами категорий.
- [ ] Неделя с временной шкалой.
- [ ] Агенда дня.
- [ ] Переключение режимов + persist.
- [ ] DnD внутри недели/месяца (перенос на другой день — уже есть в месяце,
  расширить на неделю) — переиспользовать `CALDAY_PREFIX` паттерн.
- [ ] `lazyweb-design` референсы («google calendar week view», «calendar
  agenda mobile»), скриншоты в PR.

### B2. Производительность/данные

Сейчас календарь грузит до 200/500 задач и бакетит на клиенте. Для месяца/
недели достаточно, но заложить серверную фильтрацию по диапазону:

- [ ] (Опционально) `GET /tasks?due_from=&due_to=` — параметры диапазона в
  `app/api/routers/tasks.py`; тест. Если откладываем — явно отметить долг.

---

## Workstream C — «Выполненные», completed_at, авто-архивация

**Симптом/хотелка:** выполненная задача должна оставаться зачёркнутой
(прогресс виден), повторный тап — вернуть в работу; но через ~сутки уезжать
в раздел «Выполненные». Нужен экран «Выполненные» (отдельно от Корзины).

### C1. Бэкенд: `Task.completed_at` (TDD)

**Files:**
- Create: `alembic/versions/..._task_completed_at.py` — колонка
  `completed_at: datetime | None`, nullable, индекс.
- Modify: `app/db/models.py::Task` — поле `completed_at`.
- Modify: `app/bot/services/tasks.py::mark_task_done` — ставить
  `completed_at = utcnow_naive()`; `mark_task_undone` — обнулять. Каскад
  родителя (`_maybe_complete_parent`) — тоже ставит `completed_at`.
- Modify: `app/api/schemas.py::TaskOut` — отдавать `completed_at`.
- Modify: `app/api/routers/tasks.py` — `list_tasks`: новый режим
  `status=done` уже работает; добавить сортировку done по `completed_at desc`.
  Для основного списка: показывать done, завершённые < 24ч назад (linger),
  скрывать старше — параметр `recent_done_hours` или клиентская фильтрация.

- [ ] Тест: `mark_task_done` пишет `completed_at`, `undone` — стирает.
- [ ] Тест: каскад родителя пишет `completed_at`.
- [ ] Миграция применяется (sqlite+pg), `TaskOut.completed_at` в ответе.

### C2. Фронт: linger + экран «Выполненные»

**Files:**
- Modify: `webapp/src/App.tsx::handleDone` — НЕ убирать задачу через 350мс;
  оставлять зачёркнутой, пока `completed_at` < 24ч (клиентский фильтр в
  `loadTasks`/рендере). Повторный тап (`handleReopen`) возвращает в работу.
- Create: `webapp/src/components/CompletedPage.tsx` — список выполненных
  (`apiClient.tasks({ status: "done", include_done: true })`), сгруппирован
  по дню завершения; тап — открыть деталь; кнопка «вернуть в работу».
- Modify: `webapp/src/components/SettingsPage.tsx` — в секции «Данные»
  (рядом с Корзиной) добавить строку «Выполненные» с переходом на
  `CompletedPage` (роут `/completed`, как `/trash`).
- Modify: `webapp/src/lib/router.ts` + `App.tsx` — роут `/completed`.
- Modify: `webapp/src/types.ts` — `Task.completed_at`.

- [ ] Done-задача линджерит зачёркнутой, тап возвращает.
- [ ] Экран «Выполненные» (отдельно от Корзины), переход из настроек.
- [ ] (Опционально) бейдж-счётчик выполненных за сегодня.

> **Разница Корзина vs Выполненные (зафиксировать в UI-копи):** Корзина =
> удалённые (soft-delete, 24ч retention, восстановление). Выполненные =
> сделанные задачи (история достижений, можно вернуть в работу). Это разные
> сущности.

---

## Workstream D — Bottom-sheet и сегмент-контролы (ховеры, обводки, «кнопочность»)

**Симптомы:** нижний bottom-sheet выбора — «белый фон, текст по центру», не
читается как кнопки, нет ховера/обводки; сегмент-контрол «Список/Доска» —
не видно, что это кнопки, нет ховера/активной обводки.

### D1. `BottomSheetSelect` редизайн

**Files:** `webapp/src/components/BottomSheetSelect.tsx`,
`webapp/src/components/BottomSheet.tsx`.

- [ ] Опции-строки: явная «кнопочность» — `bg-bento-card`, обводка
  `ring-1 ring-black/5`, радиус, чёткий ховер (`hover:bg-bento`/легкий tint),
  `active:scale-[0.99]`, увеличенный тач-таргет (≥44px), активная опция —
  заливка `bg-tg-button/10` + галка + жирный акцент-цвет.
- [ ] Заголовок-секция и опциональный `hint` сверху листа.
- [ ] Лёгкая stagger-анимация появления строк.
- [ ] `lazyweb-design` («ios picker bottom sheet», «telegram action sheet»).

### D2. `ViewToggle` (сегмент-контрол) редизайн

**Files:** `webapp/src/App.tsx` (компонент `ViewToggle`) → вынести в
`webapp/src/components/SegmentedControl.tsx` (переиспользуемый: канбан-вид,
календарь-режимы).

- [ ] Явный контейнер-трек `bg-bento` + «пилюля» активного сегмента
  (анимированная, как в BottomNav #109 — sliding capsule), ховер на неактивных,
  читаемый контраст. Чтобы сразу было видно: это переключатель.
- [ ] Переиспользовать в Workstream A (канбан/список) и B (режимы календаря).

---

## Workstream E — Единый дизайн-язык (Telegram / Mira)

**Цель:** свести всё к одной системе — Telegram-native ощущение (как клиент
Telegram и бот Mira на скринах юзера): крупные скругления (`rounded-3xl/[28px]`),
мягкие тени, blur на плавающих элементах, аккуратные секции-карточки,
плавные spring-переходы, консистентные иконки (lucide), tg-theme-цвета.

> **Важно (IP):** делаем СВОЙ дизайн в духе Telegram/Mira/Todoist, повторяя
> паттерны и ощущение, **не** копируя проприетарные ассеты/лейаут 1:1.

### E1. Дизайн-токены и аудит

**Files:** `webapp/tailwind.config.js`, `webapp/src/index.css`, все компоненты.

- [ ] Зафиксировать токены: радиусы, тени (`bento/bento-lg/island`), spacing,
  типографика (`font-display`), motion (`ease-apple`, spring cubic-bezier),
  tg-theme-палитра + светлая/тёмная.
- [ ] Аудит экранов: Header, TaskCard, TaskDetail, NotesList, SettingsPage,
  Calendar, Kanban, BottomSheet — на консистентность токенов.
- [ ] Документ `webapp/DESIGN.md` — короткий гайд по токенам и паттернам
  (чтобы будущие правки не разъезжались).

### E2. Settings → Telegram-native

**Симптом:** настройки не похожи на «настройки внешнего вида Telegram».

- [ ] Секции-карточки с группировкой (как iOS/Telegram settings), иконки в
  цветных «плитках» (`IconTile` уже есть), разделители, chevron, ясная
  иерархия. Добавить превью там, где уместно (например, тон ответов).
- [ ] Ровно те же паттерны строк, что и в BottomSheet (D1) — единый язык.
- [ ] `lazyweb-design` («telegram settings», «ios settings list»).

### E3. Плавность (Todoist-like)

- [ ] Чек-анимация выполнения (галочка + лёгкий haptic + плавное зачёркивание).
- [ ] Spring на открытии bottom-sheet/detail, на переключении табов/сегментов.
- [ ] Карточки: `active:scale`, тень при drag, плейсхолдер при reorder.
- [ ] Проверка плавности на устройстве (60fps, без перерисовок всего списка —
  при необходимости `memo`/ключи).

---

---

## Workstream F — Поповер «Раскладка» (Layout): вид + completed + сорт/фильтр

**Контекст от юзера (скрины Todoist):** на доске есть компактный поповер
«Раскладка» с: переключателем **Список / Доска / Календарь**, тумблером
**«Выполненные задачи»** (показывать/скрывать done прямо в текущем виде),
а также **Группировкой**, **Сортировкой** и **Фильтром** (Срок, Приоритет).
Это объединяет наш `ViewToggle` (D2), переключатель вида и видимость
completed (C) в одно меню. Делаем **свой** аналог в Telegram-стиле, не копируя
1:1.

**Files:**
- Create: `webapp/src/components/LayoutSheet.tsx` — bottom-sheet (на десктопе
  можно поповер) с секциями: Вид (сегмент-контрол из D2), «Показывать
  выполненные» (switch), Группировка (нет/категория/приоритет/горизонт),
  Сортировка (вручную/по дате/по приоритету/по алфавиту), Фильтр (срок,
  приоритет). «Сбросить всё».
- Modify: `webapp/src/App.tsx` — состояние раскладки (вид, showCompleted,
  groupBy, sortBy, filter), persist в CloudStorage
  (`StorageKeys.layoutPrefs`, один JSON ≤4096). Применять к Списку/Доске/
  Календарю.
- Триггер: иконка-кнопка в `Header` (на вкладке «Задачи»), как `⋯`/слайдеры
  у Todoist.

- [ ] Поповер/лист «Раскладка» с переключателем вида (заменяет отдельный
  `ViewToggle`, переиспользует `SegmentedControl`).
- [ ] Тумблер «Выполненные задачи» — показывает/скрывает done в текущем виде
  (связан с linger-логикой из C2).
- [ ] Группировка / Сортировка / Фильтр для списка и доски (минимум: фильтр
  по приоритету и сроку, сортировка по дате/приоритету/вручную).
- [ ] Persist всех настроек раскладки между сессиями (CloudStorage).
- [ ] `lazyweb-design` («filter sort menu», «view options popover»).

> **Объём:** F крупный. Если великоват — расщепить: F1 = вид+completed
> (минимум, заменяет D2), F2 = группировка/сортировка/фильтр. Решить при
> исполнении.

---

## Порядок исполнения (рекомендация)

1. **D** (bottom-sheet + segmented control) — быстрый видимый эффект,
   разблокирует A/B/F (переиспользуют сегмент-контрол `SegmentedControl`).
2. **A** (канбан: фикс DnD + категории-как-колонки) — главная боль юзера.
3. **C** (completed_at + «Выполненные») — бэк+фронт, ценно и самодостаточно.
4. **F1** (поповер «Раскладка»: вид + тумблер выполненных) — объединяет
   переключатель и видимость completed; **F2** (группировка/сорт/фильтр) — позже.
5. **B** (календарь Google-уровня) — самый объёмный, дробить на месяц/неделя/агенда.
6. **E** (дизайн-система) — частично по ходу A–D, финальный проход в конце.

Каждый поток: ветка `claude/7e-<name>` → TDD/Playwright → зелёный CI → PR
(draft) → merge. Обновлять `docs/PROGRESS.md` записью на каждый PR и шапку
`docs/ROADMAP.md`.

## Критерии готовности Phase 7e

- [ ] Канбан: колонки = категории; карточка реально перетаскивается между
  колонками пальцем и мышью; «+ колонка» создаёт категорию.
- [ ] Календарь: месяц/неделя/агенда, события с цветами категорий, перенос
  drag-n-drop, persist режима.
- [ ] Выполненные: linger-зачёркивание, повторный тап возвращает, экран
  «Выполненные» в настройках, `completed_at` в БД.
- [ ] Bottom-sheet и сегмент-контролы: явная кнопочность, ховер, активная
  обводка/пилюля, ≥44px тач-таргеты.
- [ ] Поповер «Раскладка»: переключение вида + тумблер «Выполненные» +
  (F2) группировка/сортировка/фильтр, всё persist'ится.
- [ ] Единый Telegram-native визуал; `webapp/DESIGN.md` есть.
- [ ] Все потоки: ruff+mypy+pytest+tsc+build зелёные; Playwright-проверки на
  ключевые интеракции; скриншоты до/после в каждом UI-PR.

## Известные риски / решения для brainstorming

- Колонки канбана = категории vs кастомные `board_columns` (миграция). Старт
  с категорий; кастомные — позже, если попросят.
- Цвет категории: детерминированная палитра (без БД) vs поле `Category.color`
  (даёт юзер-выбор, но миграция + UI палитры). Старт с детерминированной.
- Авто-архивация done: чисто клиентский linger по `completed_at` (просто) vs
  серверный флаг `archived` (честно, но сложнее). Старт с клиентского + БД
  `completed_at`.
- DnD на тач в Telegram WebView: проверить на реальном устройстве —
  `touch-action:none` + `DragOverlay` обязательны.
