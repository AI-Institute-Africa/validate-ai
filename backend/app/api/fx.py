"""Official ZWG/USD rate: look-up for reviewers, health for admins, manual entry for approvers."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.fx import service
from app.models import FxFetchLog, FxRate

router = APIRouter(tags=["official exchange rate"])
DB = Annotated[Session, Depends(get_session)]
Reviewer = Annotated[Principal, Depends(require(Role.REVIEWER))]
Approver = Annotated[Principal, Depends(require(Role.APPROVER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


def _out(row: FxRate) -> dict:
    return {
        "rate_date": row.rate_date,
        "pair": f"{row.base}/{row.quote}",
        "ask": str(row.ask),
        "bid": str(row.bid),
        "mid": str(row.mid),
        "method": row.method,
        "source_url": row.source_url,
        "pdf_sha256": row.pdf_sha256,
        "entered_by": row.entered_by,
        "reason": row.reason,
        "fetched_at": row.fetched_at,
    }


@router.get("/fx/rates")
def rate_for(db: DB, p: Reviewer, on: date | None = None) -> dict:
    """The official ask rate (ZWG per 1 USD) for a day; an older rate says it is carried forward."""
    day = on or datetime.now(UTC).date()
    found = service.get_rate(db, day)
    if found is None:
        raise HTTPException(
            404, {"code": "NO_OFFICIAL_RATE", "message": "no official rate for that day"}
        )
    return {
        "date": day,
        "ask": str(found.ask),
        "bid": str(found.bid),
        "mid": str(found.mid),
        "method": found.method,
        "source_url": found.source_url,
        "carried_forward_from": found.carried_from,
    }


@router.get("/admin/fx/status")
def status(db: DB, p: Admin) -> dict:
    s = get_settings()
    rows = db.scalars(
        select(FxRate).order_by(FxRate.rate_date.desc(), FxRate.fetched_at.desc()).limit(10)
    )
    log = db.scalars(select(FxFetchLog).order_by(FxFetchLog.attempted_at.desc()).limit(15))
    return {
        "enabled": s.fx_enabled,
        "fetch_hours_utc": s.fx_fetch_hours,
        "recent_rates": [_out(r) for r in rows],
        "recent_attempts": [
            {
                "for_date": a.for_date,
                "outcome": a.outcome,
                "detail": a.detail,
                "method": a.method,
                "attempted_at": a.attempted_at,
            }
            for a in log
        ],
    }


class ManualRateIn(BaseModel):
    rate_date: date
    ask: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    bid: Decimal | None = Field(None, gt=0, max_digits=18, decimal_places=6)
    reason: str = Field(min_length=10, max_length=500)


@router.post("/admin/fx/manual", status_code=201)
def manual(body: ManualRateIn, db: DB, p: Approver) -> dict:
    """An approver enters a rate by hand, with a written reason. Recorded in the audit trail."""
    if body.bid is not None and body.bid > body.ask:
        raise HTTPException(422, "bid cannot be above ask")
    row = service.record_manual(db, p, body.rate_date, body.ask, body.bid, body.reason)
    db.commit()
    return _out(row)
