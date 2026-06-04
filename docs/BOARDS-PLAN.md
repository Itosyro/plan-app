# Доски (Excalidraw canvas) — план фичи

> Отдельный документ под новую большую фичу. Прогресс ведём в
> `docs/BOARDS-PROGRESS.md`. Основной лог проекта — `docs/PROGRESS.md`.

## Контекст и решения пользователя

Пользователь хочет интерактивную **карту памяти / полотно** (как Excalidraw):
писать блоки, рисовать стрелочки, связывать заметки визуально, от руки. Удобно
с телефона и десктопа через Telegram Mini-App.

Решения (из голосового брифа + уточняющих вопросов):
- **Размещение:** отдельный полноэкранный раздел (НЕ шестая нижняя вкладка).
  Вход — из вкладки «Заметки» (иконка в шапке) + дублируем в Настройках.
- **Структура:** несколько **именованных досок** (как файлы Excalidraw) — список
  досок, открываешь любую, создаёшь новые.
- **Вкладка «Входящие» оставляем** как есть.
- **MVP:** настоящая библиотека `@excalidraw/excalidraw`, **lazy-load** (грузится
  отдельным чанком только при открытии доски, не тормозит запуск приложения).

## Технический ресёрч (подтверждён агентом, июнь 2026)

- `@excalidraw/excalidraw` **v0.18.1**, MIT, React 18 совместим. Чанк ~900KB-1.1MB
  gzip → **обязательно** lazy. tldraw отпадает: лицензия 4.0 требует $6k/год или
  ставит водяной знак — дилбрейкер.
- **Vite-дельта:** `define: { "process.env.IS_PREACT": '"false"' }` (иначе
  `process is not defined`), `optimizeDeps.include` + `esbuildOptions.target:
  "es2022"`, `build.target: "es2022"`. `moduleResolution: "bundler"` уже есть.
  tsconfig `target` поднять ES2020 → ES2022.
- **Шрифты:** на мобильном Telegram WebView CDN `esm.run` может тормозить —
  self-host через `EXCALIDRAW_ASSET_PATH` + копирование fonts в `public/` на
  postinstall. Фолбэк-массив `["/", "https://esm.run/..."]`.
- **Персист:** `serializeAsJSON(elements, appState, files, "database")` → JSON
  (2-30KB обычно), `restore(raw, null, null)` перед `initialData`. Хранить JSONB.
- **Telegram-гочи:** высота контейнера = `Telegram.WebApp.viewportStableHeight`
  (НЕ `100dvh`); `<meta viewport ... user-scalable=no>` (иначе iOS перехватит
  pinch); `autoFocus={false}`; `getFormFactor: () => "phone"`; паддинг
  `env(safe-area-inset-bottom)` от Android-навбара; debounce save 1.5s.
- **Тема:** проп `theme="dark"|"light"` от `Telegram.WebApp.colorScheme`, слушать
  `themeChanged`.

## Архитектура

### Backend (FastAPI + SQLModel + Alembic)

**Модель `Board`** (`app/db/models.py`) — следуем конвенциям проекта (int PK,
soft-delete через `deleted_at`, как у Task/Note):
```
id: int PK
user_id: int FK -> users.id (index)
name: str (default "Без названия", max 128)
scene_json: dict | None  (JSON column; Excalidraw scene)
created_at, updated_at: datetime
deleted_at: datetime | None  (soft delete)
```
Alembic-миграция `00NN_add_boards.py`.

**API-роутер `/api/boards`** (`app/api/routers/boards.py`):
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/boards` | список досок юзера (id, name, updated_at — БЕЗ scene_json, лёгкий) |
| POST | `/boards` | создать пустую доску `{name?}` → BoardDetailOut |
| GET | `/boards/{id}` | полная доска со scene_json |
| PATCH | `/boards/{id}` | обновить name и/или scene_json (debounced save) |
| DELETE | `/boards/{id}` | soft-delete |

**Схемы** (`app/api/schemas.py`): `BoardOut` (лёгкий список), `BoardDetailOut`
(+scene_json), `BoardCreateIn` (name?), `BoardUpdateIn` (name?, scene_json?).
Валидация: name 1..128, scene_json — dict, ограничить размер (напр. ≤ 5 МБ
сериализованного, защита от abuse).

**Тесты** (`tests/test_boards_api.py`): CRUD, user-scoping (чужую доску не
видно/не патчишь — 404), soft-delete скрывает из списка, размер-лимит → 413/422.

### Frontend (React + Vite, lazy Excalidraw)

**Роутинг** (хеш-роутер `lib/router.ts`):
- `/boards` — список досок (полноэкранный оверлей).
- `/board/:id` — холст конкретной доски (полноэкранный).
Оба — как существующие `/task/:id` оверлеи (поверх таб-стека).

**Компоненты:**
- `components/BoardsList.tsx` — сетка/список досок: имя + «изменено N назад»,
  кнопка «+ Новая доска», свайп/долгое нажатие → удалить. Через
  `useCachedResource("boards", ...)`.
- `components/BoardCanvas.tsx` — обёртка: грузит доску (GET), рендерит
  `<ExcalidrawLazy>`, debounced-save (PATCH) по `onChange`, тема от Telegram,
  phone-friendly `UIOptions`, высота от `viewportStableHeight`. Шапка с «назад»
  + редактируемое имя.
- `components/ExcalidrawLazy.tsx` — **единственный** файл, импортящий
  `@excalidraw/excalidraw` + `index.css`. `React.lazy(() => import(...))`.
- `api/client.ts` — `boards()`, `board(id)`, `createBoard()`, `patchBoard()`,
  `deleteBoard()`.
- `types.ts` — `Board`, `BoardDetail`.

**Вход в фичу:** иконка-доска (lucide `PenTool` / `Network`) в шапке вкладки
«Заметки» → `navigate("/boards")`. Плюс строка в Настройках → Данные.

**Vite/tsconfig/index.html:** дельты из ресёрча. Шрифты self-host через
postinstall-скрипт + `EXCALIDRAW_ASSET_PATH`.

## Слайсы (каждый — отдельный PR, гейты зелёные)

1. **Boards backend** — модель + миграция + CRUD API + схемы + тесты. Изолирован,
   не трогает фронт. Мержим первым.
2. **Excalidraw shell** — Vite/tsconfig/index.html дельты + `ExcalidrawLazy` +
   пустой `BoardCanvas`, проверить что чанк сплитится и не растит main bundle.
3. **Boards UI** — `BoardsList` + роутинг + вход из Заметок + apiClient + типы +
   save/load flow. Связываем со слайсом 1.
4. **Полировка** — debounced save + save-on-blur, тема, phone UIOptions,
   viewportStableHeight, safe-area, удаление с подтверждением.

Слайс 1 (бэк) можно делать агентом параллельно слайсу 2 (фронт-shell).

## Верификация
- Бэк: ruff/mypy/pytest (+ новые тесты досок), миграция применяется чисто.
- Фронт: tsc + build; **главное** — main chunk НЕ растёт (Excalidraw в отдельном
  чанке), новый `board`-чанк появляется. Проверить размер до/после.
- E2E: создать доску, порисовать, перезагрузить — сцена восстановилась; тема
  следует Telegram; на узком экране тулбар phone-формата.

## Риски
- Bundle: митигируем lazy + отдельный чанк (verified pattern).
- Telegram WebView touch/keyboard/pinch — набор пропов из ресёрча, требует
  ручного QA на телефоне (как и любой WebView-UI).
- Размер scene_json в БД — лимит на запись + `"database"` сериализация (без
  inline-картинок). Картинки-файлы пока не поддерживаем в MVP (или режем).
</content>
