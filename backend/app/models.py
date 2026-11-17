"""Relational model (blueprint 4.2, 7.2, App. D.2).

Money is stored as BIGINT minor units plus a CHAR(3) currency. Ledger, decision and audit
tables are append-only; database triggers in the initial migration enforce this.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClaimState(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED"
    AWAITING_FINANCIAL_CONFIRMATION = "AWAITING_FINANCIAL_CONFIRMATION"
    FINANCIALLY_CONFIRMED = "FINANCIALLY_CONFIRMED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DUPLICATE_HOLD = "DUPLICATE_HOLD"
    REVERSED_OR_REFUNDED = "REVERSED_OR_REFUNDED"


class EvidenceTier(StrEnum):
    E0 = "E0"  # claim only
    E1 = "E1"  # document-consistent
    E2 = "E2"  # source-corroborated (alert, attested manual confirmation)
    E3 = "E3"  # settled (statement line, signed gateway callback, provider record)


class ApprovalTier(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class ObligationType(StrEnum):
    COURSE_FEE = "course_fee"
    INSTALMENT = "instalment"
    SUBSCRIPTION = "subscription"
    USAGE = "usage"


class CreditSource(StrEnum):
    STATEMENT = "statement"
    ALERT = "alert"
    GATEWAY = "gateway"
    MANUAL = "manual"


class Organisation(Base):
    __tablename__ = "organisations"
    org_id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _created()


class PaymentPolicy(Base):
    """Versioned policy config. org_id NULL is the platform default."""

    __tablename__ = "payment_policies"
    policy_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.org_id"))
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (UniqueConstraint("org_id", "version"),)


class Obligation(Base):
    __tablename__ = "obligations"
    obligation_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(120))  # Cognify invoice id
    learner_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="obligation_amount_positive"),
        UniqueConstraint("org_id", "external_ref"),
    )


class Claim(Base):
    __tablename__ = "claims"
    claim_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obligations.obligation_id"), nullable=False
    )
    claimant_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)  # ecocash, bank_transfer…
    declared_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    declared_currency: Mapped[str | None] = mapped_column(String(3))
    declared_reference: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(40), nullable=False, default=ClaimState.RECEIVED)
    evidence_tier: Mapped[str] = mapped_column(String(2), nullable=False, default=EvidenceTier.E0)
    approval_tier: Mapped[str | None] = mapped_column(String(5))
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    candidate_credit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credits.credit_id"))
    consent_version: Mapped[str | None] = mapped_column(String(20))  # privacy notice the payer saw
    # fraud risk (app/fraud): a flag for humans, never an approval input
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(10))
    risk_signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    pipeline_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_pipeline_error: Mapped[str | None] = mapped_column(Text)
    # when the claim began waiting for a human (PENDING_REVIEW / DUPLICATE_HOLD), and how
    # many review-SLA nudges admins have already had for that wait
    review_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_escalation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # set while the payer holds provisional access for this claim (app/provisional)
    provisional_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=_uuid)
    # a client-chosen key (Idempotency-Key header) so a retried upload cannot create a second
    # claim, and a fingerprint of what was sent so the same key with different content is refused
    # the language this payer asked to be messaged in (en/sn/nd); English is used unless it is live
    payer_lang: Mapped[str | None] = mapped_column(String(2))
    client_key: Mapped[str | None] = mapped_column(String(80))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="claim")
    __table_args__ = (
        Index("ix_claims_org_state", "org_id", "state"),
        Index(
            "uq_claims_org_client_key",
            "org_id",
            "client_key",
            unique=True,
            postgresql_where=text("client_key IS NOT NULL"),
        ),
    )


class Evidence(Base):
    __tablename__ = "evidence"
    evidence_id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(300), nullable=False)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # files removed
    preview_key: Mapped[str | None] = mapped_column(String(300))  # rendered PNG for viewer
    forensics_key: Mapped[str | None] = mapped_column(String(300))  # ELA heatmap for admins
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phash: Mapped[str | None] = mapped_column(String(32))
    # same 64-bit hash as a signed integer so Hamming distance runs in SQL (bit_count)
    phash_int: Mapped[int | None] = mapped_column(BigInteger)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    received_at: Mapped[datetime] = _created()

    claim: Mapped[Claim] = relationship(back_populates="evidence")


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    run_id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = _created()


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    field_id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.evidence_id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_runs.run_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalised_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extractor: Mapped[str] = mapped_column(String(40), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {page,x,y,w,h} 0..1
    agreed: Mapped[bool] = mapped_column(default=False, nullable=False)
    # reviewer corrections keep the original row and add a new one with corrected_by set
    corrected_by: Mapped[str | None] = mapped_column(String(80))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class StatementImport(Base):
    __tablename__ = "statement_imports"
    import_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    account_alias: Mapped[str] = mapped_column(String(80), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_by: Mapped[str] = mapped_column(String(80), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    control_totals: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (UniqueConstraint("org_id", "file_sha256"),)


class Credit(Base):
    __tablename__ = "credits"
    credit_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_txn_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reference_norm: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    beneficiary: Mapped[str] = mapped_column(String(120), nullable=False)  # our account alias
    payer: Mapped[str | None] = mapped_column(String(200))
    narrative: Mapped[str | None] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(String(120))
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("statement_imports.import_id"))
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    attestation: Mapped[str | None] = mapped_column(Text)  # manual credits: evidence reference
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        UniqueConstraint("provider", "provider_txn_id", name="uq_credit_provider_txn"),
        CheckConstraint("amount_minor > 0", name="credit_amount_positive"),
        Index("ix_credits_org_occurred", "org_id", "occurred_at"),
    )


class Allocation(Base):
    """Append-only. A reversal is a new row with kind='reversal' and reverses=<original>."""

    __tablename__ = "allocations"
    allocation_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    credit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credits.credit_id"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obligations.obligation_id"), nullable=False
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.claim_id"))
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="allocation")
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reverses: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("allocations.allocation_id"), unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="allocation_amount_positive"),
        CheckConstraint("kind in ('allocation','reversal')", name="allocation_kind"),
        CheckConstraint(
            "(kind = 'reversal') = (reverses IS NOT NULL)", name="reversal_links_original"
        ),
        Index("ix_allocations_credit", "credit_id"),
        Index("ix_allocations_obligation", "obligation_id"),
    )


class ConsumedReference(Base):
    """Global registry (cross-organisation) of transaction references already credited."""

    __tablename__ = "consumed_references"
    reference_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    created_at: Mapped[datetime] = _created()


class Decision(Base):
    __tablename__ = "decisions"
    decision_id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)  # rule | reviewer
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    credit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credits.credit_id"))
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class ShadowProposal(Base):
    """Advisory AI proposal recorded beside a claim, never read by the decision path.

    Shadow mode (blueprint phase 4, innovation 8): the model proposes an outcome and a
    suggested credit; a named reviewer still decides. The scorecard compares proposals with
    what humans later decided, so the go-live decision is a measurement, not a debate.
    Append-only like decisions: proposals are measurement data, not actions.
    """

    __tablename__ = "shadow_proposals"
    proposal_id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("verification_runs.run_id"))
    # which proposer produced it: "rules" (deterministic baseline) or a model id
    proposer: Mapped[str] = mapped_column(String(120), nullable=False)
    # approve | reject | needs_info | review - advisory only, no state change ever derives from it
    proposed_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    proposed_credit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credits.credit_id"))
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        # one proposal per claim per proposer: a retried task stays idempotent
        Index("uq_shadow_claim_proposer", "claim_id", "proposer", unique=True),
        Index("ix_shadow_org_created", "org_id", "created_at"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    event_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.org_id"))
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


class OutboxEvent(Base):
    """Transactional outbox for Cognify entitlement webhooks; event_key dedupes."""

    __tablename__ = "outbox_events"
    event_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class GuardrailRule(Base):
    """An admin-managed guardrail on the AI readers (see app/guardrails).

    Guardrails can only make the pipeline stricter: every action escalates a claim to review or
    asks for information; none can approve, allocate or relax a hard gate. Removal is a soft delete
    so past verification runs stay explainable.
    """

    __tablename__ = "guardrail_rules"
    rule_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.org_id"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created()
    removed_by: Mapped[str | None] = mapped_column(String(80))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_guardrails_org_active", "org_id", "removed_at"),)


class ProvisionalGrant(Base):
    """Time-boxed, capped access granted while a receipt waits for the money to show up.

    The engine only reports it (events and GET /obligations/{id}/access); the host system decides
    what access means. It ends as confirmed (the claim was approved), revoked (rejected, reversed,
    suspected fake) or expired (no credit appeared in time).
    """

    __tablename__ = "provisional_grants"
    grant_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obligations.obligation_id"), nullable=False
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    learner_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exposure_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    granted_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_reason: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint(
            "status in ('active','confirmed','revoked','expired')", name="provisional_status"
        ),
        CheckConstraint("exposure_minor > 0", name="provisional_exposure_positive"),
        Index(
            "uq_provisional_active_claim",
            "claim_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_provisional_org_status", "org_id", "status"),
        Index("ix_provisional_obligation", "obligation_id"),
    )


class KycState(StrEnum):
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"  # capture unusable: the subject resubmits
    NEEDS_REVIEW = "NEEDS_REVIEW"  # a person decides
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class KycSubject(StrEnum):
    PAYER = "payer"  # a learner/payer submitting proofs of payment
    STAFF = "staff"  # a reviewer/approver/admin being onboarded
    ORG = "org"  # an organisation's authorised representative


class KycVerification(Base):
    """One identity-verification attempt for a subject (app/kyc).

    The readers and the face matcher only produce facts (`fields`, `checks`, the scores). The state
    is decided by deterministic rules (app/kyc/auto.py) or by a named reviewer, and every change is
    an append-only `KycDecision`. Nothing here touches the money ledger.
    """

    __tablename__ = "kyc_verifications"
    kyc_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # payer: the learner_ref / claimant_ref; staff: the user id; org: the organisation id
    subject_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default=KycState.SUBMITTED)
    submitted_by: Mapped[str] = mapped_column(String(80), nullable=False)
    doc_type: Mapped[str | None] = mapped_column(String(20))
    issuing_country: Mapped[str | None] = mapped_column(String(3))
    # keyed hash of country + document number: finds the same ID used by two subjects without
    # keeping a searchable copy of the number
    doc_number_hash: Mapped[str | None] = mapped_column(String(64))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ocr_agreement: Mapped[float | None] = mapped_column(Float)
    mrz_valid: Mapped[bool | None] = mapped_column()
    face_score: Mapped[float | None] = mapped_column(Float)
    liveness_score: Mapped[float | None] = mapped_column(Float)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pipeline_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_pipeline_error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=_uuid)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        Index("ix_kyc_org_state", "org_id", "state"),
        Index("ix_kyc_subject", "org_id", "subject_type", "subject_ref"),
        Index("ix_kyc_doc_hash", "org_id", "doc_number_hash"),
    )


class KycEvidence(Base):
    """An uploaded image: the ID (front/back/passport page) or the selfie.

    The bytes are deleted when the retention window ends; the row stays, with `purged_at` set, so
    the audit trail still shows what was held and for how long.
    """

    __tablename__ = "kyc_evidence"
    evidence_id: Mapped[uuid.UUID] = _pk()
    kyc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kyc_verifications.kyc_id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # front | back | selfie
    object_key: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phash_int: Mapped[int | None] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = _created()
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_kyc_evidence_kyc", "kyc_id"),)


class KycDecision(Base):
    """Append-only record of every KYC outcome (rule, reviewer or audit), like `Decision`."""

    __tablename__ = "kyc_decisions"
    decision_id: Mapped[uuid.UUID] = _pk()
    kyc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kyc_verifications.kyc_id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)  # rule | reviewer | audit
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (Index("ix_kyc_decisions_kyc", "kyc_id", "created_at"),)


class FraudAlert(Base):
    """A claim the risk engine thinks may be fake, escalated to an admin.

    One alert per claim; re-assessment updates it. While a high-risk alert is open the claim
    cannot be confirmed. Admins resolve it as confirmed_fake (claim rejected) or false_positive
    (claim returns to normal review); resolutions are labelled data for a future fraud model.
    """

    __tablename__ = "fraud_alerts"
    alert_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.claim_id"), nullable=False, unique=True
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolved_by: Mapped[str | None] = mapped_column(String(80))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "status in ('open','confirmed_fake','false_positive')", name="fraud_alert_status"
        ),
        Index("ix_fraud_alerts_org_status", "org_id", "status"),
    )


class AlertSource(Base):
    """A registered, trusted origin of recipient-side payment alerts.

    An SMS forwarder on the merchant phone, or a mailbox that receives bank/mobile-money credit
    notifications. Only registered sources with a valid key are accepted (threat model 4.7:
    spoofed alerts), and alert credits are capped at evidence tier E2.
    """

    __tablename__ = "alert_sources"
    source_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # sms | email
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. ECOCASH, CBZ
    account_alias: Mapped[str] = mapped_column(String(80), nullable=False)  # our account
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # SMS sender IDs (e.g. "EcoCash", "+263...") or email addresses/domains; empty = any
    allowed_senders: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    require_dkim: Mapped[bool] = mapped_column(default=True, nullable=False)
    template: Mapped[str | None] = mapped_column(String(40))  # None = try all templates
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("kind in ('sms','email')", name="alert_source_kind"),)


class AlertMessage(Base):
    """Every alert received, kept for audit whether or not it became a credit."""

    __tablename__ = "alert_messages"
    message_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_sources.source_id"), nullable=False
    )
    sender: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # text removed
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # credited | duplicate | ignored | rejected | unparsed | conflict
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    credit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credits.credit_id"))
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        UniqueConstraint("source_id", "body_sha256", name="uq_alert_message_dedupe"),
        Index("ix_alert_messages_org_created", "org_id", "created_at"),
    )


class FxRate(Base):
    """An official daily ZWG-per-USD rate (the RBZ interbank ask rate), with its evidence.

    Platform-wide, not per organisation. A corrected re-publication or a manual entry adds a new
    row; the newest row for a date is the one in use, and older rows stay as history.
    """

    __tablename__ = "fx_rates"
    rate_id: Mapped[uuid.UUID] = _pk()
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    base: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    quote: Mapped[str] = mapped_column(String(3), nullable=False, default="ZWG")
    bid: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    ask: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    mid: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_object_key: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # direct | browser | manual
    fetched_at: Mapped[datetime] = _created()
    entered_by: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("ask > 0 AND bid > 0 AND mid > 0", name="fx_rate_positive"),
        CheckConstraint("method in ('direct','browser','manual')", name="fx_method"),
        Index("ix_fx_rates_date", "rate_date", "fetched_at"),
    )


class FxFetchLog(Base):
    """One row per attempt to fetch a day's rate, for the admin status screen."""

    __tablename__ = "fx_fetch_log"
    log_id: Mapped[uuid.UUID] = _pk()
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(String(10))
    attempted_at: Mapped[datetime] = _created()


class Incident(Base):
    """A personal-data incident (for example a breach) and its reporting clock.

    The reporting duty is 24 hours from detection according to the BRD (to be confirmed with
    counsel): `due_at` is detection plus 24 hours, and reminders go to admins until it is reported.
    """

    __tablename__ = "incidents"
    incident_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # breach | near_miss | other
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_reference: Mapped[str | None] = mapped_column(String(200))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint("kind in ('breach','near_miss','other')", name="incident_kind"),
        CheckConstraint("status in ('open','reported','closed')", name="incident_status"),
        Index("ix_incidents_org_status", "org_id", "status"),
    )


class PayerPref(Base):
    """A WhatsApp payer's language, kept by a hash of the number (never the number itself)."""

    __tablename__ = "payer_prefs"
    wa_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(String(2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DetectorScore(Base):
    """One authenticity detector's score for one file or face (append-only).

    Recorded in shadow and escalate mode alike, with the model's version and SHA-256, so a past
    decision can be explained after the model has been replaced and shadow scores can be compared
    with what reviewers decided. A skipped row says why nothing was scored.
    """

    __tablename__ = "detector_scores"
    score_id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.claim_id"))
    kyc_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("kyc_verifications.kyc_id"))
    # a claim file (evidence) or a KYC photo (kyc_evidence): no foreign key, it names either
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    detector: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120))
    model_sha256: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(20))
    skipped: Mapped[str | None] = mapped_column(String(80))
    uncertain: Mapped[bool] = mapped_column(nullable=False, default=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    escalated: Mapped[bool] = mapped_column(nullable=False, default=False)
    signals: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint("mode in ('shadow','escalate')", name="detector_mode"),
        CheckConstraint(
            "score is null or (score >= 0 and score <= 1)", name="detector_score_range"
        ),
        Index("ix_detector_scores_claim", "claim_id"),
        Index("ix_detector_scores_kyc", "kyc_id"),
        Index("ix_detector_scores_kind", "org_id", "kind", "created_at"),
    )


class EvidenceEmbedding(Base):
    """The image embedding of one claim file, for near-duplicate search across organisations.

    Stored as float16 bytes of an L2-normalised vector, with the SHA-256 of the model that made it:
    vectors from different models are never compared. This is personal data in the same way the
    picture is, so retention removes it with the file (app/compliance/retention.py).
    """

    __tablename__ = "evidence_embeddings"
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.evidence_id"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.org_id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.claim_id"), nullable=False)
    model_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (Index("ix_evidence_embeddings_model", "model_sha256", "created_at"),)
