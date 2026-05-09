"""Add user_settings.courier_template_style

Splits the courier configuration into two orthogonal axes:
* ``response_style_source`` (already existed) — *source* of the
  confirmation: ``template_only`` / ``llm_only`` / ``mix``.
* ``courier_template_style`` (new) — *flavour* of template (or LLM
  tone): one of ``neutral`` / ``formal_master`` / ``friendly`` /
  ``playful`` / ``terse`` / ``respectful``. Mirrors the keys of
  ``app/ai/courier.py::TEMPLATES``.

Pre-2026-05-09 the source vocab was ``formal``/``casual``/``mix``
which silently fell through both branches in ``courier.py`` (only
``mix`` was understood). The same migration normalises any pre-
existing rows: ``formal``/``casual`` → ``template_only`` (matches
the prior degenerate behaviour), everything else → keep.

See ``docs/REVIEW-2026-05-09.md::C-1``.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-09 06:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``courier_template_style`` and migrate stale source values."""
    op.add_column(
        "user_settings",
        sa.Column(
            "courier_template_style",
            sqlmodel.sql.sqltypes.AutoString(length=24),
            nullable=False,
            server_default="neutral",
        ),
    )
    # Strip the server_default once the rows are filled — the model
    # default (``"neutral"``) takes over for new INSERTs.
    op.alter_column("user_settings", "courier_template_style", server_default=None)

    # Old vocab → new vocab. ``formal`` and ``casual`` silently
    # behaved as ``template_only`` (the courier ``if/elif`` chain
    # didn't match either string), so preserve that observed behaviour.
    op.execute(
        "UPDATE user_settings SET response_style_source = 'template_only' "
        "WHERE response_style_source IN ('formal', 'casual')",
    )


def downgrade() -> None:
    """Drop ``courier_template_style`` (no inverse for vocab migration)."""
    op.drop_column("user_settings", "courier_template_style")
