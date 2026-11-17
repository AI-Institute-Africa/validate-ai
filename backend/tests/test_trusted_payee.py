"""A receipt addressed to somebody we do not trust is flagged; it can never be auto-approved."""

import uuid

import pytest

from app.claims import payees
from app.models import Claim
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import _import, _obligation, _stmt_row, _submit

AUTO = {
    "auto_approve_enabled": True,
    "auto_approve_channels": ["ecocash"],
    "auto_approve_max_minor": {"USD": 5000},
}


def _policy(client, **cfg) -> None:
    r = client.post(
        "/admin/policy",
        headers=login(client, "admin"),
        json={"version": f"payee-{uuid.uuid4().hex[:8]}", "config": {**AUTO, **cfg}},
    )
    assert r.status_code == 201, r.text


# --- the matching rules ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("+263 77 123 4567", "0771234567", True),  # the same wallet, written two ways
        ("263771234567", "077-123-4567", True),
        ("0771234567", "0771234568", False),  # one digit off is somebody else
        ("COGNIFY MAIN", "cognify main", True),
        ("Cognify Main", "COGNIFY-MAIN ACCOUNT", True),  # one name inside the other
        ("COGNIFY MAIN", "TENDAI MOYO", False),
        ("AB", "ABC", False),  # too short to count as "inside"
        ("", "COGNIFY", False),
        ("MERCHANT 12345", "MERCHANT12345", True),
    ],
)
def test_payee_matching(a, b, same):
    assert payees.same_payee(a, b) is same
    assert payees.same_payee(b, a) is same


def test_empty_trusted_list_trusts_nothing_but_the_check_is_skipped_by_callers():
    assert payees.is_trusted("COGNIFY", []) is False
    assert payees.is_trusted("COGNIFY", ["Tendai", "cognify"]) is True


# --- through the real pipeline --------------------------------------------------------------------


def _run(client, *, trusted, recipient):
    sub, rev = login(client, "submitter"), login(client, "reviewer")
    _policy(client, trusted_payees=trusted)
    ob = _obligation(client, sub)
    _import(client, rev, [_stmt_row()])
    png = make_receipt(ecocash_fields(beneficiary=recipient))
    claim = _submit(client, sub, ob, png, declared_amount="40.00")
    return sub, rev, client.get(f"/claims/{claim['claim_id']}", headers=rev).json()


def test_a_receipt_to_an_untrusted_recipient_is_flagged_red_and_never_auto_approved(client):
    sub, rev, c = _run(client, trusted=["COGNIFY MAIN"], recipient="Tendai Moyo")
    assert "PAYEE_NOT_TRUSTED" in c["reason_codes"]
    assert c["approval_tier"] == "RED" and c["state"] != "APPROVED"
    # the payer is told neutrally, in plain words, and never accused
    sub_view = client.get(f"/claims/{c['claim_id']}", headers=sub).json()
    assert "PAYEE_MISMATCH" in sub_view["message_keys"]
    assert not any(
        w in " ".join(sub_view["messages"]).lower() for w in ("fake", "fraud", "suspect")
    )
    assert "RECIPIENT_NOT_TRUSTED" in {s["code"] for s in c["risk_signals"]}


def test_a_trusted_recipient_passes_and_an_empty_list_has_no_opinion(client):
    _, _, ok = _run(client, trusted=["Cognify Main", "0771234567"], recipient="COGNIFY MAIN")
    assert "PAYEE_NOT_TRUSTED" not in ok["reason_codes"]


def test_with_no_trusted_payees_set_nothing_changes(client):
    _, _, c = _run(client, trusted=[], recipient="Anybody At All")
    assert "PAYEE_NOT_TRUSTED" not in c["reason_codes"]


def test_a_changed_recipient_is_an_advisory_signal_not_a_rule(client, session):
    """The payer's earlier APPROVED payments named one recipient; now a different one appears."""
    sub, rev = login(client, "submitter"), login(client, "reviewer")
    _policy(client)  # no trusted list: only the history signal can fire
    ob = _obligation(client, sub)
    _import(client, rev, [_stmt_row()])
    first = _submit(client, sub, ob, make_receipt(ecocash_fields(beneficiary="COGNIFY MAIN")))
    claim = session.get(Claim, uuid.UUID(first["claim_id"]))
    claim.state = "APPROVED"  # pretend a reviewer approved it
    session.commit()

    ob2 = _obligation(client, sub, amount=2500)
    second = _submit(
        client,
        sub,
        ob2,
        make_receipt(ecocash_fields("PP251022.1500.B22222", "25.00", beneficiary="Someone Else")),
    )
    c2 = client.get(f"/claims/{second['claim_id']}", headers=rev).json()
    assert "PAYEE_CHANGED" in {s["code"] for s in c2["risk_signals"]}
    assert "PAYEE_NOT_TRUSTED" not in c2["reason_codes"]  # advisory only: no new rule fired


def test_the_same_recipient_again_is_not_a_change(client, session):
    sub, rev = login(client, "submitter"), login(client, "reviewer")
    _policy(client)
    ob = _obligation(client, sub)
    first = _submit(client, sub, ob, make_receipt(ecocash_fields(beneficiary="Cognify Main")))
    session.get(Claim, uuid.UUID(first["claim_id"])).state = "APPROVED"
    session.commit()
    ob2 = _obligation(client, sub, amount=2500)
    second = _submit(
        client,
        sub,
        ob2,
        make_receipt(ecocash_fields("PP251022.1500.B22222", "25.00", beneficiary="COGNIFY MAIN")),
    )
    c2 = client.get(f"/claims/{second['claim_id']}", headers=rev).json()
    assert "PAYEE_CHANGED" not in {s["code"] for s in c2["risk_signals"]}
