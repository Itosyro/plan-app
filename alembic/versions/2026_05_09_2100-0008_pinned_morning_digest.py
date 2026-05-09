"""Add user_settings columns for pinned morning digest tracking

Phase 6.3 — the morning digest is now pinned in the user's chat with
the bot, and re-edited as tasks are marked done during the day.
We need to remember the (chat_id, message_id, date) of the currently
pinned message so we can:

- skip re-pinning a fresh digest before yesterday's pin is replaced
  (Telegram allows multiple pins but it gets visually noisy);
- edit it on done/move/delete events;
- silently stop trying once the user has manually unpinned.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-09 21:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add three nullable columns tracking the currently-pinned digest."""
    op.add_column(
        "user_settings",
        sa.Column("pinned_morning_chat_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("pinned_morning_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("pinned_morning_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Drop the pinned-morning columns."""
    op.drop_column("user_settings", "pinned_morning_date")
    op.drop_column("user_settings", "pinned_morning_message_id")
    op.drop_column("user_settings", "pinned_morning_chat_id")
