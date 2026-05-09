"""Add user_settings.morning_anchor / evening_anchor

Per-user HH:MM anchors for the time resolver's ``утром`` / ``вечером``
preprocessor. Before this migration these were hard-coded as ``09:00``
and ``19:00`` in ``app/ai/time_resolver.py``. Now each user can
customise them via ``/settings`` (future UI) while the defaults stay
the same.

See ``docs/REVIEW-2026-05-09.md::M-6``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-09 11:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add morning_anchor and evening_anchor columns with defaults."""
    op.add_column(
        "user_settings",
        sa.Column(
            "morning_anchor",
            sa.String(length=5),
            nullable=False,
            server_default="09:00",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "evening_anchor",
            sa.String(length=5),
            nullable=False,
            server_default="19:00",
        ),
    )


def downgrade() -> None:
    """Drop morning_anchor and evening_anchor columns."""
    op.drop_column("user_settings", "evening_anchor")
    op.drop_column("user_settings", "morning_anchor")
