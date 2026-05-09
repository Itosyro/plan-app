"""Add user_settings.last_{morning,evening}_digest_on idempotency guards

Adds two ``date NULL`` columns to ``user_settings`` so the digest
scheduler can skip already-delivered digests. Stored value is the
**user-local** date on which the digest was last sent — comparing
``last_*_digest_on == ``today_local`` before sending eliminates
double-fire on sub-minute scheduler ticks.

See ``docs/REVIEW-2026-05-09.md::C-3``.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-09 07:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two ``date NULL`` digest-idempotency columns."""
    op.add_column(
        "user_settings",
        sa.Column("last_morning_digest_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("last_evening_digest_on", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Drop the digest-idempotency columns."""
    op.drop_column("user_settings", "last_evening_digest_on")
    op.drop_column("user_settings", "last_morning_digest_on")
