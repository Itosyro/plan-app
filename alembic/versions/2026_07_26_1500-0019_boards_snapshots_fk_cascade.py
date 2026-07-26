"""Add ON DELETE CASCADE to ``boards.user_id`` and ``task_edit_snapshots.user_id``.

Migrations 0011 (``task_edit_snapshots``) and 0018 (``boards``) created
their ``user_id`` FKs without an ``ON DELETE`` policy — an oversight
against the project-wide policy set in 0007 («user-owned data dies with
the user»). On Postgres this made user deletion (administrative
cleanup, GDPR erasure) fail with an FK violation as soon as the user
had a board or an undo-snapshot. SQLite tests build their schema from
the models (which now declare ``ondelete='CASCADE'``), so only prod
needed this migration.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-26 15:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, constraint_name) — колонка везде user_id → users.id.
_TARGETS: list[tuple[str, str]] = [
    ("boards", "fk_boards_user_id_users"),
    ("task_edit_snapshots", "fk_task_edit_snapshots_user_id_users"),
]


def _find_existing_fk(table: str) -> str | None:
    """Discover the anonymous FK constraint name on ``table.user_id``."""
    conn = op.get_bind()
    result = conn.exec_driver_sql(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema   = kcu.table_schema
        WHERE tc.table_name      = %s
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name    = 'user_id'
        """,
        (table,),
    )
    row = result.fetchone()
    return row[0] if row is not None else None


def upgrade() -> None:
    """Recreate the two user_id FKs with ON DELETE CASCADE (Postgres only)."""
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite / test path: no-op — тестовая схема строится из моделей,
        # где ``ondelete='CASCADE'`` уже объявлен. См. паттерн в 0007.
        return
    for table, name in _TARGETS:
        existing = _find_existing_fk(table)
        if existing is not None:
            op.drop_constraint(existing, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Recreate the FKs without an ON DELETE policy (Postgres only)."""
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    for table, name in _TARGETS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, "users", ["user_id"], ["id"])
