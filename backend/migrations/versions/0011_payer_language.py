"""payer language for outbound messages

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("payer_lang", sa.String(length=2)))
    op.create_table(
        "payer_prefs",
        sa.Column("wa_hash", sa.String(length=64), primary_key=True),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("payer_prefs")
    op.drop_column("claims", "payer_lang")
