"""idempotency key for claim uploads

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("client_key", sa.String(length=80)))
    op.add_column("claims", sa.Column("request_fingerprint", sa.String(length=64)))
    op.create_index(
        "uq_claims_org_client_key",
        "claims",
        ["org_id", "client_key"],
        unique=True,
        postgresql_where=sa.text("client_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_claims_org_client_key", table_name="claims")
    op.drop_column("claims", "request_fingerprint")
    op.drop_column("claims", "client_key")
