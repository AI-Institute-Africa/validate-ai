"""Pilot scorecard, audit packet and training export on a real database."""

from sqlalchemy import select

from app.models import AuditEvent
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import TXN, _import, _obligation, _stmt_row, _submit


def _approved_claim(client):
    sub, rev = login(client, "submitter"), login(client, "reviewer")
    ob = _obligation(client, sub)
    claim = _submit(
        client,
        sub,
        ob,
        make_receipt(ecocash_fields()),
        declared_amount="40.00",
        declared_reference=TXN,
    )
    _import(client, rev, [_stmt_row()])
    detail = client.get(f"/review/claims/{claim['claim_id']}", headers=rev).json()
    credit = detail["candidates"][0]["credit"]
    appr = login(client, "approver")
    r = client.post(
        f"/review/claims/{claim['claim_id']}/confirm",
        headers=appr,
        json={"credit_id": credit["credit_id"], "txn_last4": TXN[-4:], "note": None},
    )
    assert r.status_code == 200, r.text
    return claim["claim_id"], rev


def test_scorecard_counts_a_person_approved_claim_and_the_money(client):
    _approved_claim(client)
    admin = login(client, "admin")
    card = client.get("/admin/pilot-scorecard", headers=admin).json()
    assert card["claims_received"] == 1
    assert card["approved_by_a_person"] == 1 and card["cleared_by_rules"] == 0
    assert sum(d["minor"] for d in card["money_confirmed_by_day"]) == 4000
    assert "Estimate" in card["estimate_note"]
    assert (
        client.get("/admin/pilot-scorecard", headers=login(client, "reviewer")).status_code == 403
    )
    assert (
        client.get(
            "/admin/pilot-scorecard?start=2026-12-01&end=2026-11-01", headers=admin
        ).status_code
        == 422
    )


def test_audit_packet_has_the_record_and_is_itself_audited(client, session):
    cid, rev = _approved_claim(client)
    r = client.get(f"/review/claims/{cid}/audit-packet", headers=rev)
    assert r.status_code == 200, r.text
    pkt = r.json()
    assert pkt["packet_version"] == 1 and pkt["claim"]["claim_id"] == cid
    assert pkt["decisions"] and pkt["runs"] and pkt["evidence"][0]["sha256"] and pkt["allocations"]
    assert "object_key" not in str(
        pkt["evidence"]
    )  # fingerprints only, never storage paths or images
    session.expire_all()
    assert session.scalars(
        select(AuditEvent).where(AuditEvent.action == "audit_packet.exported")
    ).first()
    assert (
        client.get(
            f"/review/claims/{cid}/audit-packet", headers=login(client, "submitter")
        ).status_code
        == 403
    )
    other_org = login(client, "reviewer", org="Other Org")
    assert client.get(f"/review/claims/{cid}/audit-packet", headers=other_org).status_code == 404


def test_training_export_refuses_without_consent_and_writes_rows_with_it(client):
    cid, rev = _approved_claim(client)
    admin = login(client, "admin")
    fix = client.post(
        f"/review/claims/{cid}/fields",
        headers=rev,
        json={"name": "transaction_id", "value": TXN, "reason": "checked at the source"},
    )
    assert fix.status_code in (200, 409), fix.text
    denied = client.get("/admin/training/corrections", headers=admin)
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "CONSENT_MISSING"
    cfg = client.get("/admin/policy", headers=admin).json()["config"]
    cfg.update({"training_export_consent": True, "training_consent_ref": "AGR-2026-014"})
    assert (
        client.post(
            "/admin/policy", headers=admin, json={"version": "consent-1", "config": cfg}
        ).status_code
        == 201
    )
    ok = client.get("/admin/training/corrections", headers=admin)
    assert ok.status_code == 200 and ok.headers["X-Consent-Ref"] == "AGR-2026-014"
