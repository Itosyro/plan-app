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
    "splitter": "openai/gpt-oss-20b",
    "classifier": "openai/gpt-oss-120b",
    "critic": "openai/gpt-oss-120b"
  }
}
```

## 2. Interpret

- **`models.classifier` / `models.critic`** — must be `openai/gpt-oss-120b`
  (since 2026-07-26, PR #187). История, чтобы не откатить по ошибке:
  - Май 2026: gpt-oss ломал ВСЕ вызовы — но причиной был
    `instructor.Mode.JSON` (reasoning-токены вокруг ответа), а не сами
    модели. Тогда откатились на Llama (#171).
  - Июль 2026: все instructor-колсайты переведены на `Mode.TOOLS`
    (схема как tool, ответ из `tool_calls[0].function.arguments`) —
    gpt-oss работает. **Llama-модели (`llama-3.1-8b-instant`,
    `llama-3.3-70b-versatile`) депрекированы Groq и отключаются в
    августе 2026 — возвращаться на них НЕЛЬЗЯ.**
  - Если здесь видна llama или qwen — на Render торчит устаревший
    `GROQ_MODEL_*` env-override (Environment tab) или крутится старый код.
- **Page won't load / 502 / 503** — Render service is asleep (free tier spins
  down) or the deploy failed. Check Render dashboard → Events/Deploys. A
  failed `pip install` (e.g. after adding a dependency) leaves the old version
  running.
- **`groq_keys_configured: 0`** — `GROQ_API_KEYS` env var is missing → bot
  replies "AI-разбор временно недоступен".

## 3. Known good model config

The registry (`app/ai/models.py`) ships these production-safe defaults:
- classifier / critic → `openai/gpt-oss-120b`
- light stages (splitter/intent/courier/reorder/task_splitter) → `openai/gpt-oss-20b`
- whisper → `whisper-large-v3`

All are overridable via `GROQ_MODEL_<STAGE>` env vars without a redeploy —
это аварийный рычаг, но после августа 2026 валидных llama-значений
больше нет: чинить надо код/промпты, а не откатывать модель.

## 4. End-to-end smoke (the real test)

Structured output через Mode.TOOLS проверяется только живым вызовом:
попроси Юсуфа отправить боту голосовое или текст («купи молоко завтра
в 10») и убедиться, что пришла карточка задачи, а не «Ошибка при
разборе». Это обязательный шаг после любой смены модели/режима
instructor.

## 5. If the bot still errors with the right models live

Ask the user for the EXACT error text the bot replied with — the message maps
to a specific failure stage (see `app/bot/routers/_pipeline.py` and
`text.py`/`voice.py` error branches). Without Sentry (set `SENTRY_DSN` to
enable), the error text is the main diagnostic signal.
