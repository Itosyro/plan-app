"""Programmatic Alembic runner used by the self-hosted startup path.

On the managed deploy migrations run as a separate release command. When
someone self-hosts on their own VPS there is no release step — the whole
promise is «docker compose up and it works» — so the app brings its own
schema up to date on boot when ``AUTO_MIGRATE=true``.

This is deliberately the same code path as the CLI (``alembic upgrade
head`` reads the very same ``alembic.ini`` + ``alembic/env.py``), so a
self-hosted database can never drift into a shape the managed one has
never seen.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from app.shared.logging import get_logger

logger = get_logger(__name__)

# ``alembic.ini`` sits at the repository root, two levels above this file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_migrations(database_url: str) -> None:
    """Upgrade the database at *database_url* to ``head``.

    Synchronous by nature (Alembic's runner is sync) — callers inside an
    event loop must hand this to an executor.

    Caveat worth knowing before you rely on the argument: ``env.py``
    resolves the URL as ``Settings.database_url or <ini value>``, so
    whenever ``DATABASE_URL`` is set in the environment (always, in the
    container) *it* wins and this parameter is only documentation. Both
    are the same value in every current caller.
    """
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    logger.info("db.migrate.done")
