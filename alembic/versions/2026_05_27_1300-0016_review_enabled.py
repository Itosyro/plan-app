"""Add ``user_settings.review_enabled`` to gate «Входящие» review flagging.

When ``True`` (the default) the pipeline flags inbox entries as
``needs_review`` when a message yields several tasks or anything came
back low-confidence, and appends the "📥 Отправил на проверку…" note.
When ``False`` the flagging and note are suppressed.

We keep the column ``NOT NULL`` with a server-side default of ``true``
so existing ``user_settings`` rows pick up review-ON the moment the
``ALTER TABLE`` lands — preserving the pre-feature behaviour without a
follow-up UPDATE. SQLite needs the boolean written as ``1`` because its
``BOOLEAN`` storage type is actually integer; Postgres accepts ``true``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        server_default: str = "1"
    else:
        server_default = sa.sql.expression.true().compile(
            dialect=bind.dialect,
            compile_kwargs={"literal_binds": True},
        )

    op.add_column(
        "user_settings",
        sa.Column(
            "review_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text(str(server_default)),
        ),
    )
    # Drop the server_default so the column matches the model definition
    # (model has plain ``default=True`` Python-side, not a server-side
    # default). Without this, future autogenerate would keep flagging
    # a phantom diff.
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.alter_column("review_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("user_settings", "review_enabled")
