"""PR-I4: ``task_edit_snapshots`` table for undo support.

Each row stores a single field change (title, priority, due_at, status,
horizon_id, category_id) with old/new values.  The ``[Отменить]`` inline
button triggers ``edit:undo:<id>`` which restores ``old_value``.
Lazy TTL: 5 minutes from ``created_at``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_edit_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("task_edit_snapshots")
