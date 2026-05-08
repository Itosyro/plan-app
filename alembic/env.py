"""Alembic environment.

Wires Alembic up to:
- the project's SQLModel metadata (so ``--autogenerate`` works), and
- ``DATABASE_URL`` from ``app.shared.config.Settings`` (with the value in
  ``alembic.ini`` acting as a fallback for ad-hoc commands).

Online mode uses a sync engine: Alembic's migration runner is synchronous
and we don't want to spin up an event loop just to run DDL. The async
driver scheme (``+asyncpg``) is normalised to ``+psycopg`` here.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Importing models registers them on ``SQLModel.metadata``. Don't remove.
import app.db.models  # noqa: F401
from alembic import context
from app.shared.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    """Pick a connection URL: env-driven Settings first, fall back to ini.

    Alembic's migration runner is sync, so async drivers are normalised to
    sync ones (``+asyncpg`` -> ``+psycopg``, ``+aiosqlite`` -> default).
    Bare ``postgresql://`` URLs (typical for Neon copy-paste) are pinned to
    ``postgresql+psycopg://`` so SQLAlchemy doesn't try to import psycopg2.
    """
    settings = get_settings()
    url = settings.database_url or config.get_main_option("sqlalchemy.url") or ""
    url = url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        # Some providers (Heroku-style) hand out ``postgres://`` — rewrite.
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations without an active DB connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
