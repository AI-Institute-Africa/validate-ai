import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.claims.messages import (  # noqa: F401 - re-exported for older imports
    PAYER_MESSAGE_KEY,
    REASON_TEXT,
    explain,
    explain_keys,
    render,
)
from app.claims.states import check_transition
from app.core.audit import audit
from app.entitlements.outbox import enqueue_event, enqueue_payer_message
from app.models import Claim, ClaimState, Decision
from app.provisional.service import resolve_for_state

# states in which a claim is waiting for a human (admins are told once on entry)
REVIEW_WAITING = {ClaimState.PENDING_REVIEW, ClaimState.DUPLICATE_HOLD}


def transition(
    session: Session,
    claim: Claim,
    target: ClaimState,
    *,
    actor: str,
    reasons: list[str] | None = None,
) -> None:
    check_transition(claim.state, target)
    before = {"state": claim.state, "reason_codes": claim.reason_codes}
    was_waiting = claim.state in REVIEW_WAITING
    claim.state = target
    if reasons is not None:
        claim.reason_codes = reasons
    audit(
        session,
        actor=actor,
        action="claim.state_changed",
        entity_type="claim",
        entity_id=claim.claim_id,
        org_id=claim.org_id,
        before=before,
        after={"state": target, "reason_codes": claim.reason_codes},
        correlation_id=claim.correlation_id,
    )
    _track_review_wait(session, claim, target, was_waiting)
    resolve_for_state(session, claim, ClaimState(target))
    _tell_payer(session, claim, ClaimState(target))


# Neutral wording only: a payer is never told a claim is suspected (blueprint 4.5), and a
# rejection never says why. Sent only to claims that arrived over WhatsApp.
def _payer_text(claim: Claim, target: ClaimState) -> str | None:
    lang = claim.payer_lang  # chosen by the payer; English unless that language is switched on
    if target == ClaimState.APPROVED:
        return render("payer.approved", lang)
    if target == ClaimState.PARTIALLY_ALLOCATED:
        return render("PARTIAL_PAYMENT", lang)
    if target == ClaimState.REJECTED:
        return render("payer.rejected", lang)
    if target == ClaimState.NEEDS_INFORMATION:
        hints = " ".join(explain(list(claim.reason_codes), lang))
        return hints or render("payer.needs_info", lang)
    return None


def _tell_payer(session: Session, claim: Claim, target: ClaimState) -> None:
    text = _payer_text(claim, target)
    if text is not None:
        enqueue_payer_message(session, claim, target.value.lower(), text)


def _track_review_wait(
    session: Session, claim: Claim, target: ClaimState, was_waiting: bool
) -> None:
    now_waiting = target in REVIEW_WAITING
    if now_waiting and not was_waiting:
        now = datetime.now(UTC)
        claim.review_entered_at = now
        claim.review_escalation = 0
        codes = [str(c) for c in claim.reason_codes]
        # ids and reason codes only: no payer name, number or amount in the message
        enqueue_event(
            session,
            claim.org_id,
            "ops.review_pending",
            f"review:{claim.claim_id}:{target}:{now.isoformat()}",
            {
                "text": f"A proof of payment needs review ({target.value.lower()}"
                + (f": {', '.join(codes)}" if codes else "")
                + f"). Claim {claim.claim_id}.",
                "claim_id": str(claim.claim_id),
                "state": target.value,
                "reason_codes": codes,
            },
        )
    elif was_waiting and not now_waiting:
        claim.review_entered_at = None


def record_decision(
    session: Session,
    claim: Claim,
    *,
    outcome: str,
    reasons: list[str],
    policy_version: str,
    actor_type: str,
    actor_id: str,
    snapshot: dict[str, Any],
    credit_id: uuid.UUID | None = None,
    note: str | None = None,
) -> Decision:
    decision = Decision(
        claim_id=claim.claim_id,
        org_id=claim.org_id,
        outcome=outcome,
        reason_codes=reasons,
        policy_version=policy_version,
        actor_type=actor_type,
        actor_id=actor_id,
        credit_id=credit_id,
        evidence_snapshot=snapshot,
        note=note,
    )
    session.add(decision)
    return decision
