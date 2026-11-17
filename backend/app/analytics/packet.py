"""Audit packet: everything needed to show an auditor how one claim was decided.

Decision, rule and policy versions, the readers and model versions that ran, the evidence's
fingerprints (never the images), what was read and any correction, allocations, the official rate
used, and the audit events. Read-only; exporting it is itself audited.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Allocation,
    AuditEvent,
    Claim,
    Decision,
    Evidence,
    ExtractedField,
    Obligation,
    VerificationRun,
)

PACKET_VERSION = 1


def build_packet(
    session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, exported_by: str
) -> dict[str, Any] | None:
    claim = session.scalars(
        select(Claim).where(Claim.claim_id == claim_id, Claim.org_id == org_id)
    ).first()
    if claim is None:
        return None
    ob = session.get(Obligation, claim.obligation_id)
    decisions = session.scalars(
        select(Decision).where(Decision.claim_id == claim_id).order_by(Decision.created_at)
    ).all()
    runs = session.scalars(
        select(VerificationRun)
        .where(VerificationRun.claim_id == claim_id)
        .order_by(VerificationRun.created_at)
    ).all()
    fx = None
    for d in reversed(decisions):
        snap = (d.evidence_snapshot or {}).get("fx")
        if snap:
            fx = snap
            break
    return {
        "packet_version": PACKET_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": exported_by,
        "claim": {
            "claim_id": str(claim.claim_id),
            "channel": claim.channel,
            "claimant_ref": claim.claimant_ref,
            "declared_amount_minor": claim.declared_amount_minor,
            "declared_currency": claim.declared_currency,
            "declared_reference": claim.declared_reference,
            "state": str(claim.state),
            "evidence_tier": str(claim.evidence_tier),
            "approval_tier": str(claim.approval_tier) if claim.approval_tier else None,
            "reason_codes": list(claim.reason_codes),
            "risk_score": claim.risk_score,
            "risk_level": claim.risk_level,
            "created_at": claim.created_at.isoformat(),
            "consent_version": claim.consent_version,
        },
        "data_region": get_settings().data_region,
        "invoice": None
        if ob is None
        else {
            "obligation_id": str(ob.obligation_id),
            "description": ob.description,
            "amount_minor": ob.amount_minor,
            "currency": ob.currency,
            "payment_code": ob.payment_code,
        },
        "official_rate": fx,
        "decisions": [
            {
                "decision_id": str(d.decision_id),
                "outcome": d.outcome,
                "actor_type": d.actor_type,
                "actor_id": d.actor_id,
                "reason_codes": list(d.reason_codes),
                "policy_version": d.policy_version,
                "credit_id": str(d.credit_id) if d.credit_id else None,
                "note": d.note,
                "evidence_snapshot": d.evidence_snapshot,
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions
        ],
        "runs": [
            {
                "run_id": str(r.run_id),
                "created_at": r.created_at.isoformat(),
                "pipeline_version": r.pipeline_version,
                "policy_version": r.policy_version,
                "model_versions": r.model_versions,
                "outcome": r.outcome,
                "flags": list(r.flags),
            }
            for r in runs
        ],
        "evidence": [
            {
                "evidence_id": str(e.evidence_id),
                "sha256": e.sha256,
                "content_type": e.content_type,
                "size_bytes": e.size_bytes,
                "created_at": e.received_at.isoformat(),
            }
            for e in session.scalars(
                select(Evidence).where(Evidence.claim_id == claim_id).order_by(Evidence.received_at)
            )
        ],
        "fields_read": [
            {
                "name": f.name,
                "raw_value": f.raw_value,
                "normalised_value": f.normalised_value,
                "extractor": f.extractor,
                "extractor_version": f.extractor_version,
                "confidence": f.confidence,
                "agreed": f.agreed,
                "corrected_by": f.corrected_by,
                "correction_reason": f.correction_reason,
                "run_id": str(f.run_id),
            }
            for f in session.scalars(
                select(ExtractedField)
                .where(ExtractedField.claim_id == claim_id)
                .order_by(ExtractedField.created_at)
            )
        ],
        "allocations": [
            {
                "allocation_id": str(a.allocation_id),
                "kind": a.kind,
                "amount_minor": a.amount_minor,
                "currency": a.currency,
                "credit_id": str(a.credit_id),
                "created_by": a.created_by,
                "created_at": a.created_at.isoformat(),
            }
            for a in session.scalars(
                select(Allocation)
                .where(Allocation.claim_id == claim_id)
                .order_by(Allocation.created_at)
            )
        ],
        "audit_events": [
            {
                "action": ev.action,
                "actor": ev.actor,
                "at": ev.created_at.isoformat(),
                "after": ev.after,
            }
            for ev in session.scalars(
                select(AuditEvent)
                .where(AuditEvent.org_id == org_id, AuditEvent.entity_id == str(claim_id))
                .order_by(AuditEvent.created_at)
                .limit(500)
            )
        ],
    }
