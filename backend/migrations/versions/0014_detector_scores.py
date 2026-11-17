"""authenticity detector scores (append-only)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "detector_scores",
        sa.Column("score_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.org_id"),
            nullable=False,
        ),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.claim_id")),
        sa.Column(
            "kyc_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kyc_verifications.kyc_id")
        ),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("detector", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(120)),
        sa.Column("model_sha256", sa.String(64)),
        sa.Column("score", sa.Float()),
        sa.Column("label", sa.String(20)),
        sa.Column("skipped", sa.String(80)),
        sa.Column("uncertain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("mode in ('shadow','escalate')", name="detector_mode"),
        sa.CheckConstraint(
            "score is null or (score >= 0 and score <= 1)", name="detector_score_range"
        ),
    )
    op.create_index("ix_detector_scores_claim", "detector_scores", ["claim_id"])
    op.create_index("ix_detector_scores_kyc", "detector_scores", ["kyc_id"])
    op.create_index("ix_detector_scores_kind", "detector_scores", ["org_id", "kind", "created_at"])
    # a score is evidence of what the model said at the time: append-only, like the audit trail
    op.execute(
        "CREATE TRIGGER detector_scores_append_only BEFORE UPDATE OR DELETE ON detector_scores "
        "FOR EACH ROW EXECUTE FUNCTION pops_forbid_mutation()"
    )
