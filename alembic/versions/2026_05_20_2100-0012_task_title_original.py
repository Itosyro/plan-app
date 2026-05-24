"""Add ``tasks.title_original`` for the FirstStep rewrite feature.

When the classifier emits a non-null ``first_step`` and the user has
``UserSettings.concretize_tasks`` enabled, ``persist_classification``
now swaps:

    Task.title           = classifier.first_step   (actionable)
    Task.title_original  = classifier.title        (original phrasing)

The Mini-App / bot render the actionable title prominently and the
original as a small subtitle next to a 🎯 badge so the user still
sees what they actually said.

The column is nullable so legacy rows (pre-feature) and tasks that
weren't rewritten (concretize off, or classifier didn't propose a
step) require no backfill.
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("title_original", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "title_original")
