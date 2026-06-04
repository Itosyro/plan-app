---
name: gates
description: Run all CI gates for plan-app (backend ruff + mypy + pytest, and webapp tsc + build) exactly as the GitHub Actions workflow does. Use before committing, before opening a PR, or when the user asks to "run the gates / checks / tests" or verify the build is green.
allowed-tools: Bash
---

# Run all plan-app gates

This project's CI (`.github/workflows`) runs three jobs: **ruff + pytest**,
**webapp build**, and a dependency audit. Reproduce the blocking ones locally
before pushing so red CI never surprises us.

## Backend (Python, from repo root)

Run these in order and report the result of each:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```

- `ruff format --check` fails if anything is unformatted — fix with
  `uv run ruff format .` then re-run.
- `mypy` is scoped to `app` (tests are checked opportunistically, a few
  legacy generator-fixture warnings are known/accepted).
- `pytest` must end with `N passed` and zero failures.

## Frontend (Mini-App)

```bash
cd webapp && npm run typecheck && npm run build
```

- `typecheck` = `tsc --noEmit` (strict).
- `build` = Vite production build. After a build, sanity-check the printed
  chunk sizes: the main `index-*.js` chunk should stay ~20-22 KB gzip; heavy
  deps (`@dnd-kit`, `@excalidraw`) must be in their own lazy chunks, not the
  entry chunk.

## Reporting

State pass/fail per gate. If anything fails, show the relevant output and
either fix it (formatting, simple type errors) or summarise what's broken.
Never report "all green" unless every command above exited 0.
