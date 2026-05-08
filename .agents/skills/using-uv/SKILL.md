---
name: using-uv
description: Use when running, installing, or upgrading anything in plan-app. uv is the only supported way — no pip, poetry, or venv hand-rolling.
---

# Using uv in plan-app

plan-app uses [uv](https://github.com/astral-sh/uv) (Astral) as the single source of truth for Python version, virtualenv, dependencies, and lockfile. CI, Docker, and Render all assume uv.

---

## 1. Cheat sheet

```bash
# Install all deps from uv.lock (read-only, fast)
uv sync --frozen

# Install + lock (when you change pyproject.toml)
uv sync

# Add a new runtime dep
uv add httpx

# Add a dev-only dep
uv add --dev pytest-cov

# Bump a dep
uv lock --upgrade-package httpx

# Run anything inside the venv
uv run pytest -q
uv run ruff check .
uv run python -m app.workers.scheduler
```

Never activate the venv manually with `source .venv/bin/activate` — `uv run …` does it for every command and stays in sync with the lockfile.

---

## 2. uv.lock — commit it

`uv.lock` **must** be committed. CI uses `uv sync --frozen` and refuses to install if the lockfile is out of date.

If you add a dep, the lockfile changes — stage it explicitly:

```bash
uv add httpx
git add pyproject.toml uv.lock
```

---

## 3. Python version

Pinned to `3.12` via `requires-python = ">=3.12"` in `pyproject.toml` and the `python-version` field in `uv.lock`. uv will download a matching interpreter automatically — you don't need pyenv / asdf.

If you see `error: No interpreter found` on Render, the build image doesn't have Python 3.12. Fix in Dockerfile (`FROM python:3.12-slim`) or in `render.yaml` env.

---

## 4. Production install (Docker / Render)

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev    # skip pytest etc. in prod image
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`--no-dev` cuts ~80 MB. `--frozen` rejects any drift from `uv.lock`.

---

## 5. Common errors

| Error | Cause | Fix |
|---|---|---|
| `error: lockfile out of date` in CI | edited `pyproject.toml` without re-running `uv lock` | `uv sync && git add uv.lock` |
| `module not found: groq` in `uv run` | dep missing from lockfile | `uv add groq` (or `uv sync` if it's already in pyproject) |
| `no such file: .venv/bin/python` | venv was wiped | `uv sync` recreates it |
| `uv: command not found` | uv not installed | `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `OSError: cannot find python 3.12` on Render | base image too old | bump Dockerfile base |

---

## 6. ruff under uv

ruff config lives in `ruff.toml` at repo root. Run it via:

```bash
uv run ruff format .
uv run ruff check .
uv run ruff check . --fix      # auto-fix where safe
```

Both must be clean before push. CI runs the same.

---

## 7. Don'ts

- ❌ `pip install ...` — bypasses uv, breaks the lockfile.
- ❌ `python -m venv .venv` — uv manages the venv.
- ❌ Editing `uv.lock` by hand — generate it via `uv add` / `uv lock`.
- ❌ Different Python on dev vs CI vs Render — pin one and stick to it.

---

## Source

uv official docs: https://docs.astral.sh/uv/
