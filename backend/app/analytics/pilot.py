"""Pilot scorecard: the numbers that decide whether a shadow pilot pays for itself.

Money confirmed per day, how many cases the rules cleared without a person, fakes and duplicates
caught, how long decisions took, and an ESTIMATE of staff time saved. The estimate is automatic
approvals times a configured minutes-per-manual-check (policy `pilot_minutes_per_manual_check`,
default 2 from the BRD); it is labelled as an estimate everywhere it is shown.
"""

import statistics
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.claims.states import REVIEWABLE
from app.models import Allocation, Claim, Decision, FraudAlert
from app.policy.engine import load_policy
from app.shadow.scorecard import scorecard as shadow_scorecard

FINAL = ("APPROVED", "PARTIALLY_ALLOCATED", "REJECTED")
PERSON_APPROVED = ("APPROVED", "PARTIALLY_ALLOCATED")


def median_minutes(deltas: list[timedelta]) -> float | None:
    if not deltas:
        return None
    return round(statistics.median(d.total_seconds() for d in deltas) / 60, 1)


def estimate_minutes_saved(auto_approved: int, minutes_each: int) -> int:
    return max(auto_approved, 0) * max(minutes_each, 0)


def _window(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=UTC),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC),
    )


def pilot_scorecard(session: Session, org_id: uuid.UUID, start: date, end: date) -> dict[str, Any]:
    lo, hi = _window(start, end)
    minutes_each = load_policy(session, org_id).config.pilot_minutes_per_manual_check

    received = session.scalar(
        select(func.count(Claim.claim_id)).where(
            Claim.org_id == org_id, Claim.created_at >= lo, Claim.created_at < hi
        )
    )
    waiting_now = session.scalar(
        select(func.count(Claim.claim_id)).where(
            Claim.org_id == org_id, Claim.state.in_([s.value for s in REVIEWABLE])
        )
    )

    decisions = session.execute(
        select(
            Decision.claim_id,
            Decision.outcome,
            Decision.actor_type,
            Decision.reason_codes,
            Decision.created_at,
        ).where(Decision.org_id == org_id, Decision.created_at >= lo, Decision.created_at < hi)
    ).all()
    auto, by_person, rejected, duplicates = set(), set(), set(), set()
    final_at: dict[uuid.UUID, datetime] = {}
    for claim_id, outcome, actor, reasons, at in decisions:
        if outcome == "DUPLICATE_HOLD":
            duplicates.add(claim_id)
        if outcome in FINAL:
            final_at.setdefault(claim_id, at)
        if outcome in PERSON_APPROVED:
            if actor == "rule" and "AUTO_APPROVED" in (reasons or []):
                auto.add(claim_id)
            elif actor == "reviewer":
                by_person.add(claim_id)
        elif outcome == "REJECTED":
            rejected.add(claim_id)

    deltas: list[timedelta] = []
    if final_at:
        created = dict(
            session.execute(
                select(Claim.claim_id, Claim.created_at).where(Claim.claim_id.in_(list(final_at)))
            ).all()
        )
        deltas = [final_at[c] - created[c] for c in final_at if c in created]

    money: dict[tuple[str, str], int] = defaultdict(int)
    for kind, amount, currency, at in session.execute(
        select(Allocation.kind, Allocation.amount_minor, Allocation.currency, Allocation.created_at)
        .where(Allocation.org_id == org_id, Allocation.created_at >= lo, Allocation.created_at < hi)
        .order_by(Allocation.created_at)
    ):
        money[(at.date().isoformat(), currency)] += amount if kind == "allocation" else -amount

    fakes = session.scalar(
        select(func.count(FraudAlert.alert_id)).where(
            FraudAlert.org_id == org_id,
            FraudAlert.status == "confirmed_fake",
            FraudAlert.created_at >= lo,
            FraudAlert.created_at < hi,
        )
    )
    shadow = shadow_scorecard(session, org_id, days=(end - start).days + 1).as_dict()

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "claims_received": received or 0,
        "waiting_for_a_person_now": waiting_now or 0,
        "cleared_by_rules": len(auto),
        "approved_by_a_person": len(by_person),
        "rejected_by_a_person": len(rejected),
        "duplicates_held": len(duplicates),
        "fakes_confirmed": fakes or 0,
        "median_minutes_to_decision": median_minutes(deltas),
        "estimated_staff_minutes_saved": estimate_minutes_saved(len(auto), minutes_each),
        "estimate_note": (
            f"Estimate: {len(auto)} automatic approvals x {minutes_each} minutes per manual check "
            "(policy pilot_minutes_per_manual_check). Replace with measured times from the pilot."
        ),
        "money_confirmed_by_day": [
            {"date": d, "currency": c, "minor": v} for (d, c), v in sorted(money.items())
        ],
        "agreement_with_reviewers": shadow,
    }
