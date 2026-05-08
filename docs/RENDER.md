# Render deployment notes

The whole bot runs as **a single FastAPI web service** on Render. There is
no standalone cron worker because Render's free plan does not include them
(Cron Jobs require Starter+). Instead, an `asyncio` task inside the web
process ticks reminders and digests on a fixed interval — see
`app/workers/runner.py`.

## Free-tier topology

```
┌───────────────────────┐        webhook            ┌────────────┐
│ Render free web dyno  │  ◄───────────────────────►│  Telegram  │
│  · FastAPI (uvicorn)  │                           └────────────┘
│  · /tg/<secret>       │
│  · /healthz           │
│  · in-process loop ───┼── tick_reminders, tick_digests every 60s
└───────▲───────────────┘
        │ keep-alive ping every 5–10 min
        │
┌───────┴───────────────┐
│ External cron pinger  │  (cron-job.org or GitHub Actions cron)
└───────────────────────┘
```

The dyno spins down after **15 min of inactivity** on free tier. To stop
that from happening — and therefore to stop the in-process scheduler from
also going to sleep — fire a periodic `GET /healthz` from outside Render.

## Recommended pinger options

### Option 1 — cron-job.org (simplest)
1. Sign up at <https://cron-job.org> (free).
2. Create a new cronjob:
   - URL: `https://<your-render-url>/healthz`
   - Schedule: every 10 minutes
   - HTTP method: `GET`
3. Save and activate.

### Option 2 — GitHub Actions cron
Add `.github/workflows/keepalive.yml`:

```yaml
name: keepalive
on:
  schedule:
    - cron: "*/10 * * * *"   # GitHub-cron minimum is 5 minutes
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -fsS https://<your-render-url>/healthz
```

GitHub Actions cron is best-effort (can drift by a few minutes) but it's
free and good enough as a keep-alive.

## Tick interval and SLO

- Default interval: 60s (`SCHEDULER_TICK_INTERVAL_SECONDS=60`).
- Digest matching is **strict** on local `HH:MM`, so a longer interval
  (e.g. 120s) would risk skipping a slot. Don't push it past 60s.
- Reminder delivery has slack — `fire_at` is a lower bound. A late tick
  just sends a slightly delayed reminder; nothing is dropped.

## Upgrading to a real cron service later

When you outgrow the free tier:

1. Set `SCHEDULER_INPROC_ENABLED=false` on the web service (avoid double
   ticks).
2. Add a `cron` service block to `render.yaml` running
   `uv run python -m app.workers.scheduler` on `*/1 * * * *`.
3. Re-deploy. The web service still serves the webhook; the cron service
   handles ticks once per minute exactly.
