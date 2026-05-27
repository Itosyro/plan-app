"""Add ``tasks.completed_at`` for the "Выполненные" screen.

Phase 7e/C: a task gets a ``completed_at`` timestamp when marked done
(cleared on reopen). Drives the dedicated "Выполненные" list and the
Mini-App linger-strikethrough window. Nullable, no backfill — legacy
done rows keep ``NULL`` until re-completed. Indexed for
``ORDER BY completed_at DESC``.

SQLite needs ``batch_alter_table`` to add an indexed column safely; it's
a no-op wrapper on Postgres. The CI matrix includes SQLite, so we use it
unconditionally (mirrors migration 0013).
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_tasks_completed_at", ["completed_at"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_completed_at")
        batch_op.drop_column("completed_at")
