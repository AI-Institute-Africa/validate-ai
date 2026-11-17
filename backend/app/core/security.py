"""Authentication and role checks. Every permission decision is made server-side."""

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings


class Role(StrEnum):
    SUBMITTER = "submitter"  # Cognify backend or a payer-facing client
    REVIEWER = "reviewer"  # finance reviewer: confirm, reject, request info
    APPROVER = "approver"  # reviewer + manual credits, second approvals, reversals
    ADMIN = "admin"  # super admin: policies, everything above
    AUDITOR = "auditor"  # read-only: audit trail, case records, exports. Cannot submit or decide.


# The auditor sits below the submitter on purpose: every `require(...)` check refuses it, so it can
# do nothing except the routes that explicitly allow it (`require_audit_read`).
ROLE_RANK = {Role.AUDITOR: -1, Role.SUBMITTER: 0, Role.REVIEWER: 1, Role.APPROVER: 2, Role.ADMIN: 3}


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: Role
    email: str

    def at_least(self, role: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]

    @property
    def can_read_audit(self) -> bool:
        """Auditors and reviewers (and above) may read case records and the audit trail."""
        return self.role == Role.AUDITOR or self.at_least(Role.REVIEWER)

    @property
    def actor(self) -> str:
        return f"user:{self.user_id}"


def issue_token(user_id: uuid.UUID, org_id: uuid.UUID, role: Role, email: str) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role.value,
        "email": email,
        "iat": now,
        "exp": now + s.jwt_ttl_seconds,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _from_internal(token: str) -> Principal:
    data = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    return Principal(
        user_id=uuid.UUID(data["sub"]),
        org_id=uuid.UUID(data["org"]),
        role=Role(data["role"]),
        email=data.get("email", ""),
    )


def _from_oidc(token: str) -> Principal:
    """Cognify identity tokens (RS256/ES256). Role and organisation come from custom claims."""
    s = get_settings()
    assert s.oidc_jwks_url and s.oidc_issuer
    key = _jwks_client(s.oidc_jwks_url).get_signing_key_from_jwt(token)
    data = jwt.decode(
        token,
        key.key,
        algorithms=["RS256", "ES256"],
        issuer=s.oidc_issuer,
        audience=s.oidc_audience,
        options={"require": ["exp", "iss", "sub"]},
    )
    role = Role(data[s.oidc_role_claim])
    amr = data.get("amr") or []
    if s.oidc_require_mfa_for_finance and (
        ROLE_RANK[role] >= ROLE_RANK[Role.REVIEWER] or role == Role.AUDITOR
    ):
        if "mfa" not in amr and "otp" not in amr:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "finance roles must sign in with MFA")
    sub = data["sub"]
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        user_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{s.oidc_issuer}#{sub}")
    return Principal(
        user_id=user_id,
        org_id=uuid.UUID(data[s.oidc_org_claim]),
        role=role,
        email=data.get("email", ""),
    )


def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = creds.credentials
    s = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            return _from_internal(token)
        if s.oidc_jwks_url and s.oidc_issuer:
            return _from_oidc(token)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


def require_audit_read(p: Principal = Depends(current_principal)) -> Principal:
    """Read-only access to case records and the audit trail: auditors and reviewers upward."""
    if not p.can_read_audit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires role auditor or reviewer")
    return p


def require(role: Role):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.at_least(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {role.value}")
        return p

    return dep


# Short-lived signed evidence URLs (blueprint 4.3): the token binds the evidence id, the expiry
# and the person it was issued to, so a fetch can be traced to them.
# Format: "<exp>.<user hex, or - if unbound>.<mac>".
def sign_evidence(
    evidence_id: uuid.UUID, ttl: int | None = None, user_id: uuid.UUID | None = None
) -> str:
    s = get_settings()
    exp = int(time.time()) + (ttl or s.evidence_url_ttl_seconds)
    who = user_id.hex if user_id else "-"
    mac = hmac.new(s.jwt_secret.encode(), f"{evidence_id}.{exp}.{who}".encode(), hashlib.sha256)
    return f"{exp}.{who}.{mac.hexdigest()}"


def evidence_subject(evidence_id: uuid.UUID, token: str) -> str | None:
    """The user hex the link was issued to ("-" if unbound), or None if it is invalid or expired."""
    try:
        exp_s, who, mac_hex = token.split(".", 2)
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < time.time():
        return None
    s = get_settings()
    expected = hmac.new(
        s.jwt_secret.encode(), f"{evidence_id}.{exp}.{who}".encode(), hashlib.sha256
    )
    return who if hmac.compare_digest(expected.hexdigest(), mac_hex) else None


def verify_evidence_signature(evidence_id: uuid.UUID, token: str) -> bool:
    return evidence_subject(evidence_id, token) is not None
