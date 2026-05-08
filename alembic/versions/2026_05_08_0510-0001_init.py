"""init

Phase 1: ``users`` / ``user_settings`` / ``inbox_entries`` /
``telegram_updates``. Subsequent phases will layer ``categories``,
``horizons``, ``tasks``, ``notes``, ``reminders``, ``ai_runs``, etc.

Revision ID: 0001
Revises:
Create Date: 2026-05-08 05:10:23.760087+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 1 tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("lang_code", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=True),
        sa.Column("tz", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("onboarded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "critic_mode",
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=False,
        ),
        sa.Column("critic_confidence_threshold", sa.Float(), nullable=False),
        sa.Column("default_reminder_offsets", sa.JSON(), nullable=False),
        sa.Column(
            "morning_digest_at",
            sqlmodel.sql.sqltypes.AutoString(length=5),
            nullable=False,
        ),
        sa.Column(
            "evening_digest_at",
            sqlmodel.sql.sqltypes.AutoString(length=5),
            nullable=False,
        ),
        sa.Column(
            "response_style_source",
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=False,
        ),
        sa.Column(
            "week_due_semantic",
            sqlmodel.sql.sqltypes.AutoString(length=24),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "inbox_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("raw_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("transcript", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inbox_entries_user_id"),
        "inbox_entries",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("update_id"),
    )


def downgrade() -> None:
    """Drop Phase 1 tables."""
    op.drop_table("telegram_updates")
    op.drop_index(op.f("ix_inbox_entries_user_id"), table_name="inbox_entries")
    op.drop_table("inbox_entries")
    op.drop_table("user_settings")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
