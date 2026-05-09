# Phase 5 — Test Report

PR: <https://github.com/Itosyro/plan-app/pull/64>
Session: <https://app.devin.ai/sessions/d7d03b55ac804f9485a0b593fe7c8a2f>
Run: 2026-05-09 — local uvicorn (FastAPI mounting `/app/` from built `webapp/dist`) + Playwright (headless chromium) + httpx + pytest.

## Summary

| # | Test | Result |
| - | ---- | ------ |
| 1 | Mini-App happy path: load → switch horizon → filter category → mark done → move | passed |
| 2 | Bad signature → 401 + auth-error UI text | passed |
| 3 | Cross-user isolation: 4242 cannot mutate 5555's task | passed |
| 4 | Streaming progressive reveal (≥2 edits, monotonic, final = full) | passed |

Plus regression: `pytest tests/test_streaming.py tests/test_api_auth.py tests/test_api_endpoints.py tests/test_static_miniapp.py` → 29 passed.

No escalations. No deviations from the plan. Only artefact: prod bot @daylirobot was **not** retested in Telegram client because Phase 5 (Mini-App + streaming) lives in this PR until merge — Phase 4 prod bot was already verified in earlier sessions.

---

## Case 1 — Mini-App happy path

**Setup.** Two seeded users (`tg=4242` "Тестер", `tg=5555` "Второй"). Five tasks across `today`/`tomorrow`/`week`. Playwright injects `window.Telegram.WebApp` with a signed `initData` for 4242 before any page JS runs, and blocks `https://telegram.org/**` so our shim wins over the CDN script.

### Network capture (case 1, in order)

```
200 GET  /api/me
200 GET  /api/horizons
200 GET  /api/categories
200 GET  /api/tasks?horizon=today
200 GET  /api/tasks?horizon=tomorrow
200 GET  /api/tasks?horizon=today
200 GET  /api/tasks?horizon=today&category_id=1
200 GET  /api/tasks?horizon=today
200 PATCH /api/tasks/1               ← mark "Купить молоко" done
200 PATCH /api/tasks/2               ← move "Написать отчёт" → week
200 GET  /api/tasks?horizon=week
```

### Screenshots

| 01 — initial load (Сегодня, 2 tasks) | 02 — switch to Завтра |
| --- | --- |
| ![01](https://app.devin.ai/attachments/f515273e-6a75-4162-95d4-f984afc63b60/01_happy_initial.png) | ![02](https://app.devin.ai/attachments/ec7f6a90-deee-4876-b1ac-3389a9483e7c/02_horizon_tomorrow.png) |
| Header "План", subtitle "Привет, Тестер 👋", chip counts `Дом 2 / Работа 2`, two task cards visible. | Network fired `GET /api/tasks?horizon=tomorrow`; only "Завтрашняя задача" appears. |

| 03 — filter by Работа | 04 — Купить молоко marked done |
| --- | --- |
| ![03](https://app.devin.ai/attachments/9260badd-f12b-4998-a632-623995269c6d/03_filter_rabota.png) | ![04](https://app.devin.ai/attachments/0f54c47a-fa3b-464a-939a-7b1d90944a7f/04_after_done.png) |
| `?category_id=1` issued, only "Написать отчёт" remains in list. | Optimistic update: "Купить молоко" disappears from "Сегодня" within 350 ms; PATCH returned 200. |

| 05 — move picker open | 06 — after move (today empty) |
| --- | --- |
| ![05](https://app.devin.ai/attachments/4bc6430a-6155-40ad-85fc-2806948833b8/05_move_picker.png) | ![06](https://app.devin.ai/attachments/29569805-53f2-40a5-aafb-9ce8a162e91a/06_after_move.png) |
| 6-button grid: Сегодня / Завтра / На неделе / В месяце / В году / Когда-нибудь. | After picking "На неделе": Написать отчёт vanishes from "Сегодня" (only Купить молоко was here, already done). |

| 07 — На этой неделе now contains the moved task |
| --- |
| ![07](https://app.devin.ai/attachments/0cbb93f6-e410-44d0-9d7f-e69af8c36d47/07_week_tab.png) |
| Both seeded "Задача на неделе" and the just-moved "Написать отчёт" are visible — proves the PATCH actually wrote `horizon_slug=week` server-side. |

### Verdict

Pass. Every assertion in the plan held: 200s on all four shell endpoints, horizon switch → `tomorrow` task, category filter → only `Работа` task, done → optimistic + 350 ms removal, move → task on new tab.

Page video (mp4): [happy-path video](https://app.devin.ai/attachments/92c5af49-a2a4-49c0-8df6-1cca9f880e33/page%40a3984cb8eb39bae784323ca2173e162c.mp4).

---

## Case 2 — Bad signature → 401 + auth-error UI

Reload the page with `initData` whose last `hash` byte is flipped.

### Network capture

```
401 GET /api/me
401 GET /api/horizons
401 GET /api/categories
401 GET /api/tasks?horizon=today
```

### Screenshot

| 08 — auth-error screen |
| --- |
| ![08](https://app.devin.ai/attachments/891542ce-f097-418d-9cb2-d3db6d96bd80/08_bad_signature.png) |
| Body text matched **exactly**: `🔒 Нужен вход — Не удалось проверить вход. Открой бот через @daylirobot и нажми «Открыть план» в меню.` (the literal in `webapp/src/App.tsx:36-38`). |

Page video (mp4): [bad-sig video](https://app.devin.ai/attachments/e35c8d07-a641-411e-af08-ef5909a09bbf/page%408126714b1cd9168394ba2a85762b7d4d.mp4).

### Verdict

Pass. HMAC validation rejected the tampered hash; UI rendered the correct error copy.

---

## Case 3 — Cross-user isolation

Direct httpx probe: user 4242 (signed initData) attempts to mutate task #5, owned by user 5555.

```
u5555 GET  /api/tasks?horizon=today      → 200 [{id:5,status:new,...}]
u4242 PATCH /api/tasks/5 {status:done}    → 404 {"detail":"task not found"}
u4242 DELETE /api/tasks/5                  → 404 {"detail":"task not found"}
u5555 GET  /api/tasks?horizon=today      → 200 [{id:5,status:new,...}]
```

### Verdict

Pass. Both PATCH and DELETE returned 404 (the owner-check in `_load_task_owned`). `status` of task 5 is still `new` for user 5555 — no leak.

---

## Case 4 — Streaming progression

```python
msg = _FakeMessage()
await stream_reply(msg, "first\nsecond\nthird\nfourth", chunk_delay=0.0)

# captured edits:
#  [0] 'first\nsecond'
#  [1] 'first\nsecond\nthird\nfourth'
```

≥2 edits, monotonic growth, final = full. Plus the existing 4-test pytest module passes (progressive reveal, single-line, RetryAfter recovery, empty).

### Verdict

Pass. `_MIN_GROW_BYTES` coalescing groups the first two short lines into a single edit (8-byte threshold), then a final edit emits the full text — exactly the rate-limit-friendly behaviour we want.

---

## How to reproduce

```bash
cd /home/ubuntu/repos/plan-app
rm -f /tmp/plan-app-test.db
PYTHONPATH=. uv run python /tmp/seed_phase5.py
set -a && . ./.env.test.local && set +a
PYTHONPATH=. uv run uvicorn app.main:app --host 127.0.0.1 --port 8765 &
sleep 3
PYTHONPATH=. uv run python /tmp/playwright_phase5.py        # cases 1+2
PYTHONPATH=. uv run python /tmp/case3_cross_user.py         # case 3
PYTHONPATH=. uv run python /tmp/case4_streaming.py          # case 4
```

(Test scripts live in `/tmp/` for now; if you want them committed I can move them to `tests/e2e/` in a follow-up.)
