"""Reviewer corrections as training labels, only with a written consent reference.

Each time a person corrects a field, the engine already keeps the model's reading and the person's
correction. This turns those pairs into rows a fine-tuning job can use. It refuses to run unless the
organisation's policy records consent (`training_export_consent` and a `training_consent_ref`), and
every export is audited. Images are never included: rows carry the evidence SHA-256 so the files can
be fetched separately, under the same consent, from secure storage.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evidence, ExtractedField
from app.policy.engine import PolicyConfig


class ConsentMissing(Exception):
    pass


def require_consent(cfg: PolicyConfig) -> str:
    if not cfg.training_export_consent or not (cfg.training_consent_ref or "").strip():
        raise ConsentMissing(
            "training export needs training_export_consent and a training_consent_ref in the policy"
        )
    return str(cfg.training_consent_ref)


def corrections(
    session: Session, org_id: uuid.UUID, since: datetime | None = None, limit: int = 100_000
) -> Iterator[dict[str, Any]]:
    """One row per corrected field: what the model read, what the person wrote, and why."""
    q = (
        select(ExtractedField)
        .join(Evidence, Evidence.evidence_id == ExtractedField.evidence_id)
        .where(Evidence.org_id == org_id, ExtractedField.corrected_by.is_not(None))
        .order_by(ExtractedField.created_at)
        .limit(limit)
    )
    if since is not None:
        q = q.where(ExtractedField.created_at >= since)
    for fix in session.scalars(q):
        model = session.scalars(
            select(ExtractedField)
            .where(
                ExtractedField.claim_id == fix.claim_id,
                ExtractedField.run_id == fix.run_id,
                ExtractedField.name == fix.name,
                ExtractedField.corrected_by.is_(None),
            )
            .order_by(ExtractedField.created_at)
            .limit(1)
        ).first()
        ev = session.get(Evidence, fix.evidence_id)
        yield {
            "evidence_sha256": ev.sha256 if ev else None,
            "content_type": ev.content_type if ev else None,
            "field": fix.name,
            "model_reading": model.raw_value if model else None,
            "model": f"{model.extractor}:{model.extractor_version}" if model else None,
            "model_confidence": model.confidence if model else None,
            "corrected_value": fix.raw_value,
            "reason": fix.correction_reason,
            "corrected_at": fix.created_at.isoformat(),
        }
