# Render deployment notes

The whole bot runs as **a single FastAPI web service** on Render. There is
no standalone cron worker because Render's free plan does not include them
(Cron Jobs require Starter+). Instead, two `asyncio` tasks run inside the
web process:

1. **Scheduler loop** (`app/workers/runner.py`) — ticks reminders and
   daily digests on a fixed interval.
2. **Keep-alive self-ping** (`app/workers/keepalive.py`) — hits the
   public `/healthz` URL every 10 min so the free dyno never goes idle
   long enough to spin down. Mirrors `voice-bot`'s `_self_ping`.

## Free-tier topology

```
┌───────────────────────┐        webhook            ┌────────────┐
│ Render free web dyno  │  ◄───────────────────────►│  Telegram  │
│  · FastAPI (uvicorn)  │                           └────────────┘
│  · /tg/<secret>       │
│  · /healthz           │◄────┐
│  · scheduler loop ────┼─── tick_reminders + tick_digests every 60s
│  · keep-alive loop ───┼─────┘ self-GET on public URL every 10 min
└───────────────────────┘
```

The dyno spins down after **15 min of inactivity** on free tier. The
keep-alive task issues a `GET` against the **public** `WEBHOOK_BASE_URL +
/healthz` every 10 min — the request leaves the dyno over the internet
and comes back as a regular external HTTP hit, which Render counts as
activity and resets the idle timer. No external pinger is required.

## Configuration

| Env var | Default | Notes |
|---|---|---|
| `KEEPALIVE_ENABLED` | `true` | Master switch. Set to `false` on Starter+ once a real cron service is added. |
| `KEEPALIVE_INTERVAL_SECONDS` | `600` | Cadence between pings. Must be < 900 s (Render's 15-min idle window). |
| `KEEPALIVE_INITIAL_DELAY_SECONDS` | `60` | Skip the first 60 s after boot so startup has time to settle. |
| `KEEPALIVE_TIMEOUT_SECONDS` | `10` | Per-request timeout. A slow ping is logged and skipped — the next tick retries. |

The self-ping is automatically disabled when `WEBHOOK_BASE_URL` is unset
(local dev, tests).

## External pinger (no longer required, but compatible)

If you want belt-and-braces, an external pinger still works — the
`/healthz` endpoint is idempotent and the in-process loop happily
coexists. Either of these is fine:

### cron-job.org
1. Sign up at <https://cron-job.org> (free).
2. Create a new cronjob:
   - URL: `https://<your-render-url>/healthz`
   - Schedule: every 10 minutes
   - HTTP method: `GET`
3. Save and activate.

### GitHub Actions cron
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
free.

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
2. Set `KEEPALIVE_ENABLED=false` — paid plans don't idle out, so the
   self-ping is just wasted bandwidth.
3. Add a `cron` service block to `render.yaml` running
   `uv run python -m app.workers.scheduler` on `*/1 * * * *`.
4. Re-deploy. The web service still serves the webhook; the cron service
   handles ticks once per minute exactly.
