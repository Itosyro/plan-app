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


# ── Stage 2: Python runtime ─────────────────────────────────────────
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS base # 3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv (fast python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

# install deps first for better caching
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir -r <(uv pip compile pyproject.toml)

# app code
COPY . .

# Mini-App static bundle from the frontend stage. ``app/main.py``
# mounts ``webapp/dist`` at ``/app`` only when the directory exists,
# so this also works in dev when the build step is skipped.
COPY --from=frontend /webapp/dist /app/webapp/dist

# non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
