"""Add ``boards`` table for the Excalidraw canvas feature.

Boards are free-form visual canvases (mind-maps) the user draws on
directly in the Mini-App. The whole Excalidraw scene is serialised to
``scene_json`` (JSON / JSONB on Postgres). Soft-deleted via
``deleted_at`` like tasks/notes. ``user_id`` is indexed because the
list endpoint always filters by owner.

See ``docs/BOARDS-PLAN.md``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scene_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_boards_user_id", "boards", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_boards_user_id", table_name="boards")
    op.drop_table("boards")
