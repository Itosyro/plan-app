"""Add ``user_settings.concretize_tasks`` for PR-E "make it concrete".

When ``True``, the bot prepends "Шаг 1: <first_step>" to
``Task.description`` whenever the classifier returns a non-null
``first_step`` for an abstract task. Defaults to ``False`` so the
feature stays opt-in — pre-PR-E users see no behaviour change until
they flip the toggle in /settings or the Mini-App.

We keep the column ``NOT NULL`` with a server-side default of ``false``
so the row backfill is atomic and re-runnable: any pre-existing
``user_settings`` rows pick up the default the moment the ``ALTER
TABLE`` lands, without a follow-up UPDATE. SQLite needs the boolean
written as ``0`` because its ``BOOLEAN`` storage type is actually
integer; Postgres accepts ``false``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        server_default: str = "0"
    else:
        server_default = sa.sql.expression.false().compile(
            dialect=bind.dialect,
            compile_kwargs={"literal_binds": True},
        )

    op.add_column(
        "user_settings",
        sa.Column(
            "concretize_tasks",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text(str(server_default)),
        ),
    )
    # Drop the server_default so the column matches the model definition
    # (model has plain ``default=False`` Python-side, not a server-side
    # default). Without this, future autogenerate would keep flagging
    # a phantom diff.
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.alter_column("concretize_tasks", server_default=None)


def downgrade() -> None:
    op.drop_column("user_settings", "concretize_tasks")
