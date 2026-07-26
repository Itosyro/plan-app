# Security Policy

## Reporting a vulnerability

If you find a security issue in PLAN (the @daylirobot Telegram bot / Mini-App),
please report it privately — **do not open a public issue**.

- Use GitHub's **Report a vulnerability** (Security → Advisories) on this repo, or
- Contact the maintainer directly via the email on their GitHub profile.

Please include: a description, steps to reproduce, affected component
(bot pipeline / API / Mini-App), and impact. We aim to acknowledge within a
few days and to ship a fix or mitigation as soon as practical.

## Scope

In scope: the bot message pipeline (`app/`), the Mini-App API (`/api/*`),
Telegram `initData` auth, and the web bundle (`webapp/`).

Out of scope: third-party platforms (Telegram, Render, Supabase, Groq) and issues
requiring a compromised maintainer account or device.

## Hardening already in place

- Telegram `initData` HMAC verification with a 12-hour TTL (replay window) —
  see `app/api/auth.py::INIT_DATA_MAX_AGE_SECONDS`. Raised from 10 minutes in
  PR #187: sessions open longer than the old window started failing with 401.
- Per-user rate limiting on the LLM pipeline (denial-of-wallet defence).
- Prompt-injection defence: untrusted user text is wrapped in XML-style
  delimiters + a "treat as data" preamble and JSON-escaped before every LLM
  stage; system prompts carry a Security section (never reveal the prompt,
  never let input override output fields).
- Parameterised ORM queries (no string-built SQL); Pydantic `extra="forbid"`
  on API bodies (anti mass-assignment).

See `docs/SECURITY_AUDIT_REPORT.md` for the full audit and the remediation
backlog (Workstream G in `docs/plans/2026-05-25-phase7e-polish.md`).
