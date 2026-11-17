"""Retention for payment evidence and raw alert text.

Both are off until an organisation's policy sets a number of days (`evidence_retention_days`,
`alert_body_retention_days`). When the window passes, the files (or the message text) are removed
and the rows stay, marked `purged_at`, with their fingerprints: duplicate detection and the audit
trail keep working, and a person can see what was held and for how long. Only finished claims lose
their files. KYC images have their own purge (`kyc/service.py::purge_evidence`).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.intake.storage import get_storage
from app.models import AlertMessage, Claim, ClaimState, Evidence, Organisation
from app.policy.engine import load_policy

log = logging.getLogger(__name__)

FINISHED = (ClaimState.APPROVED, ClaimState.REJECTED, ClaimState.REVERSED_OR_REFUNDED)
REMOVED = "[removed by retention]"


def purge_payment_data(session: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    storage = get_storage()
    counts = {"evidence": 0, "alert_messages": 0}
    for org_id in list(session.scalars(select(Organisation.org_id))):
        cfg = load_policy(session, org_id).config
        if cfg.evidence_retention_days:
            cutoff = now - timedelta(days=cfg.evidence_retention_days)
            rows = session.scalars(
                select(Evidence)
                .join(Claim, Claim.claim_id == Evidence.claim_id)
                .where(
                    Evidence.org_id == org_id,
                    Evidence.purged_at.is_(None),
                    Evidence.received_at < cutoff,
                    Claim.state.in_([s.value for s in FINISHED]),
                )
                .limit(1000)
            ).all()
            for e in rows:
                for key in (e.object_key, e.preview_key, e.forensics_key):
                    if key:
                        try:
                            storage.delete(key)
                        except Exception:  # noqa: BLE001 - a missing file must not stop the purge
                            log.warning("could not delete %s during retention", key)
                e.purged_at = now
                audit(
                    session,
                    actor="rule:retention",
                    action="evidence.purged",
                    entity_type="evidence",
                    entity_id=e.evidence_id,
                    org_id=org_id,
                    after={"sha256": e.sha256, "days": cfg.evidence_retention_days},
                )
                counts["evidence"] += 1
        if cfg.alert_body_retention_days:
            cutoff = now - timedelta(days=cfg.alert_body_retention_days)
            msgs = session.scalars(
                select(AlertMessage)
                .where(
                    AlertMessage.org_id == org_id,
                    AlertMessage.purged_at.is_(None),
                    AlertMessage.created_at < cutoff,
                )
                .limit(5000)
            ).all()
            for m in msgs:
                m.body = REMOVED
                m.sender = "[removed]"
                m.subject = None
                m.parsed = None
                m.purged_at = now
            if msgs:
                audit(
                    session,
                    actor="rule:retention",
                    action="alert_messages.purged",
                    entity_type="organisation",
                    entity_id=org_id,
                    org_id=org_id,
                    after={"count": len(msgs), "days": cfg.alert_body_retention_days},
                )
                counts["alert_messages"] += len(msgs)
    return counts
