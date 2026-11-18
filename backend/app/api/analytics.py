"""Pilot scorecard, per-case audit packet and consented training export."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.analytics import packet as packet_mod
from app.analytics import training
from app.analytics.pilot import pilot_scorecard
from app.core.audit import audit
from app.core.db import get_session
from app.core.security import Principal, Role, require, require_audit_read
from app.policy.engine import load_policy

router = APIRouter(tags=["pilot and audit"])
DB = Annotated[Session, Depends(get_session)]
AuditRead = Annotated[Principal, Depends(require_audit_read)]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


@router.get("/admin/pilot-scorecard")
def scorecard(db: DB, p: Admin, start: date | None = None, end: date | None = None) -> dict:
    """Numbers for a pilot window (default: the last 14 days). Staff time saved is an estimate."""
    last = end or datetime.now(UTC).date()
    first = start or (last - timedelta(days=13))
    if first > last or (last - first).days > 366:
        raise HTTPException(422, "start must be before end, within one year")
    return pilot_scorecard(db, p.org_id, first, last)


@router.get("/review/claims/{claim_id}/audit-packet")
def audit_packet(claim_id: uuid.UUID, db: DB, p: AuditRead) -> dict:
    """How one claim was decided, for an auditor: no images, only fingerprints and records."""
    data = packet_mod.build_packet(db, p.org_id, claim_id, p.actor)
    if data is None:
        raise HTTPException(404, "claim not found")
    audit(
        db,
        actor=p.actor,
        action="audit_packet.exported",
        entity_type="claim",
        entity_id=claim_id,
        org_id=p.org_id,
    )
    db.commit()
    return data


@router.get("/admin/training/detector-labels")
def training_detector_labels(db: DB, p: Admin, since: datetime | None = None) -> Response:
    """Authenticity labels (confirmed fake / not fake) as JSON lines; needs consent on record."""
    cfg = load_policy(db, p.org_id).config
    try:
        ref = training.require_consent(cfg)
    except training.ConsentMissing as exc:
        raise HTTPException(403, {"code": "CONSENT_MISSING", "message": str(exc)}) from exc
    rows = list(training.detector_labels(db, p.org_id, since))
    audit(
        db,
        actor=p.actor,
        action="training.exported",
        entity_type="organisation",
        entity_id=p.org_id,
        org_id=p.org_id,
        after={"rows": len(rows), "consent_ref": ref, "kind": "detector_labels"},
    )
    db.commit()
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return Response(
        content=body + ("\n" if rows else ""),
        media_type="application/x-ndjson",
        headers={"X-Consent-Ref": ref, "X-Row-Count": str(len(rows))},
    )


@router.get("/admin/training/corrections")
def training_corrections(db: DB, p: Admin, since: datetime | None = None) -> Response:
    """Reviewer corrections as JSON lines; needs consent on record in the policy."""
    cfg = load_policy(db, p.org_id).config
    try:
        ref = training.require_consent(cfg)
    except training.ConsentMissing as exc:
        raise HTTPException(403, {"code": "CONSENT_MISSING", "message": str(exc)}) from exc
    rows = list(training.corrections(db, p.org_id, since))
    audit(
        db,
        actor=p.actor,
        action="training.exported",
        entity_type="organisation",
        entity_id=p.org_id,
        org_id=p.org_id,
        after={"rows": len(rows), "consent_ref": ref},
    )
    db.commit()
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return Response(
        content=body + ("\n" if rows else ""),
        media_type="application/x-ndjson",
        headers={"X-Consent-Ref": ref, "X-Row-Count": str(len(rows))},
    )
