---
name: deploy-check
description: Verify a plan-app production deploy on Render — confirm the merge reached prod, the right Groq models are live, and the bot pipeline isn't silently broken. Use after merging to main, when the user says "the bot is erroring / not working", or to confirm a model/config change actually deployed.
---

# Check the plan-app production deploy

Production runs on Render free tier at **https://plan-app-t6nx.onrender.com**
(bot **@daylirobot**). A merge to `main` triggers an auto-deploy (~2 min).

## 1. Hit /healthz

Ask the user to open (or fetch if the sandbox allows — it's often blocked by
the host allowlist, so the user pasting it is the reliable path):

```
https://plan-app-t6nx.onrender.com/healthz
```

Expected JSON (the diagnostics endpoint added for exactly this):

```json
{
  "status": "ok",
  "env": "production",
  "groq_keys_configured": 3,
  "sentry_enabled": false,
  "models": {
    "whisper": "whisper-large-v3",
    "splitter": "...",
    "classifier": "llama-3.3-70b-versatile",
    "critic": "llama-3.3-70b-versatile"
  }
}
```

## 2. Interpret

- **`models.classifier` / `models.critic`** — must be a Llama model, NOT a
  `gpt-oss-*` or `qwen-qwq-*` reasoning model. Reasoning models break
  `instructor` structured output on Groq → every voice/text message errors.
  This was the 2026-06 prod outage. If you see gpt-oss here, the deploy
  is running stale code OR a `GROQ_MODEL_*` env var on Render is overriding
  the default — check the Render dashboard Environment tab.
- **Page won't load / 502 / 503** — Render service is asleep (free tier spins
  down) or the deploy failed. Check Render dashboard → Events/Deploys. A
  failed `pip install` (e.g. after adding a dependency) leaves the old version
  running.
- **`groq_keys_configured: 0`** — `GROQ_API_KEYS` env var is missing → bot
  replies "AI-разбор временно недоступен".

## 3. Known good model config

The registry (`app/ai/models.py`) ships these production-safe defaults:
- classifier / critic → `llama-3.3-70b-versatile`
- light stages (splitter/intent/courier/reorder/task_splitter) → `llama-3.1-8b-instant`
- whisper → `whisper-large-v3`

All are overridable via `GROQ_MODEL_<STAGE>` env vars without a redeploy.

## 4. If the bot still errors with the right models live

Ask the user for the EXACT error text the bot replied with — the message maps
to a specific failure stage (see `app/bot/routers/_pipeline.py` and
`text.py`/`voice.py` error branches). Without Sentry (set `SENTRY_DSN` to
enable), the error text is the main diagnostic signal.
