import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent


def audit(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    org_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Append an audit event in the caller's transaction (never committed on its own)."""
    session.add(
        AuditEvent(
            org_id=org_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            before=before,
            after=after,
            correlation_id=correlation_id,
        )
    )


def audit_once(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    org_id: uuid.UUID | None,
    within_minutes: int = 15,
    after: dict[str, Any] | None = None,
) -> bool:
    """Like `audit`, but skips a repeat by the same actor for the same entity inside a window, so
    that opening one page that loads several files is one event, not dozens."""
    since = datetime.now(UTC) - timedelta(minutes=within_minutes)
    seen = session.scalars(
        select(AuditEvent.event_id)
        .where(
            AuditEvent.actor == actor,
            AuditEvent.action == action,
            AuditEvent.entity_id == str(entity_id),
            AuditEvent.created_at >= since,
        )
        .limit(1)
    ).first()
    if seen is not None:
        return False
    audit(
        session,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        org_id=org_id,
        after=after,
    )
    return True
