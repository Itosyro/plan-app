"""Phase 2.2 models

categories, horizons, tasks, notes, ai_runs, task_events.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08 11:15:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 2.2 tables."""
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index(op.f("ix_categories_user_id"), "categories", ["user_id"], unique=False)

    op.create_table(
        "horizons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "slug"),
    )
    op.create_index(op.f("ix_horizons_user_id"), "horizons", ["user_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("horizon_id", sa.Integer(), nullable=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("priority", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("source_inbox_id", sa.Integer(), nullable=True),
        sa.Column("needs_clarification", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["horizon_id"], ["horizons.id"]),
        sa.ForeignKeyConstraint(["source_inbox_id"], ["inbox_entries.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"], unique=False)

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False),
        sa.Column("body", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_inbox_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["source_inbox_id"], ["inbox_entries.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notes_user_id"), "notes", ["user_id"], unique=False)

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("inbox_id", sa.Integer(), nullable=True),
        sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("key_index", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["inbox_id"], ["inbox_entries.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_runs_user_id"), "ai_runs", ["user_id"], unique=False)

    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_events_task_id"), "task_events", ["task_id"], unique=False)


def downgrade() -> None:
    """Drop Phase 2.2 tables."""
    op.drop_index(op.f("ix_task_events_task_id"), table_name="task_events")
    op.drop_table("task_events")
    op.drop_index(op.f("ix_ai_runs_user_id"), table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index(op.f("ix_notes_user_id"), table_name="notes")
    op.drop_table("notes")
    op.drop_index(op.f("ix_tasks_user_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_horizons_user_id"), table_name="horizons")
    op.drop_table("horizons")
    op.drop_index(op.f("ix_categories_user_id"), table_name="categories")
    op.drop_table("categories")
