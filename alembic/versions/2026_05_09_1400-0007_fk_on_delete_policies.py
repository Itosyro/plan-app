"""Add ON DELETE policies to every foreign key.

Before this migration none of the FK constraints had an explicit
``ON DELETE`` policy, which meant:

* ``delete_task`` always failed on Postgres because it inserts a
  ``TaskEvent`` row and then deletes the parent ``Task`` in the same
  transaction — Postgres rejects the parent ``DELETE`` with a FK
  violation. SQLite does not enforce FKs by default so the unit
  tests passed silently. See ``docs/REVIEW-2026-05-09-v2.md::R-NEW-C-3``.

* Deleting a user (administrative cleanup, GDPR right-to-erasure)
  required hand-deleting every dependent row. See ``::R-NEW-I-7``.

This migration drops every existing FK constraint and recreates it
with one of two policies:

* **CASCADE** — for "owned-by-X" relationships. If X dies, the
  dependent rows die with it (e.g. ``tasks.user_id``,
  ``task_events.task_id``, ``reminders.task_id``).
* **SET NULL** — for "soft-references" where the dependent row is
  meaningful even after the parent is gone (e.g. ``tasks.category_id``
  — the task survives when its category is deleted; the row stays
  with ``category_id = NULL``). Requires the column to be nullable.

The single exception is ``telegram_updates.user_id`` which uses
``SET NULL``: the idempotency cache must outlive any user deletion so
deduplication still works for in-flight retries.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-09 14:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Helpers ──────────────────────────────────────────────────────────


def _recreate_fk(
    *,
    table: str,
    column: str,
    referent_table: str,
    referent_column: str = "id",
    ondelete: str,
    constraint_name: str,
) -> None:
    """Drop the existing FK on ``(table.column → referent_table.id)``
    and recreate it with the requested ``ondelete`` policy.

    This migration is Postgres-targeted (production). On other
    dialects (SQLite in dev / tests) it is a no-op: SQLite cannot
    ``ALTER`` a FK in place and this project's tests use
    ``SQLModel.metadata.create_all`` rather than running migrations,
    so the model-level ``ondelete='CASCADE'`` declaration is what
    drives test schemas instead.

    On Postgres, the existing FK constraint name is discovered via
    ``information_schema`` because alembic generated anonymous names
    in the original ``create_table`` calls.
    """
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # SQLite / test path: no-op. The model fields carry
        # ``ondelete='CASCADE'`` for the critical FKs and create_all
        # honours that. See tests/test_delete_task_fk.py.
        return

    result = conn.exec_driver_sql(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema   = kcu.table_schema
        WHERE tc.table_name      = %s
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name    = %s
        """,
        (table, column),
    )
    existing = result.fetchone()
    if existing is not None:
        op.drop_constraint(existing[0], table, type_="foreignkey")
    op.create_foreign_key(
        constraint_name,
        table,
        referent_table,
        [column],
        [referent_column],
        ondelete=ondelete,
    )


# ── Upgrade ──────────────────────────────────────────────────────────


def upgrade() -> None:
    """Recreate every FK with the right ON DELETE policy."""
    # User-owned data: when a user is deleted, all of it goes.
    for table, column, name in [
        ("user_settings", "user_id", "fk_user_settings_user_id_users"),
        ("inbox_entries", "user_id", "fk_inbox_entries_user_id_users"),
        ("categories", "user_id", "fk_categories_user_id_users"),
        ("horizons", "user_id", "fk_horizons_user_id_users"),
        ("tasks", "user_id", "fk_tasks_user_id_users"),
        ("notes", "user_id", "fk_notes_user_id_users"),
        ("ai_runs", "user_id", "fk_ai_runs_user_id_users"),
        ("reminders", "user_id", "fk_reminders_user_id_users"),
    ]:
        _recreate_fk(
            table=table,
            column=column,
            referent_table="users",
            ondelete="CASCADE",
            constraint_name=name,
        )

    # Idempotency cache survives user deletion — keep dedup working
    # for in-flight retries even after the user row is gone.
    _recreate_fk(
        table="telegram_updates",
        column="user_id",
        referent_table="users",
        ondelete="SET NULL",
        constraint_name="fk_telegram_updates_user_id_users",
    )

    # Task-owned audit trail: events and reminders die with the task.
    # ``task_events.task_id`` is the *primary* fix for C-3 — without
    # CASCADE, ``delete_task`` always FK-violates on Postgres because
    # we insert an event row and then delete the task in the same
    # transaction.
    for table, column, name in [
        ("task_events", "task_id", "fk_task_events_task_id_tasks"),
        ("reminders", "task_id", "fk_reminders_task_id_tasks"),
    ]:
        _recreate_fk(
            table=table,
            column=column,
            referent_table="tasks",
            ondelete="CASCADE",
            constraint_name=name,
        )

    # Soft references: tasks/notes survive when their category /
    # horizon / source-inbox is deleted; the column becomes NULL.
    for table, column, ref_table, name in [
        ("tasks", "category_id", "categories", "fk_tasks_category_id_categories"),
        ("tasks", "horizon_id", "horizons", "fk_tasks_horizon_id_horizons"),
        ("tasks", "source_inbox_id", "inbox_entries", "fk_tasks_source_inbox_id_inbox"),
        ("notes", "category_id", "categories", "fk_notes_category_id_categories"),
        ("notes", "source_inbox_id", "inbox_entries", "fk_notes_source_inbox_id_inbox"),
        ("ai_runs", "inbox_id", "inbox_entries", "fk_ai_runs_inbox_id_inbox"),
    ]:
        _recreate_fk(
            table=table,
            column=column,
            referent_table=ref_table,
            ondelete="SET NULL",
            constraint_name=name,
        )


# ── Downgrade ────────────────────────────────────────────────────────


def downgrade() -> None:
    """Drop the named CASCADE/SET-NULL constraints and recreate them
    without an ON DELETE policy. Postgres-only; no-op on other
    dialects (matching ``upgrade``).
    """
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # User-owned
    for table, column, name in [
        ("user_settings", "user_id", "fk_user_settings_user_id_users"),
        ("inbox_entries", "user_id", "fk_inbox_entries_user_id_users"),
        ("categories", "user_id", "fk_categories_user_id_users"),
        ("horizons", "user_id", "fk_horizons_user_id_users"),
        ("tasks", "user_id", "fk_tasks_user_id_users"),
        ("notes", "user_id", "fk_notes_user_id_users"),
        ("ai_runs", "user_id", "fk_ai_runs_user_id_users"),
        ("reminders", "user_id", "fk_reminders_user_id_users"),
        ("telegram_updates", "user_id", "fk_telegram_updates_user_id_users"),
    ]:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, "users", [column], ["id"])

    # Task-owned
    for table, column, name in [
        ("task_events", "task_id", "fk_task_events_task_id_tasks"),
        ("reminders", "task_id", "fk_reminders_task_id_tasks"),
    ]:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, "tasks", [column], ["id"])

    # Soft references
    for table, column, ref_table, name in [
        ("tasks", "category_id", "categories", "fk_tasks_category_id_categories"),
        ("tasks", "horizon_id", "horizons", "fk_tasks_horizon_id_horizons"),
        ("tasks", "source_inbox_id", "inbox_entries", "fk_tasks_source_inbox_id_inbox"),
        ("notes", "category_id", "categories", "fk_notes_category_id_categories"),
        ("notes", "source_inbox_id", "inbox_entries", "fk_notes_source_inbox_id_inbox"),
        ("ai_runs", "inbox_id", "inbox_entries", "fk_ai_runs_inbox_id_inbox"),
    ]:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, ref_table, [column], ["id"])
