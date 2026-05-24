"""Add ``tasks.parent_id`` self-FK for subtasks.

A Task can now be a child of another Task. Top-level tasks have
``parent_id IS NULL``; children point at their parent's ``id``.

``ON DELETE CASCADE`` so deleting a parent removes its subtree —
mirrors the existing ``tasks.user_id`` policy (R-NEW-C-3 in
``docs/REVIEW-2026-05-09-v2.md``). No backfill: legacy rows stay
top-level (``parent_id`` defaults to NULL).

SQLite needs ``batch_alter_table`` to add a FK; the production target
(Postgres) takes the column + constraint additions directly. We use
``batch_alter_table`` unconditionally — it's a no-op on Postgres and
the only safe path for SQLite (the CI matrix includes SQLite).
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_parent_id",
            "tasks",
            ["parent_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_tasks_parent_id", ["parent_id"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_parent_id")
        batch_op.drop_constraint("fk_tasks_parent_id", type_="foreignkey")
        batch_op.drop_column("parent_id")
