# syntax=docker/dockerfile:1.7

# ── Stage 1: build the Mini-App static bundle ───────────────────────
# We pin Node 20 LTS which matches Vite 5's supported runtime.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend # 20-alpine

WORKDIR /webapp

# Install JS deps first so subsequent code edits don't bust the cache.
COPY webapp/package.json webapp/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY webapp/ ./
RUN npm run build


# ── Stage 2: build the Python virtualenv ────────────────────────────
# Compilers live HERE and never reach the runtime image. That matters:
# ``build-essential`` alone is ~350 MB, and the self-hosted target is a
# VPS with ~2 GB of free disk shared with other projects.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

# Resolve from the lock file so the image matches CI exactly. Only the
# runtime dependency group — no ruff/pytest/mypy in production.
COPY pyproject.toml uv.lock ./
RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv sync --frozen --no-dev --no-install-project


# ── Stage 3: runtime ────────────────────────────────────────────────
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

# ``curl`` stays for the compose healthcheck; ``ca-certificates`` for
# outbound TLS to Telegram and Groq. No compiler toolchain here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

# Mini-App static bundle from the frontend stage. ``app/main.py``
# mounts ``webapp/dist`` at ``/app`` only when the directory exists,
# so this also works in dev when the build step is skipped.
COPY --from=frontend /webapp/dist /app/webapp/dist

# non-root user. ``/app/data`` is where the self-hosted SQLite file
# lives (bind-mounted by compose) — it must be writable by that user.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
