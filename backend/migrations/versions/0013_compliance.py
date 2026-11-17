"""retention marks, incident register, payer consent version

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.add_column("alert_messages", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.add_column("claims", sa.Column("consent_version", sa.String(length=20)))
    op.create_table(
        "incidents",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.org_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True)),
        sa.Column("window_end", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("reported_at", sa.DateTime(timezone=True)),
        sa.Column("report_reference", sa.String(200)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind in ('breach','near_miss','other')", name="incident_kind"),
        sa.CheckConstraint("status in ('open','reported','closed')", name="incident_status"),
    )
    op.create_index("ix_incidents_org_status", "incidents", ["org_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_incidents_org_status", table_name="incidents")
    op.drop_table("incidents")
    op.drop_column("claims", "consent_version")
    op.drop_column("alert_messages", "purged_at")
    op.drop_column("evidence", "purged_at")
