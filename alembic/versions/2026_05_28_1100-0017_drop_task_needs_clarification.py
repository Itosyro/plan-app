"""Drop the now-dead ``tasks.needs_clarification`` column.

The column backed the in-chat «создать? да/нет» clarify flow, which was
replaced by the «Входящие» review tab (вариант Б). The dead Python code
went away in #149; nothing reads or writes the column any more. This
migration drops it.

Down-grade re-adds the column with its prior shape — ``Boolean NOT NULL``
defaulting to ``False`` — so a rollback restores the schema, even though
no code path will populate the value.
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tasks", "needs_clarification")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        server_default: str = "0"
    else:
        server_default = sa.sql.expression.false().compile(
            dialect=bind.dialect,
            compile_kwargs={"literal_binds": True},
        )
    op.add_column(
        "tasks",
        sa.Column(
            "needs_clarification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text(str(server_default)),
        ),
    )
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column("needs_clarification", server_default=None)
