"""Batch check of payment references against provider adapters (reviewer only, evidence only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, Role, require
from app.providers import registry

router = APIRouter(prefix="/providers", tags=["providers"])
Reviewer = Annotated[Principal, Depends(require(Role.REVIEWER))]


class Item(BaseModel):
    provider: str | None = Field(default=None, max_length=40)
    reference: str = Field(min_length=1, max_length=120)


class BatchIn(BaseModel):
    items: list[Item] = Field(max_length=registry.MAX_BATCH)


@router.post("/verify-batch")
def verify_batch(body: BatchIn, p: Reviewer) -> dict:
    if not body.items:
        raise HTTPException(422, {"code": "EMPTY", "message": "No items."})
    out = registry.verify_batch([(i.provider, i.reference) for i in body.items])
    return {
        "count": len(out),
        "results": [
            {
                "reference": o.reference,
                "provider": o.provider,
                "failure": o.failure,
                "detail": o.detail,
                "record": None
                if o.record is None
                else {
                    "txn_id": o.record.txn_id,
                    "amount_minor": o.record.amount_minor,
                    "currency": o.record.currency,
                    "status": o.record.status,
                },
            }
            for o in out
        ],
        "decision_effect": "none",
    }
