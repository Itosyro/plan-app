"""Add ``inbox_entries.needs_review`` for the «Входящие» review tab.

The pipeline now persists tasks immediately (вариант Б) and, when a
message produced ≥2 tasks or a low-confidence result, flags the source
inbox entry with ``needs_review = True``. The Mini-App «Входящие» tab
lists flagged entries with their extracted tasks so the user can confirm
or drop them; confirming clears the flag.

The column is NOT NULL with a server-side default of ``false`` so
existing rows need no backfill — nothing pre-feature was ever flagged.
Indexed because the pending-list endpoint filters on it.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_entries",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_inbox_entries_needs_review",
        "inbox_entries",
        ["needs_review"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbox_entries_needs_review", table_name="inbox_entries")
    op.drop_column("inbox_entries", "needs_review")
