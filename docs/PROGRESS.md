# PROGRESS

Хронологический лог сделанного. Каждая запись = один PR.

Обновляй этот файл в каждом PR в самом конце, перед коммитом.

---

## 2026-05-29 — infra: переезд прод-БД с Neon на Render Postgres

**Контекст.** Прод лёг: внешняя Neon-БД исчерпала free compute-квоту
(`OperationalError: exceeded the compute time quota`), каждый деплой
падал на `alembic upgrade head`, Mini-App показывал «Ошибка
соединения». Решили начать с чистой БД (данные не сохраняли).

**Сделано (инфраструктура, вручную в Render dashboard — у агента нет
доступа к Render API/прод-хостам из-за egress-allowlist окружения).**
- `render.yaml` — добавлен managed-Postgres `plan-app-db` в `databases:`
  и `DATABASE_URL` через `fromDatabase` (PR #169). На практике сервис
  оказался не Blueprint-managed, поэтому переключение сделано руками.
- Создан/задействован Render Postgres `plan-db` (PostgreSQL 16). База в
  регионе **oregon**, web-сервис во **frankfurt** → межрегионально, так
  что используется **External Database URL** (Internal между регионами
  не резолвится). В inbound IP rules добавлен `0.0.0.0/0` (иначе внешний
  трафик заблокирован).
- `DATABASE_URL` на сервисе `plan-app` переключён с Neon на External URL
  Render-БД. Деплой прошёл `alembic upgrade head` на чистой схеме →
  `Application startup complete`. Юзер регистрируется заново через
  `/start`.

**TODO (отложено, не блокирует).** БД в oregon, сервис во frankfurt —
каждый запрос к БД идёт через Атлантик (~150 мс). Пересоздать БД во
frankfurt и переключить на Internal URL для скорости.

**Гейты.** N/A (инфраструктура). Прод проверен вручную: `/healthz` 200,
бот отвечает.

---

## 2026-05-28 — feat: live-draft — прогрессивный статус пайплайна

**Контекст.** Бот показывал статичное «⏳ Разбираю…» весь пайплайн.
Для многосоставных сообщений (несколько задач/заметок) classify+critic
заметно дольше, и пользователю не хватало обратной связи, что что-то
происходит.

**Сделано (backend).**
- `_pipeline.py` — `run_pipeline`/`_run_pipeline_inner` получили
  keyword-параметр `on_stage: StageCallback | None`. После сплита, если
  create-юнитов ≥2, пайплайн один раз зовёт
  `on_stage("✍️ Нашёл N пунктов, раскладываю по полочкам…")` ПЕРЕД
  медленной классификацией. Одиночные сообщения не трогаем — они быстры,
  лишний edit был бы шумом. Хелпер `_plural_ru` для корректного
  склонения. Колбэк best-effort: ошибка edit'а (429/no-op) не роняет
  пайплайн.
- `text.py` / `voice.py` — `_on_stage` редактирует плейсхолдер
  прогресс-строкой; стадии естественно разнесены LLM-вызовами, так что
  rate-limit на `editMessageText` не задевается. Финальный ответ
  по-прежнему идёт через `stream_reply` поверх того же плейсхолдера.

**Тесты.** `test_e2e_pipeline.py`: `on_stage` зовётся ровно раз для
2 юнитов (строка содержит «Нашёл 2»), не зовётся для одиночного;
unit-тест `_plural_ru` на 5 кейсов.

**Гейты.** ruff format/check, mypy (65 файлов), pytest — 537 passed.

---

## 2026-05-28 — ux: skeleton-плейсхолдеры на холодных загрузках

**Контекст.** На первом заходе во вкладку без SWR-кэша экран
показывал пустоту → центрированное «Загружаем…» → резким прыжком
появлялся контент. Это сильнее всего било по первому впечатлению
после открытия Mini-App.

**Сделано (frontend).**
- `components/Skeleton.tsx` — общий набор скелетонов:
  `SkeletonLine`, `SkeletonTaskCard`, `SkeletonNoteCard`,
  `SkeletonList` (task/note), `SkeletonInboxList`,
  `SkeletonAppShell`. Формы совпадают с реальными карточками
  (тот же `rounded-2xl`, `bg-bento-card`, `shadow-bento`,
  `ring-1 ring-black/5`) — когда данные приходят, layout не
  дёргается. Пульс через Tailwind `animate-pulse`, reduced-motion
  глобально его отключает.
- Подключено в местах с холодным гейтом:
  - `App.tsx` — boot-гейт (`loading === true`) → `SkeletonAppShell`
    (хедер + горизонт-табы + 4 карточки).
  - `NotesList` (`notes === null`) → `SkeletonList kind="note"`.
  - `InboxReview` (`reviews === null`) → `SkeletonInboxList`.
  - `CompletedPage`, `TrashPage` (loading flag) → `SkeletonList`.

**Эффект.** На первом кадре пользователь видит готовую структуру
будущего экрана; реальный контент проявляется поверх без визуального
рывка.

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — ux: оптимистичное удаление заметки из детали

**Контекст.** В `NoteDetail` удаление было блокирующим (как раньше в
`TaskDetail`): подтверждаешь — кнопка показывает «Удаляем…», ждёшь
round-trip, потом экран закрывается и список заметок перезагружается.

**Сделано (frontend).**
- `NoteDetail.remove` — по подтверждению сразу `onOptimisticDelete(id)`
  + `onDeleted()`; `apiClient.deleteNote` уходит фоном. После ответа
  `onMutated()` сверяет список; при сетевой ошибке (не 404) тот же
  `onMutated()` рефетчит и возвращает строку.
- `NotesList` — принимает `optimisticDelete: {id, nonce}`, по effect-у
  на `nonce` фильтрует заметку из локального стейта и синхронизирует
  SWR-кэш `notes`.
- `App.tsx` — `handleNoteOptimisticDelete` бампит `nonce`, проброшен
  в `NoteDetail` и `NotesList`.

**Эффект.** Удаление заметки ощущается мгновенным; вся история с
оптимистичным UI теперь закрыта (done, перенос по горизонтам, DnD
канбан/календарь, удаление задачи, удаление заметки).

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — ux: оптимистичное удаление задачи из детали

**Контекст.** Удаление в `TaskDetail` было блокирующим: подтверждаешь —
кнопка показывает «Удаляем…», ждёшь round-trip, и только потом экран
закрывается и список перезагружается. Заметная задержка на частом
действии.

**Сделано (frontend).**
- `TaskDetail.remove` — по подтверждению сразу `onOptimisticDelete(id)`
  (родитель убирает строку из списка) + `onDeleted()` (закрытие
  детали); `apiClient.deleteTask` уходит фоном. После ответа
  `onMutated()` сверяет все вьюхи; при сетевой ошибке (не 404) — тот
  же `onMutated()` рефетчит и возвращает строку, плюс haptic error.
- `App.tsx` — `handleTaskOptimisticDelete` фильтрует задачу из `tasks`
  мгновенно; проброшен в `TaskDetail` как `onOptimisticDelete`.

**Эффект.** Подтверждение удаления ощущается мгновенным — деталь
закрывается, задача исчезает из списка без спиннера.

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — ux: оптимистичный DnD в канбане и календаре

**Контекст.** Перенос карточки между разделами канбана и перетаскивание
задачи на другой день календаря не обновляли UI оптимистично: после
дропа карточка оставалась на месте, затем шёл полный refetch — заметный
рывок. (Перенос по горизонтам в списке уже был оптимистичным.)

**Сделано (frontend).**
- `App.tsx` — `handleSetCategory` и `handleReschedule` диспатчат
  оптимистичный payload (`{id, categoryId|dueAt, nonce}`) сразу при
  резолве дропа; полный refetch (`boardRefresh`/`calendarRefresh`)
  остался только на ветке ошибки — для отката.
- `KanbanView` / `CalendarView` — приняли prop `optimisticMove` /
  `optimisticReschedule`, применяют его локально через effect по
  `nonce` (ре-бакетят карточку в целевую колонку/день без перезагрузки)
  и синхронизируют SWR-кэш текущего окна, чтобы быстрый ре-нав не
  показал устаревшую позицию.

**Эффект.** Дроп ощущается мгновенным; сетевой PATCH идёт фоном, при
сбое список перезагружается и откатывает перемещение.

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — ux: мягкое появление условных блоков (animate-fade-in)

**Контекст.** Пользователь: «когда в настройках переключаю режимы — там
резко пропадает, и нужно много где это сделать». Условные блоки
(ошибки, инлайн-редакторы, раскрываемые секции, кнопки) появлялись и
исчезали жёстким кат-кантом, без перехода.

**Сделано (frontend).**
- `index.css` — добавлена утилита `.animate-fade-in`
  (`fade-in 0.18s ease-out`, мягче и короче `tab-in`, без подъёма, чтобы
  не перетягивать взгляд); расширен блок `prefers-reduced-motion`.
- Класс проставлен на условные ревилы по экранам:
  - `SettingsPage` — баннер ошибки, `SettingsTextRow` (view-строка +
    форма редактирования), `SettingsTimezoneRow` (view-строка + форма +
    кастомный инпут + кнопки пикера). У `Row` добавлен опциональный
    `className` для проброса фейда на view-ветки.
  - `TaskDetail` — баннеры load/save-ошибок, подпись оригинального
    заголовка, секция подзадач.
  - `NoteDetail` — баннеры load/save-ошибок, кнопка удаления.
  - `InboxReview` — ошибка заголовка, ветки textarea/span, блок кнопок
    действий, список дочерних элементов сплита.
  - `Header` — ревил подзаголовка.

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — perf: быстрый старт Mini-App (code-splitting + vendor-чанки)

**Контекст.** Пользователь: «чтобы когда запускаем прям быстро открывался
мини апп». Весь фронт был одним бандлом ~315 kB (93 kB gzip), всё
парсилось на старте.

**Сделано (frontend).**
- `App.tsx` — экраны не из первого пейнта (`TaskDetail`, `NoteDetail`,
  `SettingsPage`, `InboxReview`, `TrashPage`, `CompletedPage`) переведены
  на `React.lazy` + `Suspense` (фолбэк `ScreenFallback`). Префетч чанков
  на `requestIdleCallback` сразу после маунта — первый тап по вкладке не
  ждёт загрузки чанка, фолбэк фактически не виден.
- `vite.config.ts` — `manualChunks`: `react-vendor` (React core),
  `dnd` (@dnd-kit), `vendor` (остальное node_modules). Стабильные
  вендор-чанки кэшируются между релизами — при апдейте кода
  перекачивается только ~20 kB gzip приложения, а не всё.

**Результат сборки.** Главный бандл 315 kB → 63 kB (19.6 kB gzip).
react-vendor 45 kB gzip и dnd 14 kB gzip теперь кэшируются; шесть экранов
вынесены в ленивые чанки (~18 kB gzip суммарно, грузятся в idle/по тапу).
Шрифт уже был `font-display: swap` — FOIT не было.

**Гейты.** webapp `tsc` + `build` — зелёные.

---

## 2026-05-28 — ux: плавность переключения вкладок/режимов + SWR-кэш

**Контекст.** Пользователь: «много где не хватает плавности при
переключении другого режима». Корень — вкладки в `App.tsx` рендерятся
условно, неактивная вкладка **анмаунтится**; при возврате компонент
заново фетчит и показывает спиннер/пустоту, без перехода.

**Сделано (frontend).**
- `webapp/src/lib/cache.ts` (новый) — крошечный module-scoped
  stale-while-revalidate кэш (`getCache`/`setCache`). Переживает
  unmount/remount вкладки, сбрасывается на полном reload WebView.
- `NotesList`, `KanbanView`, `CalendarView` — сидируют начальное
  состояние из кэша и пишут свежие данные на успех. При возврате на вкладку сразу
  виден последний список, фетч идёт в фоне. Календарь кэширует по ключу
  диапазона (`cal:${from}:${to}`), поэтому возврат на посещённый
  месяц/неделю — мгновенный.
- `index.css` — keyframe `tab-in` (fade + лёгкий подъём) + утилита
  `.animate-tab-in`; уважает `prefers-reduced-motion`.
- `App.tsx` — контент вкладок обёрнут в `<div key=...>` с `animate-tab-in`
  (ключ включает `tasksView`, так что список↔доска тоже плавно).
- `CalendarView` — тело Month/Week/Agenda обёрнуто в `<div key={mode}>`
  с тем же fade при переключении режима.

**Заметка про задачи.** Список задач уже живёт в state `App.tsx` (не
анмаунтится), так что не флешит — кэш ему не нужен. «Входящие» оставил
как есть: загрузка завязана на сидирование keep-сетов, риск/выгода не в
пользу трогать.

**Гейты.** webapp `tsc` + `build` — зелёные. Живьём в Telegram-клиенте
не гонял (только сборка/типы).

---

## 2026-05-28 — perf: меньше LLM-латентности в пайплайне

**Контекст.** Продолжение перф-работы (#154). Пользователь жаловался, что
после текста/гс задачи формируются долго. Срезал ещё два круга на
критическом пути.

**Сделано (`app/bot/routers/_pipeline.py`).**
- `detect_intent` + `split_message` теперь идут параллельно через
  `asyncio.gather` — оба бьют по 8b-модели на сырой текст и не зависят
  друг от друга. Раньше split ждал результата intent. Экономия ~целый
  round-trip на каждое сообщение. На редком edit-пути split просто
  отбрасывается (дешёво, уже в полёте).
- `courier_respond` для **одиночного** элемента (`created_task + created_note
  == 1`) форсит `template_only` вместо `mix` — убирает блокирующий
  50/50 LLM-ответ (~100-200ms) на самом частом сценарии «одна задача».

**Гейты.** ruff format/check, mypy, pytest — зелёные.

---

## 2026-05-28 — perf/fix: серверная фильтрация календаря по диапазону

**Контекст.** `CalendarView` тянул **все** задачи (`GET /api/tasks`,
`include_done=true`) и раскладывал по дням на клиенте. Дефолтный `limit=200`
означал, что у пользователей с большим числом задач часть записей молча
не попадала в календарь — это не только перф, но и корректность.

**Бэкенд.**
- `app/api/routers/tasks.py::list_tasks` — два опциональных query-параметра
  `due_at_from` (вкл.) и `due_at_to` (искл.); фильтр
  `Task.due_at >= from` / `Task.due_at < to`. Бездатные задачи естественно
  отсекаются сравнением (спец-фильтра на NULL нет). Композится с остальными
  фильтрами.
- `tests/test_api_endpoints.py::test_tasks_list_filtered_by_due_at_range` —
  Jan/Feb/Mar + undated, проверка что `[Feb-01, Mar-01)` отдаёт только Feb.

**Фронт.**
- `webapp/src/api/client.ts` — `tasks()` принимает `due_at_from`/`due_at_to`.
- `webapp/src/components/CalendarView.tsx` — `useMemo` считает видимое окно
  по режиму (Month: первое число −7д … первое следующего +7д; Week: ±1д;
  Agenda: today−1д … today+180д) → UTC ISO; фетч перезапускается при
  навигации (окно в deps). Буфер съедает tz-сдвиг; точную раскладку по дням
  по-прежнему делает `localDateKey`.

**Поведенческая заметка.** Agenda теперь ограничена окном +180д (раньше была
открытой, но ограничивалась `limit=200`) — приемлемый компромисс для планера.

**Гейты.** ruff format/check, mypy, pytest, webapp tsc+build — зелёные.

---

## 2026-05-28 — chore: archival + ROADMAP truth-up

**Контекст.** В ROADMAP-секции «Что осталось» накопились stale-пункты,
которые уже сделаны (`TaskEvent` для cancel-reminders, Windows TZ-bug,
Bot-рендер subtask-tree). Плюс 21 HANDOFF файл лежал в `docs/` —
гигиена давно просилась.

**Сделано.**
- `docs/archive/` — заведено; **20** старых HANDOFF (v1..v20) переехали
  туда; в `docs/` остались актуальный `v21` + `HANDOFF.md`. Ссылка
  v21 → v20 обновлена на `docs/archive/...`.
- `docs/ROADMAP.md` — вычеркнул всё, что де-факто закрыто:
  `TaskEvent для cancel-reminders` (✅, уже эмитятся события в обоих
  путях отмены), `Windows TZ-bug fix` (✅, починено в `app/shared/time.py`),
  `Bot-рендер дерева подзадач` (✅, рендерится `courier.py::render_subtask_tree`).

**Кода не правил**, гейты остались зелёными.

---

## 2026-05-28 — feat: заметки во «Входящих» (ревью покрывает и notes)

**Контекст.** «Входящие» (вариант Б) флагали `needs_review` только по
числу задач, и в карточке ревью показывали только задачи. Многонотные
сообщения и слабоуверенные заметки проскакивали без проверки. Расширил
ревью на заметки — единая UX, как у задач: keep/drop + правка названия и
категории.

**Бэкенд (`#TBD`).**
- `app/bot/routers/_pipeline.py` — добавил `created_note_count`,
  инкремент в `elif isinstance(row, Note)`, триггер теперь
  `((tasks + notes) >= 2 or any_low_confidence)`.
- `app/api/schemas.py` — `InboxReviewOut.notes: list[NoteOut] = []`,
  `InboxConfirmIn.keep_note_ids: list[int] = []`.
- `app/api/routers/inbox.py` — `/pending` параллельно тянет заметки
  (`Note where source_inbox_id == entry.id`), join с `Category`,
  переиспользует `_note_to_out`. `/confirm` симметрично soft-удаляет
  неотмеченные заметки через `delete_note`. Запись попадает в выдачу
  если есть **хотя бы что-то** из задач/заметок.
- Тесты: +3 API (lists notes / drops unkept notes / back-compat) +1 e2e
  (2 заметки → флаг ревью). 529 → **533**.

**Фронт.**
- `webapp/src/types.ts` — `InboxReview.notes: Note[]`.
- `webapp/src/api/client.ts` — `confirmInbox(id, keepTaskIds, keepNoteIds)`,
  всегда шлёт оба ключа.
- `webapp/src/components/InboxReview.tsx` — секция «Заметки» под задачами
  (если есть): чекбокс keep/drop + название (зачёркнуто когда не оставляем)
  + опц. body-превью первой строки + чип категории (тап → `BottomSheetSelect`
  → `patchNote`) + «Исправить» (textarea → `patchNote`). Никакого
  приоритета/Разбить (у заметок нет). Счётчик «Оставлю N из M» и кнопка
  «Подтвердить» учитывают сумму tasks + notes.

**Гейты:** ruff/mypy/pytest (533) + webapp build — зелёные.

---

## 2026-05-28 — chore: дроп мёртвой колонки `Task.needs_clarification`

**Контекст.** В #149 убрал in-chat clarify-код, но саму колонку оставил
для отдельного reviewed PR. Сейчас закрываю долг.

**Сделано.**
- `app/db/models.py` — поле `needs_clarification` удалено.
- `alembic/versions/.../0017_drop_task_needs_clarification.py` —
  миграция (`drop_column` в upgrade, симметричный `add_column` в
  downgrade с `server_default false`).

**Гейты:** ruff/mypy/pytest (529) — зелёные.

---

## 2026-05-27 — feat: «Разбить» — ИИ-разбивка задачи на подзадачи во «Входящих»

**Контекст.** Финальный слайс «Входящих»: в карточке ревью у задачи теперь
есть кнопка «Разбить» — LLM генерирует 2–5 атомарных подзадач, бэкенд
создаёт их как детей и возвращает фронту для инлайн-рендера. Сделано
двумя сабагентами (бэкенд + фронт) параллельно по зафиксированному
контракту.

**Бэкенд.**
- Новый `app/ai/task_splitter.py` + промпт `app/ai/prompts/task_splitter.md`
  — функция `split_task_to_subtasks(router, title) -> list[str]`,
  Pydantic-схема с cap 5, паттерн как у `detect_intent`.
- `app/bot/services/tasks.py::split_existing_task` — зеркалит дедуп/cap/
  truncate из `_persist_subtasks`, дети наследуют `user_id` /
  `category_id` / `horizon_id` / `priority` родителя.
- `app/api/routers/tasks.py::POST /api/tasks/{id}/split` — auth, **404**
  если не свой/удалён, **409** «task is already a subtask» (`parent_id`
  не null) или «task already split» (уже есть дети), **422** «task is
  already atomic» (LLM вернул пустой), **503** если Groq не настроен.
  Ответ 201 — `list[TaskOut]` с гидрированными `horizon_slug` /
  `category_name`.
- Тесты: happy path + 404 missing/other-user + 409 already-split / is-
  subtask + 422 empty-result.

**Фронт.**
- `webapp/src/api/client.ts` — `splitTask(id) -> Task[]`.
- `webapp/src/components/InboxReview.tsx` — кнопка «Разбить» (иконка
  Split) в правой колонке рядом с «Исправить»; прячется когда
  `subtasks_total > 0`; пока идёт — «Разбиваю…», блокирована. На
  успехе создаваемые подзадачи показываются индентированным списком
  под родителем (`pl-7`, `text-[13px]`, `text-tg-hint`, точка-буллет —
  без чекбоксов: keep-confirm остаётся на уровне родителя). Ошибки
  через тот же error-banner: 422 → «Задача уже атомарная», 503 → «ИИ
  временно недоступен», иначе общая.

**Гейты:** ruff/mypy/pytest **529** (+6) + webapp build — зелёные.

**Закрывает «Входящие» полностью** (см. ROADMAP).

---

## 2026-05-27 — perf: меньше последовательных LLM-вызовов в пайплайне

**Контекст.** После текста/гс задачи формировались долго: `_run_pipeline_inner`
делал слишком много **последовательных** round-trip'ов в Groq. Срезал их,
поведение не меняя.

**Сделано (`app/bot/routers/_pipeline.py`).**
1. Убрал избыточный `_try_reorder` (+ импорты `detect_reorder`,
   `find_task_by_query`, `update_task_horizon`): reorder-интенты уже в
   `EDIT_INTENTS_ALL` и обрабатываются `execute_edit` — fallback был лишним
   LLM-вызовом. `app/ai/reorder.py` не трогал.
2. Per-unit `detect_intent` — распараллелил через `asyncio.gather`
   (был последовательный `for await`), порядок edits/creates сохранён
   через `zip(strict=True)`.
3. Шорткат: для одиночного сообщения (1 unit) per-unit detect не гоняется —
   верхнеуровневый `detect_intent` уже отработал, edit вернулся бы раньше.
4. Цикл критика — распараллелил через `gather(..., return_exceptions=True)`,
   порядок `reviewed` сохранён, на сбое единицы проходят без правки.

**Эффект (последовательные LLM-стадии).**
- Одиночная задача: 5(+критик) → **3(+критик)** — минус 2.
- Сообщение из 3 пунктов: ~8 → **4** round-trip'а.

**Гейты:** ruff/mypy/pytest (523, обновлено 12 e2e-тестов под новую
последовательность вызовов) — зелёные.

---

## 2026-05-27 — feat: выключатель ревью «Входящие» в /settings

**Контекст.** «Входящие» (вариант Б) автоматически шлёт на проверку всё,
где ≥2 задач или низкая уверенность. Не всем это нужно — добавил тумблер
`review_enabled` (по умолчанию **включён**, поведение не меняется). Выкл →
ничего не помечается `needs_review` и нет приписки «📥 Отправил на
проверку…». Сделано двумя сабагентами (бэкенд + фронт) по контракту,
зеркалит существующий `concretize_tasks` end-to-end.

**Сделано.**
- `app/db/models.py` — `UserSettings.review_enabled: bool = True`.
  Миграция `0016_review_enabled` (server_default TRUE → снимаем, чтобы
  совпадало с моделью; SQLite/Postgres).
- `app/bot/services/settings.py` — allow-list `{"on","off"}` + запись.
- `app/api/schemas.py` + `app/api/routers/me.py` — поле в out/update,
  bool→"on"/"off" в PATCH.
- `app/bot/routers/_pipeline.py` — параметр `review_enabled` в
  `run_pipeline`/`_run_pipeline_inner`, гейт `review_enabled and (…)`
  на флаг `needs_review`; проброшен из `text.py`/`voice.py`.
- Фронт: `SettingsPage.tsx` — `SettingsToggleRow` «Входящие» (иконка
  Inbox, `?? true`); `types.ts` — поле в `UserSettings`/`Update`.
- Тесты: e2e «выкл → не флагает и без приписки», PATCH /api/me round-trip.

**Гейты:** ruff/mypy/pytest (523) + webapp build — зелёные.

---

## 2026-05-27 — feat: правка категории и приоритета во «Входящих»

**Контекст.** Слайс 3 «Входящих» после инлайн-правки названия (#150):
в карточке ревью теперь можно сменить и категорию, и приоритет задачи до
подтверждения. Бэкенд не трогали — `PATCH /api/tasks/{id}` уже умеет
`category_id`/`priority`. Чисто фронт.

**Сделано.**
- `webapp/src/lib/priority.ts` — НОВЫЙ общий модуль: вынесены
  `PRIORITY_OPTIONS` + `PRIORITY_LABEL` (были локальными в `TaskDetail`),
  чтобы пикеры жили в одном месте.
- `webapp/src/components/TaskDetail.tsx` — импортирует их из общего
  модуля (поведение без изменений).
- `webapp/src/App.tsx` — прокинул проп `categories` в `<InboxReview>`.
- `webapp/src/components/InboxReview.tsx` — иконка приоритета и чип
  категории стали тапабельными, открывают `BottomSheetSelect` (тот же,
  что в `TaskDetail`). `saveField` дёргает `patchTask` и мерджит ответ +
  локальный оверрайд (для `category_name` чипа) в стейт — без
  перезагрузки. keep/«Подтвердить»/правка названия не задеты.

**Не вошло.** Очистка категории (TaskDetail тоже не очищает — совпали);
`[Разбить]` на подзадачи; выключатель триггера в /settings.

---

## 2026-05-27 — feat: инлайн-правка названия задачи во «Входящих»

**Контекст.** Слайс 2 «Входящих»: до подтверждения можно поправить
название задачи прямо в карточке ревью (AI иногда промахивается с
формулировкой). Бэкенд не трогали — `PATCH /api/tasks/{id}` уже умеет
`{title}`, фронт уже имеет `apiClient.patchTask`. Чисто фронтовый слайс.

**Сделано.**
- `webapp/src/components/InboxReview.tsx` — у каждой задачи кнопка
  «Исправить» (иконка Pencil); тап раскрывает `<textarea>` с текущим
  названием (паттерн из `TaskDetail.tsx`). Сохранение по blur:
  пусто/без изменений → без запроса; иначе `patchTask(id, {title})`,
  локальный стейт патчится сразу (без перезагрузки). Ошибка — баннер
  сверху списка (422 vs общая). Чекбоксы keep и «Подтвердить» работают
  независимо.

**Не вошло.** Правка категории/приоритета во вкладке (только название);
инлайн-дизамбигуация — не относится.

---

## 2026-05-27 — chore: удаление мёртвого in-chat clarify-кода

**Контекст.** Когда «Входящие» (вариант Б) убрали in-chat вопрос
«создать? да/нет», вся его инфраструктура осталась, но перестала
наполняться. Чищу мёртвый код, чтобы не путал.

**Удалено.**
- `app/bot/routers/_pipeline.py` — `PENDING_CLARIFICATIONS`,
  `pop_pending_clarification`, `reset_pending_clarifications_for_tests`.
- `app/bot/routers/callbacks.py` — хендлер `cb_clarify`
  (`clarify:*`), `parse_clarify_callback`, `remove_clarify_buttons`,
  `_CLARIFY_ID_HEX` и осиротевшие импорты.
- Тесты: `test_parse_clarify_*`, `test_remove_clarify_buttons_*`
  (`tests/test_callbacks.py`); ссылки на `PENDING_CLARIFICATIONS` в
  `tests/test_e2e_pipeline.py` (поведенческие проверки — «нет промпта,
  есть указатель на Входящие» — остались).

**Намеренно оставлено.** Колонка `Task.needs_clarification` (никем не
читается/не пишется, кроме дефолта). Дроп — это миграция схемы, вынесу
отдельным PR, чтобы не смешивать с чисткой кода.

**Совместимость.** Старые сообщения с кнопками `clarify:*` (если у
кого-то ещё висят до деплоя) после удаления хендлера на тап не ответят —
приемлемо для удалённой фичи.

---

## 2026-05-27 — feat: редактирование заметок голосом/текстом

**Контекст.** Голосовые правки работали только над задачами. Заметки
(`Note`: title/body/category, soft-delete) нельзя было ни переименовать,
ни перенести, ни удалить голосом. Добавил три интента, различаемые словом
«заметк-» (как «категория» различает категорийные интенты).

**Сделано.**
- `app/ai/schemas.py` — интенты `rename_note`, `delete_note`,
  `set_note_category`; для них `task_query` = строка поиска заметки.
- `app/ai/prompts/intent.md` — правила/примеры; «удали X» без слова
  «заметку» остаётся удалением задачи.
- `app/bot/services/tasks.py` — `find_note_by_query` (ILIKE по title+body,
  самая свежая), `get_note_by_id`, `update_note_title`,
  `update_note_category`, `delete_note` (soft).
- `app/bot/edit_executor.py` — исполнители + ветка в `execute_edit`.
  Заметка резолвится как единственное совпадение (самое свежее), её
  заголовок эхо-показывается в ответе, чтобы поймать неверный выбор.
  Удаление — двухшаговое подтверждение (`edit:ndeldo:` / `edit:ndelno:`).
- `app/bot/routers/callbacks.py` — парсер + хендлер подтверждения.
- Тесты: `tests/test_note_intents.py` (9 кейсов); счётчик интентов в
  `test_edit_i2.py` 14→17.

**Не вошло.** Инлайн-дизамбигуация при нескольких совпавших заметках
(сейчас берём самое свежее + подтверждение для удаления); управление
заметками из Mini-App UI.

---

## 2026-05-27 — feat: управление категориями голосом/текстом

**Контекст.** Раньше голосом/текстом можно было переименовать задачу
(`rename`) и перенести её в категорию (`set_category`, с авто-созданием
категории на лету). Не хватало операций над самой категорией. Phase 3
плана это закладывала («UI создания/редактирования категорий»). Добавил
три интента в существующий детектор (`app/ai/intent.py` →
`edit_executor`).

**Сделано.**
- `app/ai/schemas.py` — в `EditIntent` три новых интента
  (`create_category`, `rename_category`, `delete_category`) + поле
  `category_query` (целевая существующая категория для rename/delete).
- `app/ai/prompts/intent.md` — правила и примеры; ключевое различение:
  слово «категория/категорию» → операция над категорией, а «удали X» без
  него → удаление задачи.
- `app/bot/services/tasks.py` — `find_category_by_name` (регистр-независимый
  поиск **в Python**, т.к. `lower()` в SQLite не сворачивает кириллицу),
  `rename_category`, `delete_category` (отвязывает задачи и заметки →
  `category_id=NULL`, затем удаляет; возвращает число задач).
- `app/bot/edit_executor.py` — исполнители + ветка в `execute_edit` (у
  категорийных интентов нет `task_query`, поэтому до поиска задачи).
  Удаление категории — двухшаговое подтверждение (как у delete задачи,
  G3): кнопки `edit:catdo:<id>` / `edit:catno:<id>`.
- `app/bot/routers/callbacks.py` — парсер + хендлер подтверждения удаления.
- Тесты: `tests/test_category_intents.py` (11 кейсов), обновлён счётчик в
  `tests/test_edit_i2.py` (11→14 интентов).

**Не вошло.** Управление категориями из Mini-App UI (только голос/текст);
ревью/перемещение заметок голосом (по-прежнему только задачи).

---

## 2026-05-27 — feat: «Входящие» — вкладка ревью в Mini-App (слайс 1, frontend)

**Контекст.** Фронтовая половина «Входящих» поверх вчерашнего бэкенда
(`GET /api/inbox/pending`, `POST /api/inbox/{id}/confirm`). Пятая вкладка
в нижней навигации; показывает записи на проверке + распознанные задачи,
галочками убираешь лишнее, «Подтвердить» удаляет неотмеченные. Без
инлайн-правки [Исправить] — это следующий слайс.

**Сделано.**
- `components/InboxReview.tsx` — экран: карточка на запись (транскрипт в
  кавычках + чекбоксы по задачам с приоритет-точкой и категорией),
  «Оставлю N из M» + кнопка «Подтвердить». Оптимистично убирает карточку,
  при ошибке перезапрашивает. Пустое состояние «Всё разобрано».
- `components/BottomNav.tsx` — пятая вкладка «Входящие» (иконка `Inbox`);
  `CELL_PX` 86→68 и лейбл 12→11px, чтобы пять ячеек влезали на телефон;
  опциональный бейдж-счётчик (`badges` prop) на иконке.
- `App.tsx` — `inboxCount` + `loadInboxCount` (бейдж), рендер вкладки,
  `onResolved` рефрешит задачи/счётчики/категории/бейдж. Бейдж проброшен
  во все четыре инстанса `BottomNav`.
- `api/client.ts` + `types.ts` — `pendingInbox()`, `confirmInbox()`,
  тип `InboxReview`.

**Верификация.** `tsc` + `npm run build` чисто. Прогнал реальный браузер
(Playwright, 390px): вкладка рендерит обе сид-записи, чекбокс
переключается, «Подтвердить» убирает карточку (2→1), задачи сразу видны
во вкладке «Задачи» (вариант Б), пятитабовая навигация влезает, бейдж
показывает число на проверке. Скриншоты приложены в чат.

---

## 2026-05-27 — feat: «Входящие» — бэкенд ревью-инбокса (слайс 1, backend)

**Контекст.** Юзер хочет вкладку «Входящие» в Mini-App: когда из голоса/
текста получается ≥2 задач или что-то распозналось неуверенно — они
попадают туда на проверку. Выбран **вариант Б**: задачи создаются сразу,
«Входящие» — экран ревью, где галочками убираешь лишнее и жмёшь
«Подтвердить». Этот PR — серверная половина слайса; вкладка (фронт) идёт
следующим PR.

**Сделано.**
- `db/models.py`: `InboxEntry.needs_review: bool` (default false, indexed).
  Миграция `0014_inbox_needs_review` (NOT NULL + server_default false,
  бэкфилл не нужен).
- `bot/routers/_pipeline.py`: убрал in-chat clarify-ветку «создать?
  да/нет» (низкая уверенность больше не откладывает создание). Теперь
  все распознанные единицы персистятся сразу; если из одного сообщения
  вышло ≥2 задач **или** была единица с `confidence < threshold` —
  помечаем `InboxEntry.needs_review = True` и добавляем в ответ строку
  «📥 Отправил на проверку — открой "Входящие"».
- `api/routers/inbox.py`: `GET /api/inbox/pending` (записи на ревью +
  их топ-уровневые задачи, пустые карточки скрываются) и
  `POST /api/inbox/{id}/confirm` (`keep_task_ids` — оставить отмеченные,
  остальные soft-delete, флаг снять). Owner-check на обоих.
- `api/schemas.py`: `InboxReviewOut`, `InboxConfirmIn`.

**Заметка про регрессию.** До выхода фронта (следующий PR) у low-confidence
/ мульти-задач результатов нет UI для ревью — задачи просто создаются и
ждут во флаге `needs_review`. Окно короткое: вкладка — сразу следующий шаг.

**Верификация.** `pytest` (вся сюита) зелёный; переписан e2e-тест
low-confidence под новое поведение, добавлены тесты pending/confirm
(+ IDOR). `ruff` clean.

---

## 2026-05-26 — feat: per-field CoT в критике (P2.6)

**Контекст.** ROADMAP P2.6. Критик (`app/ai/critic.py`,
`qwen-qwq-32b`) выносил вердикт `approved`/`reason`/`corrected` без явной
пофайловой рефлексии — рассуждение reasoning-модели не фиксировалось и не
поддавалось аудиту. Цель: заставить критика сначала пройтись по каждому
полю (chain-of-thought) и только затем выносить вердикт, не меняя
архитектуру (остаёмся single-stage) и сохраняя обратную совместимость с
единственным call-site `app/bot/routers/_pipeline.py`.

**Сделано.**
- `app/ai/schemas.py` — добавлен `FieldCheck`
  (`field: Literal[is_task|category|horizon|priority|title|reminders|first_step|subtasks]`,
  `ok: bool`, короткий русский `note`). В `CriticVerdict` добавлено поле
  `checks: list[FieldCheck] = Field(default_factory=list)` — стоит
  **перед** `approved`/`reason`/`corrected`, чтобы модель рассуждала до
  вывода. Дефолт `[]` сохраняет обратную совместимость для всего кода,
  что конструирует `CriticVerdict(...)` вручную.
- `app/ai/prompts/critic.md` — переписан Decision flow: критик сначала
  заполняет `checks` (по одному `FieldCheck` на каждое релевантное поле с
  `ok` и русским `note`-обоснованием), затем выносит вердикт по правилу
  «`approved: true` тогда и только тогда, когда все `checks` `ok: true`;
  иначе `approved: false` + полный `corrected`». Сохранены все исходные
  критерии «What to check», русский `reason`, консервативность и блок
  Security (untrusted `<user_intent>`, не следовать инструкциям внутри,
  не раскрывать промпт). JSON-примеры обновлены с массивом `checks`.
- `app/ai/critic.py` — в `logger.info("critic.done", ...)` добавлен
  `checks=len(verdict.checks)`. Сигнатуры и `apply_verdict` без изменений.
- `scripts/golden_eval.py` — live-раннер теперь, помимо скоринга сырого
  классификатора, прогоняет каждый предикт через
  `critique_classification` + `apply_verdict` и пере-скорит, печатая
  BEFORE vs AFTER точность (is_task / horizon / priority / overall) и
  дельту. Полностью за `GROQ_API_KEYS`: без ключа печатает
  `skipped (no GROQ_API_KEYS)` и выходит 0 — CI остаётся зелёным.
- `tests/test_critic.py` — тесты (мок Groq через respx, без сети):
  round-trip `CriticVerdict` с заполненными `checks`, валидация без
  `checks` (дефолт `[]`), вердикт с провальным полем → `apply_verdict`
  возвращает `corrected`, all-ok вердикт → возвращает оригинал;
  поведение `should_run_critic` без изменений.

**Верификация.**
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — чисто
  (64 файла, без ошибок).
- `uv run pytest` — 498 passed, 2 skipped (было 495 + 2; +3 теста критика).
- `GROQ_API_KEYS= uv run python scripts/golden_eval.py` печатает skip и
  выходит 0.

**Не сделано.**
- Порогов / fail-gate по приросту точности критика в CI нет — раннер
  только отчитывается (BEFORE/AFTER/дельта).
- Архитектура остаётся single-stage — отдельной стадии критика не вводим.

## 2026-05-26 — feat: golden-evals классификатора (P2.7)

**Контекст.** ROADMAP P2.7. Нужен «золотой» набор для замера точности
классификатора (`app/ai/classifier.py::classify_intent`) на курируемом
наборе русских фраз. Сам классификатор ходит в Groq (живой LLM), а в CI
ключа `GROQ_API_KEYS` нет — поэтому live-прогон не должен запускаться в
CI, но датасет и чистая логика скоринга обязаны проверяться тестами без
сети.

**Сделано.**
- `tests/golden/ru/cases.json` — 55 реалистичных русских фраз. Каждый
  кейс: `text`, `is_task`, `horizon` (один из 6 слугов), `priority`
  (`low|medium|high`), опциональный `note` с обоснованием. Покрыты явные
  даты, «на неделе», «когда-нибудь», срочное, заметки/не-задачи,
  опечатки, транслит, разговорная речь. Поля `category` в скоринге нет
  (open-vocab).
- `app/ai/golden.py` — чистый, без сети (кроме чтения файла):
  `@dataclass GoldenCase` + `load_cases(path)`; `score_case(expected,
  predicted) -> {is_task, horizon, priority}`; `aggregate(results) ->`
  точность по каждому полю + `overall` (доля кейсов, где все 3 поля
  верны). `category_name` намеренно не оценивается.
- `scripts/golden_eval.py` — CLI-раннер. Без `GROQ_API_KEYS` печатает
  `skipped (no GROQ_API_KEYS)` и выходит `0`. Иначе собирает
  `GroqKeyRouter` из env, гоняет `classify_intent` по всем кейсам
  (`asyncio.run`) и печатает пофайловую/общую точность + до 15
  несовпадений. Запуск вручную/локально, не в CI.
- `tests/test_golden_dataset.py` — CI-safe (без сети): валидация датасета
  (≥50 кейсов, домены `horizon`/`priority`, `is_task` — bool, непустой
  `text`, нет дублей, покрытие всех слугов) + юнит-тесты `score_case` и
  `aggregate` на руками собранных `ClassifierResult`.

**Как запускать live-прогон.**
`GROQ_API_KEYS=gsk_xxx,gsk_yyy uv run python scripts/golden_eval.py`.
В CI крутится только валидация датасета и скоринга — живой прогон
классификатора зашит за `GROQ_API_KEYS` и не дёргает Groq.

**Верификация.**
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — чисто.
- `uv run pytest -q` — 495 passed, 2 skipped (было 486 + 2; +9 тестов).
- `scripts/golden_eval.py` без ключа печатает skip и выходит 0.

**Не сделано.**
- Нет порогов точности / fail-gate в CI — раннер только отчитывается.
- Скоринг `category_name` не реализован (open-vocab, по дизайну).

## 2026-05-26 — feat: TaskEvent для отмены напоминаний (P0.2)

**Контекст.** ROADMAP P0.2. Отмена напоминаний переводила
`Reminder.status` в `"cancelled"`, но не оставляла записи в аудит-логе
`TaskEvent` — в отличие от выполнения, удаления и смены категории задачи
(`mark_task_done`/`delete_task`/`update_task_category`). Из-за этого
история по задаче была неполной: нельзя восстановить, когда и какое
напоминание было отменено.

**Сделано.**
- `app/bot/services/tasks.py` — `cancel_reminder`: после flush, если
  `reminder.task_id is not None`, пишется один
  `TaskEvent(kind="reminder_cancelled")` c payload
  `{"reminder_id", "fire_at" (ISO или None), "scope": "single"}`, затем
  flush и `logger.info("reminder.cancelled", ...)`.
- `app/bot/services/tasks.py` — `cancel_task_reminders`: после цикла
  отмены и flush (чтобы id уже существовали) пишется по одному
  `TaskEvent(kind="reminder_cancelled")` на каждое отменённое напоминание
  с `scope="task"` и `task_id` из аргумента; при пустом списке событий нет.
- Сигнатуры и возвращаемые типы обеих функций не изменены.
- `tests/test_reminder_management.py` — 3 новых теста: одиночная отмена →
  ровно одно событие с `reminder_id` в payload; `cancel_task_reminders` →
  событие на каждое напоминание; «нечего отменять» → новых событий нет.

**Верификация.**
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — чисто.
- `uv run pytest -q` — 486 passed, 2 skipped (было 483 + 2; +3 теста).

**Не сделано.**
- UI/тексты ответов бота не менялись — задача чисто про аудит-лог.
- Отдельной выборки/отчёта по `reminder_cancelled` событиям не добавлено.

## 2026-05-26 — fix: Windows/non-UTC TZ — корректный epoch (P0.1)

**Контекст.** Скрытый баг таймзоны (ROADMAP P0.1). `utcnow_naive()`
возвращает naive-datetime (UTC wall-clock без tzinfo). В `app/api/auth.py`
проверка TTL Telegram-`initData` вычисляла «сейчас» как
`int(utcnow_naive().timestamp())`. Python интерпретирует `.timestamp()` у
naive-datetime в **системной локальной** таймзоне, поэтому на не-UTC хосте
полученный epoch смещён на локальный UTC-offset. Это маскировалось на
Render (`TZ=UTC`), но локально под не-UTC TZ ломало сравнение
`auth_date` (настоящий Unix-epoch от Telegram) с вычисленным `now` — это
реальный баг корректности/безопасности (свежий initData отклонялся 401).

**Сделано.**
- `app/shared/time.py` — добавлены два маленьких хелпера:
  - `utcnow_epoch() -> int` — «сейчас» как настоящий Unix-epoch через
    aware-UTC (`datetime.now(UTC).timestamp()`).
  - `to_epoch(naive_utc) -> int` — конвертация хранимого naive-UTC в epoch
    через явное `replace(tzinfo=UTC)`.
- `app/api/auth.py` — единственный битый call-site (`parse_init_data`,
  стр. 97) переведён с `int(utcnow_naive().timestamp())` на `utcnow_epoch()`.
- Конвенция хранения naive-UTC в БД и остальные вызовы `utcnow_naive()`
  не тронуты — они корректны (используются для сравнений/записи в naive-колонки).
- `tests/test_time_tz.py` — новый детерминированный regression-тест: через
  `time.tzset()` форсит `TZ=America/New_York` и проверяет, что `utcnow_epoch`/
  `to_epoch` совпадают с aware-UTC-epoch, а проверка TTL принимает свежий и
  отклоняет протухший initData независимо от TZ.

**Верификация.**
- До фикса: `TZ=America/New_York uv run pytest` → **45 failed**, 433 passed,
  2 skipped (массово 401/`KeyError` из-за отклонения валидного initData).
- После фикса: `TZ=America/New_York` → **483 passed**, 2 skipped;
  `TZ=Asia/Kolkata` → 483 passed; default-TZ → 483 passed.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy` — чисто.

**Не сделано.** Рефакторинг прочих call-sites не делался: только конвертации
epoch были багом, остальное хранение naive-UTC оставлено как есть.

## 2026-05-26 — security: Phase 7e/G6+G2 — audit-CI + Docker digest

**Контекст.** Два мелких пункта из аудита (Workstream G): G6 — CI-job для
выявления уязвимых зависимостей на каждом PR; G2 (остаток) — пиннинг базовых
Docker-образов по immutable-дайджесту.

**Сделано.**
- `.github/workflows/ci.yml` — новый **отдельный** job `dependency-audit`
  (informational). Python: `uv export --format requirements-txt --no-emit-project
  | uvx pip-audit -r /dev/stdin` (pip-audit запускается эфемерно через uvx по
  залоченным зависимостям). webapp: `npm audit --audit-level=high` в `webapp/`
  (работает по committed `package-lock.json`). Оба audit-шага **non-blocking**
  через `continue-on-error: true` — pre-existing транзитивные advisories не
  блокируют будущие мержи. Новые экшены не добавлялись: переиспользованы уже
  запиненные по SHA `actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node`.
- `Dockerfile` — оба `FROM`-образа запинены по дайджесту (тег сохранён комментом):
  - `node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293`
  - `python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203`
  Дайджесты резолвлены через registry API (mirror.gcr.io из-за rate-limit Docker
  Hub) и кросс-чекнуты против registry-1.docker.io (python совпал byte-to-byte).

**Верификация.** YAML парсится (`yaml.safe_load`). `uv run ruff format --check .`
и `uv run ruff check .` — clean (.py не трогались). Сам CI-job и Docker build
локально не запускались (нет docker-демона/раннера) — расчёт на выверенный
синтаксис и проверенные дайджесты.

**Не сделано / отложено.** `COPY --from=ghcr.io/astral-sh/uv:0.5.4` не пинился
по дайджесту — это `COPY --from`, а не `FROM`-строка (вне scope G2; ghcr требует
отдельного token-flow). Все целевые `FROM`-образы запинены, пропусков нет.

---

## 2026-05-26 — feat: Phase 7e/F2 — «Раскладка»: группировка / сортировка / фильтр

**Контекст.** Workstream F2 плана 7e (дополняет F1). Сделано **субагентом**
(worktree-изоляция, оркестрация); код отревьюен мной (логика чистая,
типизированная). Доки — мной (агент уперся в session-лимит на параллельной
задаче).

**Сделано.**
- Новый `webapp/src/lib/layoutPrefs.ts` — типы + дефолты + валидируемый
  parse/serialize + чистые трансформы `applyFilters`/`applySort`/`groupTasks`.
  `groupBy`: нет/категория/приоритет/горизонт; `sortBy`: вручную/дата/приоритет/
  алфавит; `filterPriority`: все/high/medium/low; `filterDue`: все/просрочено/
  сегодня/неделя. Дата-сорт — nulls-last; due-фильтр через `localDateKey` в tz;
  `addDaysKey` — DST-safe UTC-математика.
- `LayoutSheet.tsx` — секции «Группировка», «Сортировка», «Фильтр» (приоритет +
  срок) + «Сбросить всё»; показываются только в виде «Список».
- `App.tsx` — стейт/гидрация/persist (один JSON-блоб `StorageKeys.layoutPrefs`),
  `visibleTasks` → `applyFilters` → `applySort` → `groupTasks`; при группировке
  список рендерится секциями с `text-tg-link` заголовком. Linger/showCompleted
  не тронуты. Доска эти контролы игнорирует.
- `storage.ts` — ключ `layoutPrefs`.

**Верификация.** `tsc --noEmit` + `npm run build` clean (мной перепроверено
после ребейза на main). UI переиспользует проверенные компоненты; живой
скриншот опущен (экономия лимита) — логика покрыта ревью. Python не тронут.

**Не сделано / отложено.** Группировка/сортировка для доски (сейчас только
список); фильтр по дате с произвольным диапазоном.

---

## 2026-05-26 — security: Phase 7e/G3 — двухшаговое подтверждение free-text delete

**Контекст.** Workstream G3 аудита, митигация **Excessive Agency**. Когда
LLM-конвейер разбора свободного текста (`app/ai/intent.py` →
`app/bot/edit_executor.py`) определял интент `delete`, задача софт-удалялась
сразу. Prompt-injection во входном тексте мог заставить модель выдать `delete`
и стереть чужую задачу без явного намерения пользователя.

**Сделано.**
- `app/bot/edit_executor.py`: новые `_delete_confirm_keyboard(task_id, title)`
  и `_delete_confirmation(task_id, user_id)` — строят промпт «Удалить «<title>»?»
  с инлайн-клавиатурой `[Да, удалить «<title>»]` (`edit:deldo:<id>`) /
  `[Отмена]` (`edit:delno:<id>`) **без мутации** задачи. В `execute_edit`
  одиночный resolved `delete` теперь идёт в `_delete_confirmation`, а не в
  `_execute_delete`; то же для анафоры (LAST_TASK). `_dispatch_single` оставлен
  как есть — `delete` выделен на уровне `execute_edit`/коллбэков.
- `app/bot/routers/callbacks.py`: `parse_edit_delete_confirm_callback` (парсит
  `edit:deldo:` / `edit:delno:`, та же дисциплина что у `parse_edit_undo_callback`)
  и хендлер `cb_edit_delete_confirm`: `deldo` → `_execute_delete` (со снимком для
  undo) и редактирование сообщения в текст удаления + кнопка «Отменить»; `delno`
  → «Отменено» и снятие кнопок, **без** удаления. Дизамбигуация delete из
  свободного текста (`cb_edit_resolve`, `intent_name == "delete"`) тоже уводится
  в подтверждение, а не в немедленное удаление.
- **Явная кнопка 🗑 (`task:delete:<id>` в `cb_task_delete`) — это осознанный тап
  пользователя и остаётся МГНОВЕННОЙ**, её не трогали.
- `tests/test_edit_delete_confirm.py` (+7 тестов): парсер confirm/cancel;
  `delete`-интент создаёт подтверждение и `deleted_at` остаётся `None`; путь
  confirm софт-удаляет; путь cancel оставляет задачу нетронутой.

**Верификация.** `ruff format --check` + `ruff check` + `mypy` clean,
**478 passed, 2 skipped** (было ~471 + 2). Фронт не тронут.

**Не сделано.** Мульти-юнит сообщение, где `delete` — один из нескольких
интентов: ветка `_run_pipeline_inner` объединяет только текст реплаев и теряет
клавиатуру (структурное ограничение конвейера, вне scope). Одиночный free-text
delete и дизамбигуация покрыты полностью.

---

## 2026-05-26 — security: Phase 7e/G4 — security-headers middleware

**Контекст.** Workstream G4 аудита. Сделано **субагентом** (worktree-изоляция,
оркестрация), CSP **доправлен мной** (см. ниже).

**Сделано.** `app/main.py` — `@app.middleware("http") security_headers`:
- На каждый ответ: `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Strict-Transport-Security` (max-age 1y).
- Только на `/app` (Mini-App): `Content-Security-Policy` с
  `frame-ancestors 'self' https://web.telegram.org https://*.telegram.org tg:`.
  **X-Frame-Options НЕ ставим** (сломал бы встраивание в Telegram WebView).
- `tests/test_security_headers.py` (+3 теста): заголовки на `/healthz`; нет
  `X-Frame-Options: DENY/SAMEORIGIN`; нет CSP на `/api`/мета-путях.

**Правка ревью (важно).** Агент задал `script-src 'self'`, но `index.html`
грузит Telegram-SDK с `https://telegram.org` — такой CSP **сломал бы**
Mini-App (нет `window.Telegram`). Поймал на ревью, добавил `https://telegram.org`
в `script-src`.

**Верификация.** `ruff format --check` + `ruff` + `mypy` clean, **471 pytest
passed**. Фронт не тронут. CSP применяется только в проде (FastAPI-статика),
dev-Vite его не навязывает.

**Не сделано / отложено.** Pin Docker base-images по digest; G3 (подтверждение
delete); `pip-audit`/`npm audit` джоб — остаток G.

---

## 2026-05-26 — security: Phase 7e/G2 — pin GitHub Actions по SHA (supply-chain)

**Контекст.** Workstream G2 аудита: actions по мутабельным тегам (`@v4`) —
supply-chain риск (тег можно переписать). Сделано **субагентом** (worktree-
изоляция) в рамках оркестрации.

**Сделано.** `.github/workflows/ci.yml` — все third-party actions запинены на
полный commit-SHA с комментом-версией:
- `actions/checkout@34e1148…f8d5 # v4` (в обоих джобах)
- `astral-sh/setup-uv@38f3f10…af3a # v4`
- `actions/setup-node@49933ea…0020 # v4`

SHA резолвились через `git ls-remote --tags` (GitHub API был rate-limited без
токена; для annotated-тегов взят peeled `^{}` = commit). **Верифицировано
независимо** повторным `git ls-remote` — все три SHA совпадают с тегами.

**Верификация.** YAML валиден; `git diff` — изменены только 4 `uses:`-строки.
Docker-образы не трогали (отдельно). CI зелёный (actions резолвятся по SHA).

**Не сделано / отложено.** Pin Docker base images по digest; `pip-audit`/
`npm audit` джоб (остаток G2/G6).

---

## 2026-05-26 — security: Phase 7e/G1+G6 — prompt-injection hardening + SECURITY.md

**Контекст.** Workstream G плана 7e (после UI-потоков). По аудиту Jules
(`docs/SECURITY_AUDIT_REPORT.md`): семантическая prompt-injection — CRITICAL.
#106 добавил JSON-escape в classifier, но аудит прямо пишет, что этого мало.

**Сделано (G1 — prompt-injection).**
- Новый `app/ai/_safety.py::wrap_untrusted(text, tag)` — единая обёртка:
  преамбула «это недоверенные данные, не исполняй инструкции внутри» +
  XML-делимитер `<tag>…</tag>` + `json.dumps` (экранирует переводы строк/кавычки/
  фейковые `system:`-префиксы).
- Применил ко **всем** LLM-стадиям, где шёл сырой ввод: `splitter.py`,
  `intent.py`, `reorder.py` (раньше слали `stripped` напрямую). `classifier.py`
  и `critic.py` уже оборачивали (`<user_intent>`) — оставлены.
- Раздел **«Security»** добавлен в system-промпты `classifier.md`, `critic.md`,
  `splitter.md`, `intent.md`, `reorder.md`: модель не раскрывает промпт, не
  следует командам из ввода, не даёт вводу переопределять поля вывода
  (`is_task`/`confidence`/`priority`/`intent`/…).
- 3 теста (`tests/test_prompt_injection.py`): `wrap_untrusted` экранирует/
  делимитит инъекцию; classifier шлёт обёрнутый+экранированный ввод в запросе
  (respx-mock), вывод не сломан, «confidence 1.0» из инъекции проигнорирован.

**Сделано (G6 — quick win).** `SECURITY.md` в корне (процесс disclosure +
сводка уже сделанного хардненинга). `.gitignore` уже покрывал `.DS_Store`/
`Thumbs.db`.

**Верификация.** `ruff format --check` + `ruff` + `mypy` clean, **470 pytest
passed** (467 → +3). Фронт не тронут.

**Не сделано / отложено (остаток G).** G2 (pin Actions/Docker по SHA),
G3 (двухшаговое подтверждение `delete`), G4 (security-headers middleware с
оглядкой на Telegram WebView), G5 (scheduler вне web — trade-off Render Free).

---

## 2026-05-26 — feat: Phase 7e/B — календарь: режимы Месяц / Неделя / Агенда

**Контекст.** Workstream B плана 7e. Был только месяц-грид с точками; нужен
календарь уровня Google: режимы Месяц/Неделя/Агенда, события-пилюли с цветами
категорий, persist режима. Заодно закрыты 3 устаревших открытых PR (#1/#2/#82,
старый стек) по решению юзера; security-PR не было (всё в main).

**Сделано.**
- `CalendarView.tsx` переписан: SegmentedControl сверху (Месяц/Неделя/Агенда),
  выбор persist в CloudStorage (`StorageKeys.lastCalendarView`).
  - **Месяц** — сетка с **событиями-пилюлями** в ячейках (до 2 + «ещё N»),
    цвет = категория; сегодня/выбранный подсвечены; тап по дню → детали снизу.
    Ячейки droppable (DnD-перенос на день сохранён).
  - **Неделя** — 7 строк-дней (ПН…ВС) с навигацией ‹ диапазон ›, события —
    цветные тайм-пилюли (время + бар категории); каждый день droppable
    (DnD-reschedule), `touch-action:none` на событиях.
  - **Агенда** — предстоящие задачи, сгруппированы по дню
    (Сегодня/Завтра/дата, акцентные заголовки), grouped-карточка с
    цвет-баром + временем.
- `lib/format.ts`: `categoryColor(id)` — детерминированная палитра (dot/pill/
  text классы) по `category_id`, без БД-поля. «Без категории» → нейтральный.
- `lib/storage.ts`: ключ `lastCalendarView`.

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright,
реальный бэк, задачи с due_at): месяц/неделя/агенда сняты — события с цветами
категорий, persist, today-подсветка. Скриншоты в PR. Python не тронут.

**Не сделано / отложено.** Полная hour-grid неделя (пиксельная шкала часов) —
сейчас компактные день-строки (функционально, Google-mobile-уровень);
серверная фильтрация по диапазону `due_from/due_to` (B2) — клиентская пока ок
для личного объёма; events без времени в «весь день»-строке — отдельно.

---

## 2026-05-26 — feat: Phase 7e/F1 — поповер «Раскладка» (вид + тумблер выполненных)

**Контекст.** Workstream F1 плана 7e (Todoist-style «Раскладка», наш
Telegram-вариант): объединить переключатель вида и видимость completed в одно
меню по иконке в Header. Заодно синхронизированы планерные доки (статус-шапка
плана 7e + `ROADMAP.md`).

**Сделано.**
- Новый `LayoutSheet.tsx` — bottom-sheet «Раскладка»: секция «Вид»
  (`SegmentedControl` Список/Доска, переиспользован) + секция «Задачи» с
  тумблером **«Показывать выполненные»** (строка-кнопка + `Switch`).
- `Header.tsx`: новая кнопка-триггер «Раскладка» (иконка `SlidersHorizontal`);
  кнопка категорий сменила иконку на `ListFilter` (чтобы две кнопки различались).
- `App.tsx`: инлайновый `SegmentedControl` над списком **убран** (переехал в
  поповер, как в плане F1). Состояние `showLayoutSheet`, `showCompleted`
  (гидрация/persist в CloudStorage `StorageKeys.showCompleted`). Фильтр
  `visibleTasks`: при выкл. «Показывать выполненные» done скрываются полностью
  (иначе linger-окно 24ч как раньше).
- `storage.ts`: ключ `showCompleted`.

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright,
реальный бэк): поповер «Раскладка» открывается из Header — вид + тумблер;
выключение «Показывать выполненные» убирает done-задачу из списка (осталось 3
открытых), persist. Скриншоты в PR. Python не тронут.

**Не сделано / отложено.** F2: Группировка / Сортировка / Фильтр (срок,
приоритет) — отдельным PR. «Календарь» как опция вида в поповере (сейчас Calendar
— вкладка навбара). Дальше по плану: B (календарь Google-уровня).

---

## 2026-05-26 — feat: Phase 7e/E — «живые обои» (aurora) + навбар Mira-точнее

**Контекст.** Уточнение юзера по предыдущему проходу (#128): фон не плоский
сине-серый, а **белый с эффектом «живых обоев»** (мягкое синее aurora-свечение,
как на скрине Mira); навбар — неактивные иконка+текст **чёрные**, активный —
синяя пилюля-«кнопка» (iOS-скругление).

**Сделано.**
- **Aurora-фон** (`index.css`): белый base на `<html>`; `<body>`/`#root`
  прозрачны (`#root z-index:1`), фиксированный `body::before` со слоем мягких
  синих radial-градиентов (`--aurora-1..4`), медленный дрейф+«дыхание»
  (`@keyframes aurora-drift`, GPU-`transform`, отключается при
  `prefers-reduced-motion`). Раньше `#root` красил белым поверх — aurora была
  не видна; теперь свечение читается в зазорах между карточками.
- **Декаплинг тинта**: `--bento-bg` (`bg-bento`) теперь отдельный светлый
  сине-серый **только для компонентов** (чипы, треки, плитки канбана, тумблеры),
  не для страничного фона — иначе белый фон сделал бы плитки невидимыми.
- **BottomNav**: неактивные — `text-tg-text` (чёрные, было `tg-hint` серое);
  активная вкладка — `text-tg-button` (синие иконка+лейбл) в пилюле. Точное
  совпадение с навбаром Mira.
- Тёмная тема: aurora на тёмно-синем base.
- `webapp/DESIGN.md` обновлён (aurora-фон + навбар-состояния).

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright,
реальный бэк): список/доска на белом aurora-фоне (синее свечение видно), навбар
крупный план — неактивные чёрные, активная «Задачи» синяя в пилюле. Скриншоты
в PR. Python не тронут.

**Не сделано / отложено.** Микро-полировка остальных экранов, чек-анимация done
с haptic — остаток E. Дальше: F1 (поповер «Раскладка») → B (календарь).

---

## 2026-05-25 — feat: Phase 7e/E — дизайн-проход: фон, навбар как Mira, разделители канбана

**Контекст.** Прямая просьба юзера (со скринами Mira): фон «песчано-синий»
чтобы карточки не сливались; bottom-nav как у Mira (крупнее/понятнее, но в духе
Telegram); разделители колонок канбана (разделы сливались). Стиль = мобильный
Telegram + много iOS. Сверено с `taste-skill` (Inter оставляем — наше
исключение для TG-совпадения; один акцент; тактильность; GPU-анимации только
`transform/opacity`).

**Сделано.**
- **Фон** (`index.css`): `--bento-bg` теперь мягкий сине-серый `#e6eaf2` +
  верхний градиент `--bento-bg-soft`, фиксированный (не наследует tg
  secondary-bg, который бывает белым → карточки сливались). Добавлена тёмная
  тема (`html.dark`: сине-чарко́л). Белые карточки теперь чётко лифтятся.
- **BottomNav** под Mira: крупнее — ячейки 76→86px, иконки 22→25, лейблы
  11→12px, тач-таргет ≥56px, остров `rounded-[30px]` p-2; активная вкладка —
  заметная пилюля `bg-tg-button/14` + ring (было бледное /12).
- **Канбан**: колонка теперь **белая панель** (`bg-bento-card` + `shadow-bento`
  + ring) с header-разделителем (`border-b`), карточки внутри — **тинт-плитки**
  (`bg-bento`). Три уровня глубины (фон→панель→плитка) — соседние колонки больше
  не сливаются. `DragOverlay`-снимок поднимается в белую карточку. «+ Добавить
  раздел» — dashed-панель.
- **`webapp/DESIGN.md`** (Workstream E1): гайд по токенам/поверхностям/
  компонентам/правилам — чтобы будущие правки не разъезжались.

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright,
реальный бэк): список, доска, настройки — все на новом фоне, навбар с пилюлей,
колонки канбана разделены белыми панелями. Скриншоты в PR. Python не тронут.

**Не сделано / отложено.** Полная дизайн-полировка остальных экранов
(TaskDetail/NoteDetail/Calendar микро-правки), чек-анимация done с haptic —
остаток Workstream E. Дальше по плану: F1 (поповер «Раскладка») → B (календарь).

---

## 2026-05-25 — feat: Phase 7e/C (фронт) — экран «Выполненные» + linger-зачёркивание

**Контекст.** Фронт-часть Workstream C поверх бэка (#126). Выполненная
задача должна оставаться зачёркнутой в списке (~сутки), повторный тап —
вернуть в работу; старые done уезжают в отдельный экран «Выполненные»
(≠ Корзина).

**Сделано.**
- `CompletedPage.tsx` — экран «Выполненные»: `GET /tasks?status=done`,
  группировка по дню завершения (Сегодня/Вчера/дата, акцентные заголовки),
  зачёркнутые строки + кнопка «В работу» (reopen → `PATCH status=new`,
  бэк чистит `completed_at`). Empty-state с пояснением (история достижений,
  ≠ Корзина).
- Роут `/completed` (`router.ts` + рендер в `App.tsx`, как `/trash`),
  строка «Выполненные» в Настройках (секция «Данные», над Корзиной).
- **Linger**: `loadTasks` тянет `include_done:true`; render-фильтр
  `visibleTasks` показывает open + done за последние 24ч (старше — только в
  «Выполненных»). `handleDone` больше не убирает задачу через 350мс —
  оставляет зачёркнутой с `completed_at`. Новый `handleReopen`. `TaskCard`
  получил `onReopen`: тап по чекбоксу done-карточки возвращает в работу.
- `types.ts`: `Task.completed_at`. Нормализация наивного/Z-таймстампа в
  фильтре.

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright,
реальный бэк): отметка задачи done → линджерит зачёркнутой в списке (счётчик
«3 задачи» исключает done); экран «Выполненные» — группа «Сегодня» с
зачёркнутой задачей + «В работу»; пустой экран рендерит copy. Скриншоты в PR.
Python не тронут.

**Не сделано / отложено.** Бейдж-счётчик выполненных за сегодня; авто-чистка
linger без перезагрузки (сейчас 24ч-окно вычисляется при рендере, уходит при
следующем `loadTasks`). Прочая полировка — Workstream E.

---

## 2026-05-25 — feat: Phase 7e/C (бэк) — Task.completed_at + сортировка «Выполненных»

**Контекст.** Workstream C плана 7e, бэкенд-часть (TDD). Выполненной задаче
нужен таймстамп завершения — для будущего экрана «Выполненные» и linger-
зачёркивания в Mini-App. Фронт-часть (экран CompletedPage, linger, роут
`/completed`) — следующим PR.

**Сделано (бэк, TDD).**
- Миграция `0014_task_completed_at` — колонка `tasks.completed_at`
  (`DateTime`, nullable, индекс `ix_tasks_completed_at`), `batch_alter_table`
  (SQLite-safe), без бэкафилла. 0014 — единственный head.
- `Task.completed_at: datetime | None` (indexed).
- `mark_task_done` ставит `completed_at = utcnow_naive()`; каскад родителя
  (`_maybe_complete_parent`) — тоже. `mark_task_undone` обнуляет (и у
  авто-переоткрытого родителя).
- `TaskOut.completed_at` отдаётся в API; `_task_to_out` маппит поле.
- `GET /tasks?status=done` сортируется по `completed_at DESC NULLS LAST`,
  затем `created_at DESC` (legacy done без completed_at — в конце).
- 2 теста: done ставит/undone стирает completed_at; каскад родителя
  ставит/обнуляет.

**Верификация.** `ruff format --check` + `ruff` + `mypy` clean, **467 pytest
passed** (465 → +2). Миграция в цепочке (`alembic history`/`heads`). Фронт
не тронут.

**Не сделано / отложено (фронт C, следующий PR).** `CompletedPage.tsx`
(список выполненных, группировка по дню, «вернуть в работу»); linger-
зачёркивание в `App.handleDone` (не убирать done сразу, пока `completed_at`
< 24ч); роут `/completed` + строка в Настройках; `types.ts Task.completed_at`.

---

## 2026-05-25 — feat: Phase 7e/E2 — Настройки в Mira-стиле: grouped-карточки + iOS-тумблер

**Контекст.** Прямая просьба юзера (со скринами бота Mira): сделать раздел
«Настройки» как в Mira — секции-карточки, drill-in к функциям, чтобы можно
было «выключить/включить». Workstream E2 плана 7e (вынесли вперёд по просьбе).
Применён `redesign-skill` (с поправкой: Inter оставляем — он намеренно
совпадает с клиентом Telegram; один акцент `tg-button`).

**Сделано.**
- Новый `webapp/src/components/Switch.tsx` — iOS/Telegram-тумблер (трек-пилюля
  + слайдящийся knob, заливка `tg-button` во включённом, spring-переход).
  Режим `presentational` (рендер без вложенной кнопки, когда вся строка-кнопка
  обрабатывает клик).
- Редизайн `SettingsPage.tsx` под Mira-grouped-list:
  - Секции = **единая скруглённая карточка** на секцию (`rounded-3xl
    bg-bento-card` + `divide-y` между строками), как iOS/Mira (раньше —
    отдельная карточка на каждую строку).
  - **Акцентные заголовки** секций (`text-tg-link`, sentence-case) вместо
    серых uppercase.
  - Секции переименованы: «Основные» → «Профиль» (как в Mira).
  - Булева настройка «Первый шаг» (`concretize_tasks`) теперь **iOS-тумблер**
    (вся строка кликабельна, `aria-pressed`) вместо bottom-sheet с on/off —
    это и есть запрошенное «выключить/включить». Подсказка в подзаголовке.
  - Stagger-появление секций (`sheet-row-in`, per-section delay).
  - Строки-примитивы `Row`/`RowLabel` (grouped-list), чёткие ховер/актив.
  - Удалён `CONCRETIZE_OPTIONS` (заменён тумблером).

**Верификация.** `tsc --noEmit` + `npm run build` clean. E2e (Playwright на
реальном бэке SQLite + Vite, валидный initData): экран «Настройки» снят
целиком — все 6 секций grouped-карточками с цветными плитками и акцентными
заголовками; тумблер «Первый шаг» переключён OFF→ON, PATCH сохранился,
knob уехал вправо. Скриншоты в PR. Python не тронут.

**Не сделано / отложено.** Полноценные drill-in под-страницы на отдельных
роутах (как Mira Daily) — bottom-sheet пикеры уже дают drill-in для
мультивыбора; отдельные роуты — если попросят. Прочая дизайн-полировка —
Workstream E.

---

## 2026-05-25 — feat: Phase 7e/A — рабочий канбан: колонки = категории, фикс DnD

**Контекст.** Workstream A плана 7e (главная боль юзера). Канбан #118
был сломан: карточка «зажималась», но не перетаскивалась между колонками,
а колонки были по горизонтам (Сегодня/Завтра/…) — юзер просил **категории/
разделы** (как Todoist «+ Добавить раздел»). Root-cause (диагностика в плане,
§A0): нет `touch-action:none` (горизонтальный скролл крал тач-жест), нет
`DragOverlay` (карточка двигалась CSS-трансформом, оставаясь в исходной
колонке → дефолтная коллизия резолвила дроп обратно), дефолтная
collisionDetection.

**Сделано (бэк, TDD).**
- `update_task_category` принимает `None` (очистка категории).
- `PATCH /api/tasks/{id}` различает явный `category_id: null` (очистить —
  дроп в «Без категории») от отсутствия ключа (без изменений) через
  `model_fields_set`. Раньше `is not None` не давал очистить категорию.
- 3 теста: смена категории, очистка явным null, omitted-ключ не стирает.

**Сделано (фронт).**
- `KanbanView.tsx` переписан: колонки = **категории** (проп `categories`)
  + служебная «Без категории» (`category_id === null`). Дроп карточки →
  `PATCH category_id` (или null). Дроп-таргеты с префиксом `kcat:` (не
  пересекаются с горизонт-пилюлями списка). Карточка вынесена в
  презентационный `KanbanCardView` (общий с DragOverlay).
- DnD-фикс: `touch-action:none` на карточке; `DragOverlay` (рендерит
  «снимок» карточки в портале, оригинал затемняется `opacity-40`);
  `collisionDetection={closestCorners}` на App-`DndContext`;
  `onDragStart` сохраняет активную задачу. Колонка подсвечивается `isOver`.
- «+ Добавить раздел» в хвосте доски — inline-инпут, создаёт категорию
  (`apiClient.createCategory`) = новую колонку.
- `App.tsx`: `handleSetCategory(id, catId|null)`, `handleCreateCategoryColumn`,
  канбан-ветка в `handleDragEnd`, `DragOverlay` в портале.
- `types.ts`: `TaskUpdate.category_id?: number | null`.
- Горизонтальный snap-скролл (`snap-x snap-mandatory`).

**Верификация.** `ruff format --check` + `ruff` + `mypy` clean, **465 pytest
passed** (462 → +3). `tsc --noEmit` + `npm run build` clean. E2e: подняты
реальные FastAPI (SQLite) + Vite, инжектнут валидный initData, Playwright
протащил карточку «Купить продукты» из «Дом» в «Работа» — `PATCH
/api/tasks/3 {category_id:1}` → 200, БД подтверждает, доска перерисовалась
(Дом 1→0 «Пусто», Работа 2→3). Скриншоты до/после в PR.

**Не сделано / отложено.** Тач-проверка в реальном Telegram WebView (ручная);
визуальная полировка карточек/колонок (приоритет-флажок, due-чип) — в
Workstream E; кастомные колонки-`BoardSection` отдельно от категорий —
Phase 7f, если попросят.

---

## 2026-05-25 — feat: Phase 7e/D — SegmentedControl + редизайн BottomSheetSelect

**Контекст.** Workstream D плана 7e. Симптомы юзера: сегмент-контрол
«Список/Доска» не читался как кнопки (нет ховера/активной обводки);
bottom-sheet выбора — «белый фон, текст по центру», опции не выглядели
тапабельными. Этот поток разблокирует A/B/F (переиспользуют сегмент-контрол).

**Сделано.**
- Новый `webapp/src/components/SegmentedControl.tsx` — переиспользуемый
  iOS/Telegram-style сегмент-контрол: трек `bg-bento` + hairline-ring,
  одна **анимированная sliding-капсула** активного сегмента (тот же приём
  translateX, что в BottomNav #109, soft-spring cubic-bezier), ховер на
  неактивных, поддержка иконок (lucide), generic по value-типу,
  тач-таргеты ≥44px (size=md). Заменил инлайновый `ViewToggle` в `App.tsx`
  (List/Board теперь с иконками ListTodo/LayoutGrid). Готов к F1
  (Список/Доска/Календарь) и B (режимы календаря).
- Редизайн `webapp/src/components/BottomSheetSelect.tsx` — опции теперь
  **карточки-кнопки**: поверхность `bg-bento`, hairline-ring, ≥44px,
  чёткий ховер (tint + усиление обводки), `active:scale`; активная опция —
  акцентная заливка `bg-tg-button/10` + ring + лейбл акцентом/semibold +
  круглая синяя галка. Stagger-анимация появления строк
  (`sheet-row-in` keyframe в `index.css`, per-row delay). Добавлен
  опциональный проп `hint` (подзаголовок листа).

**Верификация.** `tsc --noEmit` clean, `npm run build` clean. Изолированный
Playwright-harness (chromium /opt/pw-browsers) — скриншоты bottom-sheet и
обоих сегмент-контролов (2- и 3-сегментный, со слайдом капсулы) в PR.
Python не тронут.

**Не сделано / отложено.** Применение `SegmentedControl` в календаре (B) и
поповере «Раскладка» (F1) — в своих потоках. Десктоп-поповер-вариант листа
(F) — позже.

---

## 2026-05-25 — feat: Phase 7d — выбор «Список/Доска» сохраняется в prefs

**Контекст.** Тумблер List/Board (#118) сбрасывался на «Список» при
каждой перезагрузке Mini-App. Финальный штрих Phase 7d.

**Сделано.**
- `lib/storage.ts`: новый ключ `StorageKeys.lastTasksView`.
- `App.tsx`: гидрация `tasksView` из CloudStorage (валидируется
  `"board" | "list"`); сохранение через `storageSet` при переключении
  тумблера. Синхронизируется между клиентами Telegram (CloudStorage).

**Верификация.** `tsc --noEmit` clean, `npm run build` clean. Фронт.

**Итог Phase 7d.** Календарь (месячная сетка) + drag-n-drop по дням +
канбан по горизонтам + сохранение вида. Осталось опционально:
недельный режим календаря, канбан по категориям, серверная фильтрация
календаря по диапазону.

---

## 2026-05-25 — feat: Phase 7d — канбан-доска с drag-n-drop по горизонтам

**Контекст.** Юзер прямо просил канбан («не списком… а можно было в
канбан самому двигать, передвигать»). Слайс 3 Phase 7d.

**Сделано.**
- `KanbanView.tsx` — горизонтально-скроллящиеся колонки по горизонтам
  (today→someday). Колонка — `useDroppable` (id = слаг горизонта),
  карточки — `useDraggable` (в `data` текущий горизонт). Дроп карточки
  на колонку = переиспользует `handleMove` (тот же путь, что хорайзон-
  пилюли). Компактная карточка с чекбоксом (complete) + тап (open) +
  чип N/M подзадач. Колонка подсвечивается при наведении.
- `App.tsx`:
  - Сегмент-контрол `ViewToggle` («Список / Доска») над вкладкой
    «Задачи»; `tasksView` стейт.
  - `boardRefresh` счётчик — бампается в `handleMove` / `handleDone`,
    чтобы доска пересобиралась после drag/complete.
  - `handleDragEnd` horizon-ветка теперь берёт текущий слаг из
    drag-payload, если задачи нет в App.tasks (board-карточки живут в
    своём стейте) — корректно отсекает no-op дропы.
- `api/client.ts`: тип query у `tasks()` дополнен `limit` +
  `include_subtasks`.

**Верификация.** `tsc --noEmit` clean, `npm run build` clean. Фронт.

**Не сделано / отложено.** Недельный режим календаря; канбан по
категориям (сейчас по горизонтам); сохранение выбора List/Board в
CloudStorage prefs (сейчас сбрасывается на «Список» при перезагрузке).

---

## 2026-05-25 — feat: Phase 7d — drag-n-drop задач между днями календаря

**Контекст.** Слайс 2 Phase 7d поверх календаря (#116): теперь задачу
можно перетащить на другой день — `due_at` сдвигается, локальное время
сохраняется.

**Сделано.**
- `CalendarView.tsx`:
  - День-ячейка вынесена в `DayCell` с `useDroppable`
    (`id = "calday:<YYYY-MM-DD>"`); при наведении перетаскиваемой
    задачи — подсветка `ring-2 + bg`.
  - Задачи дня — `DraggableTaskRow` с `useDraggable`, в `data` кладётся
    текущий `due_at` (чтобы App мог пересчитать сдвиг). Done-задачи не
    таскаются.
  - Экспорт `CALDAY_PREFIX`.
- `App.tsx`:
  - `handleDragEnd` расширен: если `over.id` начинается с `calday:` —
    берём `dueAt` из drag-payload, считаем дельту в днях между старым и
    новым локальным ключом, сдвигаем UTC-таймстамп на `delta*24ч`
    (локальное время-суток сохраняется, DST-края — редкое исключение),
    патчим. Хорайзон-пилюли работают как раньше.
  - `handleReschedule(id, dueAtIso)` — PATCH `due_at` + бамп
    `calendarRefresh` + `loadCounts`.
  - `tz` поднят к стейту (был объявлен после колбэков — TDZ в deps).

**Верификация.** `tsc --noEmit` clean, `npm run build` clean. Только
фронт.

**Не сделано / отложено.** Недельный режим; канбан по статусам;
серверная фильтрация календаря по диапазону (сейчас клиентская, лимит
200 задач).

---

## 2026-05-25 — feat: Phase 7d — вкладка «Календарь» (месячная сетка)

**Контекст.** Вкладка «Календарь» в Mini-App была заглушкой
(`ComingSoon`). Первый слайс Phase 7d — реальная месячная сетка задач
по датам.

**Сделано.**
- `webapp/src/components/CalendarView.tsx` — новый компонент:
  - Месячная сетка 6×7 (понедельник-первый), навигация ‹ / › по
    месяцам, заголовок «Месяц Год».
  - Задачи с `due_at` фетчатся (`include_done=true`) и бакетятся по
    локальному дню в tz юзера.
  - День с задачами помечен точкой (синяя / зелёная если все done),
    сегодня — кольцом, выбранный день — заливкой.
  - Тап по дню раскрывает список его задач под сеткой (со временем),
    тап по задаче открывает детали (тот же роут `/task/:id`).
- `webapp/src/lib/format.ts` — `localDateKey` (YYYY-MM-DD в tz юзера,
  чтобы задача в 23:30 не утекала в следующий UTC-день) и `localTime`.
- `App.tsx` — `ComingSoon` для календаря заменён на `CalendarView`;
  новый `calendarRefresh` счётчик бампается при mutate (done /
  detail-edit), чтобы сетка перезагружалась.
- Удалён неиспользуемый `ComingSoon.tsx` (единственное применение
  было на этой вкладке).

**Верификация.** `tsc --noEmit` clean, `npm run build` clean, 462
pytest passed (python не тронут). Только фронт.

**Не сделано / отложено (следующие слайсы Phase 7d).**
- Drag-n-drop задачи между днями календаря (сейчас только просмотр +
  открытие).
- Недельный режим.
- Канбан-доска по статусам / категориям.
- Перетаскивание в календаре требует @dnd-kit drop-target на ячейках.

---

## 2026-05-25 — ui: пояснения к режиму «Первый шаг» в настройках Mini-App

**Контекст.** Тоггл «Первый шаг» в SettingsPage показывал опции
«Добавлять / Не трогать» без объяснения — новый юзер не понимал, что
это за режим. Исходный запрос явно просил «режим показан / понятен».

**Сделано.**
- `webapp/src/components/SettingsPage.tsx`: `CONCRETIZE_OPTIONS`
  получили `hint`:
  - Добавлять → «Абстрактную задачу превращаю в конкретный первый
    шаг 🎯 — „создать презентацию“ станет „сделать первый слайд“.»
  - Не трогать → «Сохраняю формулировку ровно так, как ты сказал.»
  `SelectRowProps.options` тип расширен полем `hint?`.
- `webapp/src/components/BottomSheetSelect.tsx`: hint-строка опции
  больше не `truncate` (резала пояснение в одну строку) — теперь
  переносится (`leading-snug`), чтобы длинные подсказки читались
  целиком. Касается всех select-пикеров, но полезно везде.

**Верификация.** `tsc --noEmit` clean, `npm run build` clean. Только
фронт, Python не тронут.

**Не сделано / отложено.** Бот-сайд `/settings` для concretize_tasks
показывает label «Первый шаг в задачах» (уже описательнее), отдельные
описания опций в боте — отдельно, если понадобится.

---

## 2026-05-25 — feat: авто-завершение родителя по последней подзадаче

**Контекст.** UX-долг из #108: завершив последнюю подзадачу проекта,
юзер видел родителя всё ещё открытым с полным чипом 3/3 — читается как
баг. Нужен каскад вверх.

**Сделано.**
- `app/bot/services/tasks.py`:
  - `_active_sibling_count` — считает незакрытых детей родителя.
  - `_maybe_complete_parent` — после завершения ребёнка, если открытых
    сиблингов 0, авто-закрывает родителя (`TaskEvent` source
    `subtask_cascade`). Один уровень вглубо (внуков не поддерживаем).
  - `mark_task_done` дёргает каскад в конце.
  - `mark_task_undone` — зеркально: переоткрытие ребёнка переоткрывает
    авто-закрытого родителя (родитель больше не complete).
- Каскад работает на обеих поверхностях (API patch + bot callback),
  т.к. обе идут через `mark_task_done`.
- 3 теста: авто-complete на последнем ребёнке, reopen возвращает
  родителя, атомарная задача (parent_id=None) без сайд-эффектов.

**Верификация.** 455 → после merge с rate-limiting веткой 462 passed,
ruff + mypy clean.

**Не сделано / отложено.** Уведомление юзеру «проект закрылся
автоматически» — `_maybe_complete_parent` возвращает родителя, но
callers пока не surface'ят это в текст. Добавить тост при желании.

---

## 2026-05-24 — feat: per-user rate limiting на LLM-пайплайн (CRIT-2)

**Контекст.** Из security-ревью: один юзер (или утёкший токен) мог
заспамить сотни сообщений в минуту → сотни Groq-вызовов → реальные
деньги (denial-of-wallet). Точка входа `text.py` / `voice.py` дёргала
пайплайн без всякого throttle.

**Сделано.**
- Новый `app/bot/rate_limit.py` — token-bucket в памяти процесса,
  keyed по telegram user_id. `capacity = rate_limit_burst`, refill
  `rate_limit_per_minute / 60` токенов/сек. Lock-free (asyncio
  кооперативный, один поток). `prune()` чистит полностью-наполненные
  idle-бакеты чтобы память не росла.
- `app/shared/config.py`: `rate_limit_per_minute=20`, `rate_limit_burst=10`.
  `per_minute=0` полностью выключает.
- `text.py` + `voice.py`: перед DB/Groq дёргают `get_rate_limiter().allow(uid)`;
  при отказе — мягкий ответ «слишком много сообщений подряд» и ранний
  return, лог `ratelimit.{text,voice}_throttled`.
- 7 тестов: disabled-режим, burst→throttle, refill во времени,
  per-user изоляция, cap на refill, prune, singleton.

**Верификация.** 459 passed (+7), ruff + mypy clean.

**Не сделано / отложено.** Перенос в Redis при масштабировании на
несколько воркеров (сейчас один Render-процесс — dict достаточно).
API-rate-limiting на `/api/*` эндпоинты — отдельно, там initData-auth
уже отсекает анонимов. Периодический вызов `prune()` из scheduler —
опционально, память и так bounded числом активных юзеров.

---

## 2026-05-24 — prompt: classifier + critic эмитят first_step / subtasks (#110)

**Контекст.** Поля `first_step` (#107) и `subtasks` (#108) уже в БД и UI,
но classifier их почти не возвращал: прежние примеры в промпте были про
lifestyle-цели («научиться играть на гитаре»), поэтому «создать
презентацию» / «организовать день рождения» сходили за атомарные задачи
и фичи не стреляли.

**Сделано.**
- `app/ai/prompts/classifier.md`: расширил список triggering-глаголов
  (`создать / сделать / подготовить / написать / разработать /
  организовать / спланировать / разобраться / научиться / освоить`).
  Default toward emitting — `null` теперь только для truly atomic.
- Новая секция **Subtasks** с правилами (max 5, атомарные, не путать
  с first_step).
- Новые примеры: «создать презентацию про природу» → first_step;
  «организовать день рождения» → subtasks; «подготовить презентацию
  для клиента к среде» → subtasks (4 шага); «до пятницы отчёт» теперь
  тоже получает first_step.
- `app/ai/prompts/critic.md`: чек-лист дополнен пунктами 7–8
  (first_step / subtasks), `corrected` пример теперь содержит оба поля
  чтобы LLM-корректор не занулил их случайно.

**Верификация.** 449 passed, ruff + mypy clean. Только промпт-файлы,
кода нет.

**Не сделано / отложено.** Golden evals на 50 фраз — отдельный PR
(требует ручной разметки эталонов). Пересекается с PR-H.

---

## 2026-05-24 — ui(BottomNav): Telegram-style pill with sliding capsule (#109)

**Контекст.** Юзер просил навбар «как в Telegram» — глубже скругление,
сильнее blur, плавный переезд active-вкладки.

**Сделано.**
- Внешний pill: `rounded-3xl → rounded-[28px]`, `backdrop-blur-xl →
  backdrop-blur-2xl`, opacity 85% → 80%.
- Внутренние ячейки: `rounded-[22px]`, width фиксирован 76px чтобы
  капсула могла слайдиться через `translateX(i * 76)`.
- Абсолютно-позиционированный capsule `bg-tg-button/12` за иконками;
  слайдится с iOS-spring easing `cubic-bezier(0.32, 0.72, 0.20, 1.05)`.
- Active icon: `scale-110` + `strokeWidth=2.4`.
- Per-cell background убран — теперь рендерит только капсула, иначе
  при слайде получался double-fill flash.

**Верификация.** `tsc --noEmit` clean, `npm run build` clean
(261.51 kB → не изменился). Без новых deps (framer-motion не понадобился).

**Не сделано.** Тесты на компонент — UI-only, проверка глазами.

---

## 2026-05-24 — feat: Subtasks с parent_id, classifier subtasks[], UI чек-лист (#108)

**Контекст.** Юзер говорит «организовать день рождения» — это не
атомарная задача, а проект. До этого PR всё ложилось в одну строку
и юзер сидел уставившись в неподъёмный пункт.

**Сделано.**
- **БД:** `Task.parent_id: int | None` — self-FK на `tasks.id`,
  `ON DELETE CASCADE`. Миграция 0013, индекс на `parent_id` для
  GROUP BY.
- **Classifier schema:** `subtasks: list[str] | None`.
- **Persist:** новый `_persist_subtasks` после создания родителя
  заводит детей с inheritance category/horizon/priority. Cap 5,
  дедуп пустых, обрезка >256 символов.
- **API:** `TaskOut.parent_id`, `subtasks_total`, `subtasks_done`
  (агрегаты считаются одной `GROUP BY` без N+1). Новый `TaskDetailOut`
  с массивом `subtasks: TaskOut[]` для `GET /tasks/{id}`. Список задач
  по умолчанию скрывает детей (`parent_id IS NULL`), `?include_subtasks=true`
  возвращает плоский список.
- **Mini-App:** `Task` тип расширен, новый `TaskDetail`. `TaskCard`
  показывает чип `📋 N/M` (зелёный когда все done). `TaskDetail`
  рендерит секцию «Подзадачи» с прогрессом и чекбоксами; toggle
  оптимистичный + патч на бэк.
- **Тесты:** 7 новых (persist inheritance, cap=5, дедуп, null;
  list скрывает детей и считает агрегаты; детальный hydrated).

**Верификация.** 447 passed (+6), ruff format + check + mypy + tsc
clean.

**Не сделано / отложено.** Bot-рендер дерева в чате (Unicode ◯/●) —
отдельный PR. Каскадное завершение (родитель done когда все дети done)
— UX-добавка, опционально.

---

## 2026-05-24 — feat: FirstStep rewrite — actionable title + 🎯 (#107)

**Контекст.** Поле `first_step` уже было в `ClassifierResult`, но в БД
лилось как `description="Шаг 1: …"`. В детальной карточке это было
закопано, в списке не видно вообще — фича не стреляла.

**Сделано.**
- **БД:** `Task.title_original: str | None`. Миграция 0012, без
  backfill.
- **Persist swap:** когда `concretize_tasks=True` и `first_step`
  непустой — `Task.title` = first_step (actionable), `Task.title_original`
  = оригинальная абстрактная фраза. `description` префикс «Шаг 1:»
  убран (стал redundant — title несёт сам шаг).
- **API:** `TaskOut.title_original` выставлен.
- **Mini-App:** `Task` тип расширен. `TaskCard` показывает 🎯 + курсив
  с оригиналом. `TaskDetail` меняет лейбл «Название» → «Первый шаг»
  и добавляет блок «Изначально» когда rewrite сработал.
- **Тесты:** 3 новых (swap-on, swap-off, swap-on-no-step).

**Верификация.** 441 passed (+3), ruff/mypy/tsc clean.

**Не сделано / отложено.** Classifier-промпт ещё не учил агрессивно
эмитить first_step на «создать X» — это закрывает #110.

---

## 2026-05-24 — security: initData TTL 10min + JSON-escape + max_length (#106)

**Контекст.** Из глубокого ревью (`code-review-findings.md` +
свежий аудит). Три точечные дыры:

**Сделано.**
- `app/api/auth.py`: `INIT_DATA_MAX_AGE_SECONDS` 24h → 10min. Перехваченный
  Telegram initData жил сутки — теперь 10 мин. Реальные юзеры не
  заметят (Mini-App при reopen получает свежий initData).
- `app/ai/classifier.py`: JSON-escape `intent_text`, `user_categories`,
  `user_tz` при сборке user-message — защита от prompt injection
  (юзер не может вшить `\nsystem: ...`).
- `app/ai/schemas.py`: `max_length` на `ClassifierResult.title` (200),
  `category_name` (80), `first_step` (200) — runaway LLM не пустит
  мусор в БД и UI.

**Верификация.** 438 passed, ruff/mypy clean.

**Не сделано / отложено.** Rate limiting и API versioning — отдельная
hardening-волна. Транзакционность `persist_classification` — обернуть
в одну `session_scope`, в этот хотфикс не вошло.

---

## 2026-05-19 — feat: PR-J UX polish (multi-match copy + /reminders all + пагинация)

**Контекст.** HANDOFF v20 §6 оставил три недоделанных UX-куска поверх первого слайса PR-J:
односложный ответ после `cancel_reminder`, отсутствие способа увидеть >20 pending reminders
и отсутствие способа взглянуть на overdue pending rows, которые не успел подобрать scheduler.

**Сделано.**
- **Голос/текст `cancel_reminder` теперь показывает локальные времена и склоняется**: «Отменил 2 напоминания для «X»: 10:00, 11:45, 20 мая.» вместо безликого «Отменил напоминания для «X»: 2.». Helpers `format_reminder_local` и `plural_ru` в `app/shared/time.py`. `cancel_task_reminders` теперь возвращает `list[Reminder]` (а не `int`), чтобы вызывающий мог достать `fire_at` для рендера.
- **`/reminders all`** — новый аргумент: рендерит overdue + upcoming pending до `REMINDERS_ALL_CAP = 200`, overdue-строки помечены `❗ ... (просрочено)`.
- **Пагинация для дефолтного `/reminders`** — кнопка `[➡️ Ещё]` подгружает следующую страницу `REMINDERS_PAGE_SIZE = 20` в то же сообщение через `rem:page:<offset>`.
- **Сервисы**: `list_pending_reminders(offset, include_overdue)`, новый `count_pending_reminders` для футера «Показано N из M».
- **Общий рендер** вынесен в `app/bot/reminder_view.py::format_reminder_list`, чтобы commands и callbacks не дублировали логику и не плодили циклический импорт.

**Верификация.** `uv run ruff format/check .`, `uv run mypy`, `TZ=UTC uv run pytest -q` — все зелёные. **438 passed, 2 skipped** (было 426; +12 новых тестов в `tests/test_reminder_management.py`, включая overdue-маркер, footer, pluralization, paging offset, валидацию `rem:page:<n>` callback'а и копи `_execute_cancel_reminder`).

**Не сделано / отложено.**
- `TaskEvent` для cancel-reminders — осознанный долг из v20 §7, отдельный PR.
- Подмеченный пре-существующий грабельник: на Windows без `TZ=UTC` падают API/soft-delete тесты, потому что `utcnow_naive().timestamp()` на naive datetime трактуется как local. На Render/CI с TZ=UTC маскируется. Заведу отдельной мини-задачей.

---

## 2026-05-19 — feat: reminder management (PR-J)

PR-J добавляет первый слой управления напоминаниями:

- **/reminders**: показывает ближайшие pending-напоминания с локальным временем пользователя.
- **Inline отмена**: кнопки `rem:cancel:<id>` отменяют только pending-напоминание текущего пользователя.
- **Голос/текст intent**: `cancel_reminder` отменяет все pending-напоминания найденной задачи, не удаляя саму задачу.
- **Сервисы**: `list_pending_reminders`, `cancel_reminder`, `cancel_task_reminders`.
- **Follow-up**: `/reminders` показывает только будущие pending-напоминания;
  просроченные pending-строки остаются задачей scheduler-а, но не засоряют
  пользовательский список upcoming reminders.

---

## 2026-05-18 — feat: needs clarification UI (PR-K)

PR-K внедряет промежуточное уточнение для неуверенных классификаций:

- **_pipeline.py**: Перехват интентов, где `confidence < 0.7`.
  Сохранение `(cr, resolved, inbox_id, user_id, timestamp)` в
  глобальный словарь `PENDING_CLARIFICATIONS` с уникальным `uuid`.
- **Inline клавиатура**: Пользователю отправляется клавиатура
  с кнопками `[Да, создать]` и `[Нет, отмена]`.
- **callbacks.py**: Обработка кнопок с авторизацией (отсечение IDOR)
  и TTL в 5 минут (чтобы не было утечек памяти).
- **Слияние логики**: При подтверждении используется `persist_classification`.
  Обновление текста происходит через склейку старого текста и результата.
- **PR-L включён в этот же открытый PR**: фактически убраны SQLModel
  `DeprecationWarning` в `app/bot/services/tasks.py` и
  `app/workers/scheduler.py` (`session.execute()` → `session.exec()`).

---

## 2026-05-11 — feat: undo (TaskEditSnapshot) (PR-I4)

PR-I4 добавляет поддержку отмены последнего edit-действия:

- **TaskEditSnapshot** (`app/db/models.py`): новая таблица для хранения
  снимков изменений полей — `field`, `old_value`, `new_value`,
  `task_id`, `user_id`, `created_at`. CASCADE delete при удалении задачи.
- **Alembic migration 0011**: создание таблицы `task_edit_snapshots`.
- **Snapshot saving** (`edit_executor.py`): каждый executor (complete,
  delete, reopen, reorder_horizon, rename, set_due, set_priority,
  set_category, reorder_time) сохраняет снимок перед возвратом ответа.
  Функция `_save_snapshot()` + `_undo_keyboard()`.
- **Inline кнопка [Отменить]** (`edit_executor.py`, `callbacks.py`):
  при успешном выполнении edit-действия к ответу прикрепляется
  inline-кнопка `[Отменить]` с callback `edit:undo:<snapshot_id>`.
- **Undo handler** (`callbacks.py`): `cb_edit_undo` обрабатывает callback,
  проверяет lazy TTL (5 мин), восстанавливает `old_value` через
  `_apply_undo()`, удаляет inline-кнопку после отмены или истечения TTL.
- **12 новых тестов** (`tests/test_edit_i4.py`): snapshot CRUD, keyboard
  format, parse callback, executor returns snapshot, _apply_undo для
  status/title/deleted_at/priority, execute_edit returns undo kb.
- **Итого тестов: 412** (400 → 412).

---

## 2026-05-11 — feat: context + multi-intent + list_done (PR-I3)

PR-I3 добавляет контекстные фичи поверх intent-based editing:

- **LAST_TASK анафоры** (`edit_executor.py`): in-memory dict
  `{user_id: (task_id, timestamp)}` с TTL 60с. Обновляется при
  `persist_classification`, `execute_edit`, `cb_edit_resolve`.
  Если `intent.task_query` пуст → используется последняя задача.
- **PENDING_EDITS** (`edit_executor.py`): `{user_id: (EditIntent, timestamp)}`
  для multi-match disambiguation — I2 интенты (rename, set_due и пр.)
  сохраняют полный EditIntent для callback `edit:resolve:`.
- **Multi-intent** (`_pipeline.py`): после `split_message` каждый unit
  проходит через `detect_intent` — edit-интенты выполняются сразу,
  create-интенты идут в обычный classify/persist pipeline. Смешанные
  сообщения поддерживаются (edit + create в одном тексте).
- **list_completed_today** (`edit_executor.py`): read-only интент `list_done` —
  показывает задачи завершённые сегодня (JOIN Task ↔ TaskEvent.kind=completed).
- **EDIT_INTENTS_ALL** расширен до 10 (I1:4 + I2:5 + I3_READONLY:1).
- **Callback handler** (`callbacks.py`): `cb_edit_resolve` использует
  `pop_pending_edit` для I2+ интентов, `touch_last_task` при каждом resolve.
- **12 тестов** (`tests/test_edit_i3.py`): LAST_TASK TTL, PENDING_EDITS,
  anaphora, multi-match storage, list_completed_today, execute_edit dispatch.
- **E2E тесты** обновлены для multi-intent mock sequences (+per-unit intent).
- Итого: 400 тестов, все зелёные.

---

## 2026-05-11 — feat: edit executors — rename/set_due/set_priority/set_category/reorder_time (PR-I2)

PR-I2 расширяет intent-based редактирование задач из PR-I1:

- **Новые executors** (`app/bot/edit_executor.py`): `_execute_rename`,
  `_execute_set_due`, `_execute_set_priority`, `_execute_set_category`,
  `_execute_reorder_time`. Каждый в собственной `session_scope`.
- **Новые сервисы** (`app/bot/services/tasks.py`): `update_task_title`,
  `update_task_due_at`, `update_task_priority` — все логируют `TaskEvent`.
- **Парсинг дат**: `_execute_set_due` и `_execute_reorder_time` используют
  `dateparser.parse` с `languages=["ru"]` и `PREFER_DATES_FROM=future`.
- **Pipeline**: `EDIT_INTENTS_ALL` объединяет I1 + I2 (9 интентов), pipeline
  роутит все через `execute_edit`.
- **13 новых тестов** (services + executors + dispatch).
- Итого 390 тестов, все зелёные (2 skipped — webapp/dist).

Файлы: `app/bot/edit_executor.py`, `app/bot/services/tasks.py`,
`app/bot/services/__init__.py`, `app/bot/routers/_pipeline.py`,
`tests/test_edit_i2.py`.

---

## 2026-05-11 — feat: voice/text task editing — complete/delete/reopen (PR-I1)

PR-I1 добавляет первый набор intent-based редактирования задач через
голос и текст:

- **EditIntent schema** (`app/ai/schemas.py`): Pydantic модель с 12
  типами intent (create, complete, delete, reopen, rename, set_due,
  set_priority, set_category, reorder_horizon, reorder_time, list_done, none).
- **detect_intent()** (`app/ai/intent.py`): LLM-вызов через
  `llama-3.1-8b-instant` + instructor для определения intent пользователя.
  Короткие сообщения (<2 символов) сразу возвращают `none` без вызова LLM.
- **Промпт** (`app/ai/prompts/intent.md`): системный промпт с 13
  few-shot примерами на русском.
- **Executors** (`app/bot/edit_executor.py`): `_execute_complete`,
  `_execute_delete`, `_execute_reopen`, `_execute_reorder_horizon`.
  Каждый работает в собственной `session_scope`.
- **find_tasks_by_query()** (`app/bot/services/tasks.py`): поиск задач
  по ILIKE-паттерну. Возвращает `list[Task]` (до 5 совпадений).
  Поддержка `include_done` для поиска завершённых задач.
- **Multi-match**: если >1 совпадение — inline-клавиатура с кнопками
  `edit:resolve:<intent>:<task_id>`. Callback-обработчик в
  `callbacks.py` через `parse_edit_resolve_callback()`.
- **Pipeline integration** (`app/bot/routers/_pipeline.py`):
  `detect_intent` вызывается ДО `_try_reorder`. Для create/none
  intent — fallback на прежний pipeline.
- **Тесты**: 17 новых тестов (schema, detect_intent с respx-моками,
  find_tasks_by_query, executors, execute_edit dispatch). Обновлены
  e2e pipeline тесты для нового intent-detection шага.

Файлы: `app/ai/intent.py`, `app/ai/schemas.py`, `app/ai/prompts/intent.md`,
`app/bot/edit_executor.py`, `app/bot/services/tasks.py`,
`app/bot/services/__init__.py`, `app/bot/routers/_pipeline.py`,
`app/bot/routers/callbacks.py`, `tests/test_edit_intent.py`,
`tests/test_e2e_pipeline.py`.

---

## 2026-05-11 — feat(bot): richer morning/evening digest sections (PR-G)

PR-G доводит утренний и вечерний дайджесты до спеки `docs/PLAN.md §2.5`.
Раньше:

- Утренний: только список «Сегодня».
- Вечерний: «осталось сегодня + завтра».

Теперь:

**Утренний** (`build_morning_digest`):
1. `🌅 Доброе утро!`
2. `Сегодня:` — задачи горизонта `today`, status ≠ done (как было).
3. `Просрочено:` — открытые задачи с `due_at < локальное начало сегодня`,
   отсортированы oldest-first, лимит 5. Формат строки — `<icon> <title> — ДД.ММ HH:MM`.
4. `Горячие дедлайны на неделе:` — открытые задачи с `due_at` в окне
   `[конец сегодня; +7 дней)`, отсортированы по ближайшему дедлайну, лимит 5.
   Задачи горизонта `today` исключаются (они уже в секции «Сегодня»).
   Если всё пусто — fallback на «На сегодня задач не запланировано — лёгкого дня.».

**Вечерний** (`build_evening_digest`):
1. `🌙 Подводим итоги дня.`
2. `Закрыто сегодня — N ✅` + список title'ов — задачи, у которых есть
   `TaskEvent(kind="completed")` с `created_at` внутри сегодняшнего
   user-local дня. Дедуп по `task.id` (если задачу закрыли → переоткрыли →
   снова закрыли, она засчитывается один раз). Лимит 10, новейшие первыми.
3. `Осталось на сегодня:` — горизонт `today`, status ≠ done.
4. `Завтра:` — горизонт `tomorrow`, status ≠ done.
5. Если открытых нет и закрытых тоже нет — «Сегодня всё закрыто 🎉.»
   (если только закрытые — победный счётчик уже стоит, второй «всё закрыто»
   не дублируем).

**Хелперы и техника**

- `app/bot/digest.py:_local_day_bounds_utc(user_tz, now_utc)` →
  `(today_start_utc, today_end_utc)` как naive UTC. Локальное «сегодня»
  вычисляется в пользовательской TZ, потом конвертируется обратно в UTC
  для сравнения с `Task.due_at` / `TaskEvent.created_at` (схема хранит
  naive UTC — см. `app/shared/time.py`).
- Новые async-хелперы: `_tasks_overdue`, `_tasks_urgent_week`,
  `_tasks_completed_today`. Все исключают soft-deleted (`deleted_at IS NOT NULL`).
- `_format_task_line_with_date` — рендер `<icon> <title> — ДД.ММ[ HH:MM]`,
  midnight трактуется как date-only (без HH:MM).
- `build_morning_digest` / `build_evening_digest` получили kw-only
  `now_utc: datetime | None = None` — тесты могут зафиксировать «сегодня»
  без monkeypatch'инга `datetime.now`. Прод-вызовы (`tick_digests`,
  `refresh_pinned_morning`) пробрасывают свой `now`.
- `OVERDUE_LIMIT = 5`, `URGENT_WEEK_LIMIT = 5`, `COMPLETED_TODAY_LIMIT = 10`
  — константы модуля, чтобы потом легко настроить.

**Pinned-morning (Phase 6.3)** работает без изменений: `refresh_pinned_morning`
вызывает обновлённый `build_morning_digest`, новые секции автоматически
попадают в пин и live-обновляются по мере закрытия/добавления задач.

**Тесты**

- `tests/test_digest.py` — 6 новых кейсов:
  - `test_morning_digest_includes_overdue` — overdue секция + done task
    с overdue due_at не попадает.
  - `test_morning_digest_includes_urgent_week` — окно next-7-days,
    today-горизонт не дублируется, >7d не попадают.
  - `test_morning_digest_limits_overdue_to_top_five` — `OVERDUE_LIMIT`
    отсекает на 5.
  - `test_evening_digest_includes_completed_today` — счётчик + список +
    yesterday-event не попадает.
  - `test_evening_digest_dedupes_reopened_task` — задача с двумя
    `completed`-эвентами за день засчитывается один раз.
  - `test_evening_digest_skips_completed_for_other_user` — изоляция
    между пользователями.

Все 355 тестов плана зелёные. `ruff`/`mypy`/webapp build — чисто.

---

## 2026-05-11 — feat(ops): in-process keep-alive self-ping (Render free-tier)

Render Free спускает web-dyno в idle после ~15 минут без входящих
запросов. Из-за этого: (а) первый запрос после простоя висит 30–60 сек,
пока dyno стартует; (б) пока dyno спит, in-process scheduler
(`app/workers/runner.py`) тоже спит — реминдеры и daily digest не
тикают. У юзера это проявлялось как «бот просыпается ~10 минут».

Закрыли по образцу `voice-bot` (commit `b7d387a`, см.
`Itosyro/voice-bot:src/main.py::_self_ping`): в lifespan FastAPI-приложения
запускается фоновая asyncio-задача, которая каждые 10 минут делает
`GET` на собственный публичный `WEBHOOK_BASE_URL + /healthz`. Запрос
уходит наружу и возвращается как обычный внешний HTTP — Render
считает это активностью и сбрасывает idle-таймер. Внешний пингер
(GitHub Actions / cron-job.org) больше не нужен, но совместим.

**Backend**
- `app/workers/keepalive.py` (НОВЫЙ): `run_keepalive_loop`,
  `start_keepalive`, `stop_keepalive`. Зеркало `runner.py` по форме —
  `(task, stop_event)`-tuple / grace shutdown / лог-теги `keepalive.*`.
  httpx (уже в зависимостях) вместо aiohttp из voice-bot.
- `app/shared/config.py`: добавлены `keepalive_enabled`,
  `keepalive_interval_seconds=600`, `keepalive_initial_delay_seconds=60`,
  `keepalive_timeout_seconds=10` + property `keepalive_url`. Property
  возвращает `None` если `webhook_base_url` пуст — в тестах и локалке
  цикл стартует, но `keepalive_url` пуст → ветка в lifespan не
  включается, всё тихо.
- `app/main.py`: импорт `start_keepalive`/`stop_keepalive`, отдельный
  `keepalive_handle` рядом с `scheduler_handle`. Запуск гейтится
  `settings.keepalive_enabled and settings.keepalive_url`. Стоп в
  `finally` идёт до scheduler/bot — таймауты симметричны runner'у.
- `render.yaml`: новые env vars `KEEPALIVE_ENABLED=true`,
  `KEEPALIVE_INTERVAL_SECONDS=600`. Комментарий шапки обновлён —
  теперь упоминает keepalive и говорит выключать его на Starter+.
- `docs/RENDER.md`: переписана секция топологии (in-process self-ping
  вместо внешнего пингера как primary), добавлена таблица env vars,
  внешний пингер оставлен как опциональный «belt-and-braces». Раздел
  «Upgrading to Starter+» теперь также упоминает `KEEPALIVE_ENABLED=false`.

**Tests** (+5)
- `tests/test_keepalive.py`:
  - `test_loop_pings_url_until_stopped` — respx mock на `/healthz`,
    проверяем что роут вызван ≥1 раз и таск чисто завершается на
    `stop.set()`.
  - `test_loop_swallows_errors` — первая попытка кидает
    `httpx.ConnectError`, вторая ОК → ожидаем `counter >= 2`
    (одна ошибка не убивает цикл).
  - `test_start_and_stop_round_trip` — `start_keepalive` → ждём пинг →
    `stop_keepalive` с grace=1s; `task.done()` и роут вызван.
  - `test_stop_keepalive_noop_for_finished_task` — стоп уже
    завершённой таски не падает (зеркало `test_runner.py` контракта).
  - `test_loop_returns_immediately_if_stopped_during_initial_delay` —
    стоп в окне `initial_delay` корректно short-circuit'ит.

**Baseline**
- `uv run pytest -q` — 336 passed, 2 skipped (webapp/dist в CI не билдится)
- `uv run ruff format --check . && uv run ruff check . && uv run mypy app` — clean
- `cd webapp && npm run typecheck && npm run build` — clean (bundle 258 KB)

**Note on PR #82.** В нём отдельно лежит ещё `.github/workflows/keepalive.yml`
(GitHub Actions cron каждые 10 мин) + slash-команды для бота. Этот PR
ортогонален: in-process self-ping надёжнее (нет дрейфа cron у GitHub
Actions) и не зависит от того, активен ли репозиторий на GitHub. PR #82
можно мерджить когда хочется — он только добавит запасной внешний
пингер. Удалять keepalive.yml оттуда не нужно: оба работают вместе.

---

||||||| b8f0652
## 2026-05-11 — feat: friendlier bot replies + recognised-card inline keyboard + make-it-concrete (PR-E)

PR-E переписывает ответ бота после разбора входящего сообщения. Раньше
бот возвращал сухой текст вида «Принял.\n📌 задача: Купить хлеб · Покупки\n…».
Теперь:

1. Подтверждение стало живой фразой («Окей, разобрал.», «Лови карточку»,
   «Готово, мой господин» — зависит от стиля). Без сухих «Принял»/«Записал»,
   с ограничением «не больше одной эмодзи на фразу» (юзер прямо просил).
2. Список распознанного уехал из текста в *inline-keyboard* —
   «карточку распознанного». Каждая распознанная единица = одна кнопка-строка:
   - ☐ задача → тап переводит её в ✅ (статус `done` в БД), повторный тап
     возвращает в работу (статус `new`, событие `reopened` в `task_events`).
   - 📄 заметка → тап даёт toast «Заметка», но БД не трогает. Удаление/архив
     заметок остаются на mini-app и голосовые команды.
3. Опциональный «make-it-concrete» режим: классификатор может предложить
   первый 5–15-минутный шаг (`first_step`) для абстрактных задач («научиться
   играть на гитаре»). По умолчанию off — включается в настройках бота
   и mini-app переключателем «Первый шаг» (`concretize_tasks`). При включении
   `first_step` записывается в `Task.description` префиксом `Шаг 1: …`.

**Backend**
- `app/ai/courier.py` — `SummaryItem` dataclass (kind/title/category_name/
  persisted_id/status), `build_summary_keyboard(items)`, `flip_item()`,
  обновлён `courier_respond()` → `tuple[str, InlineKeyboardMarkup | None]`.
  Шаблоны подтверждений переписаны: drop dry-acks, max 1 эмодзи/фраза.
- `app/ai/schemas.py::ClassifierResult` — добавлено опциональное поле
  `first_step: str | None`.
- `app/ai/prompts/classifier.md` — раздел «First step (optional, only for
  tasks)» с примерами и правилами (≤80 символов, императив, конкретное
  физическое действие на сегодня).
- `app/bot/courier_templates.py` — переписан `WELCOME_*`, `WAITING_FOR_NAME`,
  `NAME_PERSONALIZED` под живой тон + 1 эмодзи на ключевой шаг.
- `app/bot/routers/_pipeline.py` — `run_pipeline()` теперь возвращает
  `tuple[str, InlineKeyboardMarkup | None]` (`PipelineReply`). Принимает
  `concretize_tasks: bool`. Во время persist-цикла собирает `list[SummaryItem]`
  из персистнутых строк и передаёт его в `courier_respond`.
- `app/bot/routers/text.py`, `app/bot/routers/voice.py` — анпак tuple-ответа,
  чтение `concretize_tasks` из `UserSettings`, передача `reply_markup=keyboard`
  в `stream_reply`.
- `app/bot/routers/callbacks.py` — новый хендлер
  `cb_summary_toggle` на `summary:toggle:<kind>:<id>`:
  - kind=task → `mark_task_done` / `mark_task_undone`, флипает префикс ☐↔✅,
    рефрешит pinned-morning digest.
  - kind=note → toast «Заметка — не требует действий», БД не трогает.
  Парсинг payload вынесен в чистую функцию `parse_summary_toggle_callback`
  (зеркалит R-NEW-I-1 дисциплину — никаких unguarded `int(parts[N])` в
  хендлерах).
- `app/bot/routers/settings.py` — добавлен `concretize_tasks` в SETTING_LABELS
  + CONCRETIZE_OPTIONS (on/off), интегрирован в `_setting_value`.
- `app/bot/services/settings.py::ALLOWED_SETTING_VALUES` — добавлен
  `concretize_tasks: frozenset({"on", "off"})`, конвертация on/off → bool
  в `update_user_settings`.
- `app/bot/services/tasks.py` — `mark_task_undone()` (event `reopened`),
  `_build_task_description()` (склейка first_step при concretize=True),
  `persist_classification()` принимает `concretize_tasks: bool`.
- `app/bot/streaming.py::stream_reply` — параметр `reply_markup`; markup
  крепится только на финальном edit (чтобы клавиатура не моргала во время
  streaming-эффекта).
- `app/db/models.py::UserSettings` — поле `concretize_tasks: bool` (default
  False, nullable=False).
- `alembic/versions/2026_05_11_1100-0010_concretize_tasks.py` — миграция
  (SQLite-aware: `"0"` для sqlite, `false()` для остальных диалектов;
  server_default снимается сразу после backfill).

**API + Mini-App**
- `app/api/schemas.py::UserSettingsOut`/`UserSettingsUpdateIn` — добавлено
  `concretize_tasks: bool`.
- `app/api/routers/me.py::patch_me` — конвертация bool↔string на wire-границе
  (mini-app шлёт `true`/`false`, бот хранит как bool).
- `webapp/src/types.ts` — `concretize_tasks: boolean` в `UserSettings` и
  `concretize_tasks?: boolean` в `UserSettingsUpdate`.
- `webapp/src/components/SettingsPage.tsx` — `SettingsSelectRow` с
  иконкой `ListChecks`, лейблом «Первый шаг», конверсия bool↔«on»/«off»
  на onChange.

**Тесты**
- `tests/test_courier.py` — переписан под новый contract `courier_respond`,
  добавлены:
  - `test_templates_no_emoji_parade` — ≤1 эмодзи на фразу.
  - `test_templates_no_dry_acks` — `Принял.`/`Записал.` запрещены.
  - `test_build_summary_keyboard_*` — структура клавиатуры, callback_data
    `summary:toggle:<kind>:<id>`, префиксы ☐/✅/📄, обрезка длинных
    тайтлов.
  - `test_flip_item_*` — для tasks toggle меняет статус, для notes нет.
- `tests/test_e2e_pipeline.py` — все e2e-тесты обновлены под tuple-возврат:
  утверждения теперь смотрят в `keyboard.inline_keyboard[i][0].text`, а
  не в текст. Добавлен helper `_kb_labels(kb)`.

**Что осталось пользователю**
- Семантика тапа на 📄-заметку в карточке распознанного — пока no-op +
  toast «Заметка». Полное удаление/архив остаются на mini-app и голосовые
  команды («удали заметку про X»). Юзер подтвердил такое поведение в чате.

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
