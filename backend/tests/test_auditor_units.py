"""Auditor role and user-bound evidence links (no database)."""

import time
import uuid

import pytest
from fastapi import HTTPException

from app.core.security import (
    ROLE_RANK,
    Principal,
    Role,
    evidence_subject,
    require,
    require_audit_read,
    sign_evidence,
    verify_evidence_signature,
)


def _p(role: Role) -> Principal:
    return Principal(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role=role, email="x@example.com")


def test_the_auditor_ranks_below_everyone_so_every_ordinary_check_refuses_it():
    assert ROLE_RANK[Role.AUDITOR] < ROLE_RANK[Role.SUBMITTER]
    aud = _p(Role.AUDITOR)
    for needed in (Role.SUBMITTER, Role.REVIEWER, Role.APPROVER, Role.ADMIN):
        assert not aud.at_least(needed)
        with pytest.raises(HTTPException) as e:
            require(needed)(aud)
        assert e.value.status_code == 403


def test_audit_read_allows_the_auditor_and_reviewers_upward_but_not_submitters():
    assert require_audit_read(_p(Role.AUDITOR)).role == Role.AUDITOR
    for role in (Role.REVIEWER, Role.APPROVER, Role.ADMIN):
        assert require_audit_read(_p(role))
    with pytest.raises(HTTPException):
        require_audit_read(_p(Role.SUBMITTER))


def test_evidence_link_is_bound_to_the_person_it_was_issued_to():
    ev, user = uuid.uuid4(), uuid.uuid4()
    token = sign_evidence(ev, user_id=user)
    assert evidence_subject(ev, token) == user.hex
    assert verify_evidence_signature(ev, token)
    assert not verify_evidence_signature(uuid.uuid4(), token)  # a different file
    exp, who, mac = token.split(".")
    assert evidence_subject(ev, f"{exp}.{uuid.uuid4().hex}.{mac}") is None  # swapped person
    assert evidence_subject(ev, f"{int(exp) + 10}.{who}.{mac}") is None  # extended expiry
    assert evidence_subject(ev, "garbage") is None


def test_unbound_links_still_work_and_expired_ones_do_not():
    ev = uuid.uuid4()
    assert evidence_subject(ev, sign_evidence(ev)) == "-"
    assert evidence_subject(ev, sign_evidence(ev, ttl=-5)) is None
    assert time.time() > 0
