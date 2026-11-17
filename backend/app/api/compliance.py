"""Compliance screen for admins: data location, retention, model endpoints, incident register."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance import incidents as inc_svc
from app.core import ai_http
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.models import Incident
from app.policy.engine import load_policy

router = APIRouter(prefix="/admin", tags=["compliance"])
DB = Annotated[Session, Depends(get_session)]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


@router.get("/compliance")
def overview(db: DB, p: Admin) -> dict:
    s = get_settings()
    cfg = load_policy(db, p.org_id).config
    open_incidents = db.scalar(
        select(func.count(Incident.incident_id)).where(
            Incident.org_id == p.org_id, Incident.status == "open"
        )
    )
    return {
        "data_region": s.data_region,
        "storage_backend": s.storage_backend,
        "api_docs_enabled": s.docs_on,
        "retention": {
            "evidence_days": cfg.evidence_retention_days,
            "alert_text_days": cfg.alert_body_retention_days,
            "kyc_image_days": cfg.kyc_retention_days,
        },
        "ai": {
            "enforced": not s.is_dev,
            "allowed_hosts": s.ai_allowed_hosts,
            "endpoints": ai_http.endpoints(s),
        },
        "open_incidents": open_incidents or 0,
        "reporting_hours": inc_svc.REPORTING_HOURS,
    }


class IncidentIn(BaseModel):
    kind: Literal["breach", "near_miss", "other"]
    title: str = Field(min_length=5, max_length=200)
    summary: str = Field(min_length=10, max_length=4000)
    detected_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


def _out(i: Incident) -> dict:
    return {
        "incident_id": i.incident_id,
        "kind": i.kind,
        "title": i.title,
        "summary": i.summary,
        "status": i.status,
        "detected_at": i.detected_at,
        "due_at": i.due_at,
        "window_start": i.window_start,
        "window_end": i.window_end,
        "reported_at": i.reported_at,
        "report_reference": i.report_reference,
        "closed_at": i.closed_at,
        "created_by": i.created_by,
    }


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentIn, db: DB, p: Admin) -> dict:
    if body.window_start and body.window_end and body.window_start > body.window_end:
        raise HTTPException(422, "window_start must be before window_end")
    inc = inc_svc.create_incident(db, p, **body.model_dump())
    db.commit()
    return _out(inc)


@router.get("/incidents")
def list_incidents(db: DB, p: Admin, status: str | None = None) -> list[dict]:
    q = select(Incident).where(Incident.org_id == p.org_id)
    if status:
        q = q.where(Incident.status == status)
    return [_out(i) for i in db.scalars(q.order_by(Incident.detected_at.desc()).limit(200))]


def _get(db: Session, p: Principal, incident_id: uuid.UUID) -> Incident:
    inc = inc_svc.get_incident(db, p.org_id, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc


class ReportedIn(BaseModel):
    reference: str = Field(min_length=3, max_length=200, description="the regulator's reference")


class CloseIn(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


@router.post("/incidents/{incident_id}/reported")
def reported(incident_id: uuid.UUID, body: ReportedIn, db: DB, p: Admin) -> dict:
    inc = _get(db, p, incident_id)
    if inc.status != "open":
        raise HTTPException(409, f"incident is {inc.status}")
    inc_svc.mark_reported(db, p, inc, body.reference)
    db.commit()
    return _out(inc)


@router.post("/incidents/{incident_id}/close")
def close_incident(incident_id: uuid.UUID, body: CloseIn, db: DB, p: Admin) -> dict:
    inc = _get(db, p, incident_id)
    if inc.status == "closed":
        raise HTTPException(409, "incident is already closed")
    inc_svc.close(db, p, inc, body.note)
    db.commit()
    return _out(inc)


@router.get("/incidents/{incident_id}/affected.csv")
def affected(incident_id: uuid.UUID, db: DB, p: Admin) -> Response:
    """Claims and ID checks created in the incident's window: a starting list, not a verdict."""
    inc = _get(db, p, incident_id)
    return Response(
        inc_svc.affected_csv(db, inc),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="incident-{incident_id}.csv"'},
    )
