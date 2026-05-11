"""Add deleted_at to tasks and notes for 24h soft-delete (trash bin).

PR-D: soft-delete instead of physical deletion. Records with
``deleted_at IS NOT NULL`` are hidden from all list/detail queries;
a background worker purges them after 24 hours.

Partial indexes ensure hot SELECT paths (``WHERE deleted_at IS NULL``)
stay fast on both Postgres and SQLite.
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("notes", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # Partial indexes speed up the hot path (active records only).
    # Both Postgres and SQLite support partial indexes via ``WHERE``.
    op.create_index(
        "ix_tasks_active",
        "tasks",
        ["user_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_notes_active",
        "notes",
        ["user_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notes_active", table_name="notes")
    op.drop_index("ix_tasks_active", table_name="tasks")
    op.drop_column("notes", "deleted_at")
    op.drop_column("tasks", "deleted_at")
