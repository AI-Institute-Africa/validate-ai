"""Personal-data incident register with a reporting clock.

The BRD says a personal-data breach must be reported within 24 hours (to be confirmed with
counsel). An incident records when it was detected; `due_at` is detection plus 24 hours; admins are
reminded at 12 hours, at 20 hours and when overdue until someone records the report. The
affected-records export lists the claims and ID checks created in the incident's time window, as a
starting point for the notification; a person decides who was really affected.
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.security import Principal
from app.entitlements.outbox import enqueue_event
from app.models import Claim, Incident, KycVerification

REPORTING_HOURS = 24
STAGES = ((24, "overdue"), (20, "20h"), (12, "12h"))


def stage_for(detected_at: datetime, now: datetime) -> str | None:
    """Which reminder is due: 'overdue' from 24h, '20h' from 20h, '12h' from 12h, else None."""
    hours = (now - detected_at).total_seconds() / 3600
    for limit, name in STAGES:
        if hours >= limit:
            return name
    return None


def create_incident(
    session: Session,
    p: Principal,
    *,
    kind: str,
    title: str,
    summary: str,
    detected_at: datetime | None,
    window_start: datetime | None,
    window_end: datetime | None,
) -> Incident:
    detected = detected_at or datetime.now(UTC)
    inc = Incident(
        org_id=p.org_id,
        kind=kind,
        title=title,
        summary=summary,
        detected_at=detected,
        due_at=detected + timedelta(hours=REPORTING_HOURS),
        window_start=window_start,
        window_end=window_end,
        created_by=p.actor,
    )
    session.add(inc)
    session.flush()
    audit(
        session,
        actor=p.actor,
        action="incident.created",
        entity_type="incident",
        entity_id=inc.incident_id,
        org_id=p.org_id,
        after={"kind": kind, "title": title, "due_at": inc.due_at.isoformat()},
    )
    return inc


def mark_reported(session: Session, p: Principal, inc: Incident, reference: str) -> Incident:
    inc.status = "reported"
    inc.reported_at = datetime.now(UTC)
    inc.report_reference = reference
    audit(
        session,
        actor=p.actor,
        action="incident.reported",
        entity_type="incident",
        entity_id=inc.incident_id,
        org_id=p.org_id,
        after={"reference": reference, "late": inc.reported_at > inc.due_at},
    )
    return inc


def close(session: Session, p: Principal, inc: Incident, note: str) -> Incident:
    inc.status = "closed"
    inc.closed_at = datetime.now(UTC)
    audit(
        session,
        actor=p.actor,
        action="incident.closed",
        entity_type="incident",
        entity_id=inc.incident_id,
        org_id=p.org_id,
        after={"note": note},
    )
    return inc


def affected_csv(session: Session, inc: Incident) -> str:
    """Claims and ID checks created inside the incident's window (a starting list only)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["record_type", "record_id", "created_at", "subject", "channel_or_type", "state"])
    if inc.window_start and inc.window_end:
        claims = session.scalars(
            select(Claim).where(
                Claim.org_id == inc.org_id,
                Claim.created_at >= inc.window_start,
                Claim.created_at <= inc.window_end,
            )
        )
        for c in claims:
            w.writerow(
                ["claim", c.claim_id, c.created_at.isoformat(), c.claimant_ref, c.channel, c.state]
            )
        ids = session.scalars(
            select(KycVerification).where(
                KycVerification.org_id == inc.org_id,
                KycVerification.created_at >= inc.window_start,
                KycVerification.created_at <= inc.window_end,
            )
        )
        for k in ids:
            w.writerow(
                [
                    "id_check",
                    k.kyc_id,
                    k.created_at.isoformat(),
                    k.subject_ref,
                    k.subject_type,
                    k.state,
                ]
            )
    return out.getvalue()


def send_reminders(session: Session, now: datetime | None = None) -> int:
    """Queue a reminder (once per stage) for every open incident that has reached one."""
    now = now or datetime.now(UTC)
    sent = 0
    for inc in session.scalars(select(Incident).where(Incident.status == "open")):
        stage = stage_for(inc.detected_at, now)
        if stage is None:
            continue
        hours = int((now - inc.detected_at).total_seconds() // 3600)
        text = (
            f"Incident '{inc.title}' was detected {hours} hours ago and has not been reported"
            + (" (the 24-hour reporting time has passed)." if stage == "overdue" else ".")
        )
        if enqueue_event(
            session,
            inc.org_id,
            "ops.incident_due",
            f"incident:{inc.incident_id}:{stage}",
            {"text": text, "incident_id": str(inc.incident_id), "stage": stage},
        ):
            sent += 1
    return sent


def get_incident(session: Session, org_id: uuid.UUID, incident_id: uuid.UUID) -> Incident | None:
    return session.scalars(
        select(Incident).where(Incident.incident_id == incident_id, Incident.org_id == org_id)
    ).first()
