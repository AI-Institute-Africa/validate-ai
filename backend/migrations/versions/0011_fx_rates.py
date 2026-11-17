"""official daily exchange rates (RBZ interbank ask rate) and the fetch log

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("rate_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("base", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("quote", sa.String(3), nullable=False, server_default="ZWG"),
        sa.Column("bid", sa.Numeric(18, 6), nullable=False),
        sa.Column("ask", sa.Numeric(18, 6), nullable=False),
        sa.Column("mid", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("pdf_sha256", sa.String(64)),
        sa.Column("pdf_object_key", sa.Text()),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("entered_by", sa.String(80)),
        sa.Column("reason", sa.Text()),
        sa.CheckConstraint("ask > 0 AND bid > 0 AND mid > 0", name="fx_rate_positive"),
        sa.CheckConstraint("method in ('direct','browser','manual')", name="fx_method"),
    )
    op.create_index("ix_fx_rates_date", "fx_rates", ["rate_date", "fetched_at"])
    op.create_table(
        "fx_fetch_log",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("method", sa.String(10)),
        sa.Column(
            "attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # history is evidence: rates and the fetch log are append-only, like the audit trail
    for table in ("fx_rates", "fx_fetch_log"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION pops_forbid_mutation()"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS fx_fetch_log_append_only ON fx_fetch_log")
    op.execute("DROP TRIGGER IF EXISTS fx_rates_append_only ON fx_rates")
    op.drop_table("fx_fetch_log")
    op.drop_index("ix_fx_rates_date", table_name="fx_rates")
    op.drop_table("fx_rates")
