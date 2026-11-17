"""The auditor can read the record and cannot change anything; evidence access is logged."""

from sqlalchemy import select

from app.models import AuditEvent
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import TXN, _obligation, _submit


def _claim(client):
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    c = _submit(
        client,
        sub,
        ob,
        make_receipt(ecocash_fields()),
        declared_amount="40.00",
        declared_reference=TXN,
    )
    return c["claim_id"]


def test_the_auditor_reads_the_record_and_nothing_else(client):
    cid = _claim(client)
    aud = login(client, "auditor")
    assert client.get(f"/review/claims/{cid}", headers=aud).status_code == 200
    assert client.get(f"/review/claims/{cid}/runs", headers=aud).status_code == 200
    assert client.get(f"/review/claims/{cid}/audit-packet", headers=aud).status_code == 200
    assert client.get(f"/audit?entity_id={cid}", headers=aud).status_code == 200
    assert client.get("/allocations/export", headers=aud).status_code in (200, 204)
    # no queue, no decisions, no submissions, no settings
    assert client.get("/review/queue", headers=aud).status_code == 403
    assert (
        client.post(
            f"/review/claims/{cid}/reject", headers=aud, json={"reason": "OTHER"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/review/claims/{cid}/reprocess", headers=aud, json={"note": "again"}
        ).status_code
        == 403
    )
    assert client.get("/admin/policy", headers=aud).status_code == 403
    assert client.get("/credits", headers=aud).status_code == 403


def test_opening_a_case_is_recorded_once_per_person_and_fetching_the_original_is_always_recorded(
    client, session
):
    cid = _claim(client)
    rev = login(client, "reviewer")
    for _ in range(3):
        d = client.get(f"/review/claims/{cid}", headers=rev).json()
    session.expire_all()
    viewed = session.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.viewed")).all()
    assert len(viewed) == 1 and viewed[0].entity_id == cid
    url = d["evidence"][0]["original_url"]
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 200
    session.expire_all()
    fetched = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "evidence.fetched")
    ).all()
    assert len(fetched) == 2 and fetched[0].actor.startswith("user:")
    preview = d["evidence"][0]["preview_url"]
    assert client.get(preview).status_code == 200  # previews are not logged one by one
    session.expire_all()
    assert (
        len(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.fetched")).all()
        )
        == 2
    )
