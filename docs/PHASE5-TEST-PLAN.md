# Phase 5 — Mini-App + Streaming Reply Test Plan

PR: <https://github.com/Itosyro/plan-app/pull/64>

## What changed (user-visible)

1. Bot now exposes a **Telegram Mini-App** at `/app/` (Todoist-style mobile UI):
   sticky horizon pill-tabs → category chips → task cards with checkbox /
   Перенести / Удалить.
2. Backend has new **`/api/*`** endpoints (`me`, `horizons`, `categories`,
   `tasks`, `notes`, `inbox`) that authenticate via Telegram `initData`
   (HMAC-SHA256 signature, 24 h TTL).
3. Bot replies are now **streamed line-by-line** via `editMessageText` instead
   of being printed in one shot.

## Code-path evidence

- `app/main.py:175-190` — mounts `/api/*` routers + `StaticFiles("/app", webapp/dist, html=True)` only when `WEBAPP_DIST` exists.
- `app/api/auth.py:50-65` — HMAC-SHA256(`WebAppData`, bot_token) over sorted `key=value\n…` pairs.
- `app/api/auth.py:95-98` — auth_date TTL: rejects `now - auth_date > 24h` and `auth_date > now + 60s`.
- `app/api/routers/tasks.py:62-116` — `GET /api/tasks?horizon=...&category_id=...` with allow-list; LEFT OUTER JOIN to horizons/categories so NULL FK still appears.
- `app/api/routers/tasks.py:119-128` — `_load_task_owned` 404s if task isn't owned by `user.id` (cross-user isolation).
- `webapp/src/App.tsx:22-48` — first load fires `Promise.all([me, horizons, categories])`; on 401 shows "Не удалось проверить вход", on 404 "Сначала пройди /start", else "Ошибка соединения".
- `webapp/src/api/client.ts:40-57` — every API call adds header `X-Telegram-Init-Data: <window.Telegram.WebApp.initData>`.
- `app/bot/streaming.py:71-118` — `_edit(text)` only edits when text changed; coalesces sub-`_MIN_GROW_BYTES=8` growths; sleeps `min(retry_after, 5)` on `TelegramRetryAfter`.

## What I will test

**Single primary end-to-end flow:** open the Mini-App in a real browser with a
signed `initData`, walk through happy path (load → switch horizon → mark done →
move to "Завтра"), then flip ONE input to a broken state and confirm the
boundary fires (bad signature → 401 + "Не удалось проверить вход").

Plus three targeted adversarial probes for things the UI flow alone can't
prove (signature TTL, cross-user isolation, streaming progression).

I will NOT:
- Re-prove unit-tested behaviour that already passed in CI (the 29 new tests).
- Run "all 272 tests" again — that's regression noise.
- Test through the Telegram client itself — production prod-side has bot @daylirobot from Phase 4 already; Phase 5 lives in the PR until merge.

## Environment

| | |
|---|---|
| Backend | `uv run uvicorn app.main:app` on `:8000` with `.env.test` (SQLite + fake bot token matching tests' `_BOT_TOKEN`) |
| Frontend | Built bundle from `webapp/dist/`, mounted at `/app/` by FastAPI |
| Browser | Playwright (chromium, headless) via `webapp-testing` skill |
| `initData` injection | `page.add_init_script` overrides `window.Telegram.WebApp` with a pre-signed payload before any app JS runs |
| Seed data | A Python script seeds two users (`tg_id=4242`, `tg_id=5555`), categories, horizons, tasks before Playwright starts |

## Test cases

Exactly one primary flow + three targeted probes. Each step has a concrete
pass/fail expectation that would visibly differ if the change were broken.

### 1. Primary E2E: Mini-App happy path

Run a Playwright script that:

1. **Load** `http://localhost:8000/app/` with injected `initData` for user 4242.
   - **Pass:** screenshot shows page title "План", subtitle "Привет, Тестер 👋" (from `Header.tsx`), and at least one task card with title "Купить молоко" (seeded).
   - **Fail signal if broken:** "Не удалось проверить вход" / "Загружаем…" / blank screen / no task cards.

2. **Verify network** — check Playwright captures show `GET /api/me`, `GET /api/horizons`, `GET /api/categories`, `GET /api/tasks?horizon=today` all return `200`.
   - **Pass:** all four 200.
   - **Fail signal:** any 401/500.

3. **Switch horizon** — click button with text `Завтра`.
   - **Pass:** `GET /api/tasks?horizon=tomorrow` fires (200), and the seeded "Завтрашняя задача" appears, today's "Купить молоко" disappears.
   - **Fail signal if broken:** same task list as before, or 422.

4. **Filter by category** — click chip `Работа`.
   - **Pass:** request fires with `category_id=<id>`, list updates to show only "Работа" tasks. Counter on chip > 0.
   - **Fail signal if broken:** chip stays inactive, list unchanged.

5. **Mark done** — switch back to `Сегодня`, click circular checkbox of "Купить молоко".
   - **Pass:** card opacity drops to 50% with strike-through `text-tg-hint line-through` (visual), then 350ms later the card disappears from list. `PATCH /api/tasks/<id>` returns 200 with `"status":"done"`.
   - **Fail signal if broken:** card stays solid; PATCH 4xx; list still contains item after 1 s.

6. **Move task** — on a different task, click "🔄 Перенести" → click "На неделе".
   - **Pass:** task disappears from "Сегодня". Switch to "На неделе" tab — task appears there. `PATCH /api/tasks/<id>` body contained `{"horizon_slug":"week"}`.
   - **Fail signal if broken:** task stays on "Сегодня", or appears on wrong tab.

### 2. Adversarial: bad signature → 401 + auth-error UI

Reload the page with `initData` whose `hash` field has been tampered (replace last char with `0`).

- **Pass:** UI renders the auth-error screen with text exactly: `"Не удалось проверить вход. Открой бот через @daylirobot и нажми «Открыть план» в меню."` (from `App.tsx:36-38`). Network tab shows `GET /api/me` → 401.
- **Fail signal if broken:** UI loads fully (broken validation) or shows generic spinner forever.

### 3. Adversarial: cross-user isolation

Using user-4242's signed initData, fire `PATCH /api/tasks/<task_id_owned_by_user_5555>` with `{"status":"done"}` (we know the IDs because we seeded both).

- **Pass:** response is `404 task not found`. The seed task in user 5555's DB row is still `status="new"` (verified via direct DB query after).
- **Fail signal if broken:** 200 / 204 (data leak) or seed task flips to `done`.

### 4. Adversarial: streaming progression

Run `pytest tests/test_streaming.py -v` and observe assertion that `msg.calls`
ends with the full text and contains at least one strict prefix in between
(progressive reveal).

In addition, run a quick repl-style probe:
```python
msg = _FakeMessage()
await stream_reply(msg, "first\nsecond\nthird\nfourth", chunk_delay=0)
assert len(msg.calls) >= 2 and msg.calls[-1] == "first\nsecond\nthird\nfourth"
```

- **Pass:** at least 2 distinct edits captured, final call equals full text.
- **Fail signal if broken:** only 1 call (no progression), or final call ≠ full text.

This is the only non-UI test because the streaming behaviour can't be observed
in the local browser (no Telegram client). Production verification of the
visible animation will happen post-merge in Telegram.

## Recording

I will record the primary E2E flow (case 1) and the bad-signature adversarial
(case 2) in a single short Playwright trace + screenshots. Cases 3 and 4 are
shell-only with their outputs captured as text in the report.

## Pass/fail summary format

After execution I will post one comment on PR #64 with:

```
| # | Test | Result |
| - | ---- | ------ |
| 1 | Mini-App happy path (load + switch + filter + done + move) | ✅ / ❌ |
| 2 | Bad signature → 401 + auth-error text | ✅ / ❌ |
| 3 | Cross-user isolation → 404 + DB unchanged | ✅ / ❌ |
| 4 | Streaming progression (≥2 edits, final = full) | ✅ / ❌ |
```

with screenshots inline (before/after for each UI step) and shell output for
3 + 4. Plus a separate `docs/PHASE5-TEST-REPORT.md` attached.
