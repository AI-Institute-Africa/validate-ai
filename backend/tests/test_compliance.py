"""Retention, incidents and the compliance screen on a real database."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.compliance import retention
from app.core.config import get_settings
from app.models import AlertMessage, AuditEvent, Evidence, OutboxEvent
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import TXN, _obligation, _submit


def _policy(client, admin, **over):
    cfg = client.get("/admin/policy", headers=admin).json()["config"]
    cfg.update(over)
    r = client.post(
        "/admin/policy", headers=admin, json={"version": f"t-{len(over)}-{id(over)}", "config": cfg}
    )
    assert r.status_code == 201, r.text


def test_compliance_overview_shows_region_retention_and_open_incidents(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_region", "ZA-test")
    admin = login(client, "admin")
    body = client.get("/admin/compliance", headers=admin).json()
    assert body["data_region"] == "ZA-test" and body["open_incidents"] == 0
    assert body["retention"]["evidence_days"] is None and body["reporting_hours"] == 24
    assert client.get("/admin/compliance", headers=login(client, "reviewer")).status_code == 403


def test_incident_lifecycle_clock_and_affected_export(client, session):
    admin = login(client, "admin")
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    _submit(
        client,
        sub,
        ob,
        make_receipt(ecocash_fields()),
        declared_amount="40.00",
        declared_reference=TXN,
    )
    now = datetime.now(UTC)
    made = client.post(
        "/admin/incidents",
        headers=admin,
        json={
            "kind": "breach",
            "title": "Mailbox exposed",
            "summary": "An exported file was shared by mistake.",
            "detected_at": (now - timedelta(hours=13)).isoformat(),
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": now.isoformat(),
        },
    )
    assert made.status_code == 201, made.text
    inc = made.json()
    assert datetime.fromisoformat(inc["due_at"]) - datetime.fromisoformat(
        inc["detected_at"]
    ) == timedelta(hours=24)

    from app.compliance.incidents import send_reminders

    assert send_reminders(session) == 1
    session.commit()
    assert send_reminders(session) == 0  # once per stage
    ev = session.scalars(
        select(OutboxEvent).where(OutboxEvent.event_type == "ops.incident_due")
    ).one()
    assert ev.payload["stage"] == "12h"

    csv = client.get(f"/admin/incidents/{inc['incident_id']}/affected.csv", headers=admin)
    assert csv.status_code == 200 and "claim," in csv.text
    done = client.post(
        f"/admin/incidents/{inc['incident_id']}/reported",
        headers=admin,
        json={"reference": "POTRAZ-123"},
    )
    assert done.status_code == 200 and done.json()["status"] == "reported"
    assert (
        client.post(
            f"/admin/incidents/{inc['incident_id']}/reported",
            headers=admin,
            json={"reference": "again"},
        ).status_code
        == 409
    )
    assert client.get("/admin/incidents", headers=login(client, "reviewer")).status_code == 403


def test_retention_removes_files_and_alert_text_but_keeps_the_fingerprints(client, session):
    admin, rev = login(client, "admin"), login(client, "reviewer")
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    claim = _submit(
        client,
        sub,
        ob,
        make_receipt(ecocash_fields()),
        declared_amount="40.00",
        declared_reference=TXN,
    )
    cid = claim["claim_id"]
    assert (
        client.post(
            f"/review/claims/{cid}/reject", headers=rev, json={"reason": "OTHER", "note": None}
        ).status_code
        == 200
    )
    _policy(client, admin, evidence_retention_days=30)
    session.execute(update(Evidence).values(created_at=datetime.now(UTC) - timedelta(days=45)))
    session.commit()
    assert retention.purge_payment_data(session)["evidence"] == 1
    session.commit()
    ev = session.scalars(select(Evidence)).first()
    assert ev.purged_at is not None and ev.sha256
    assert session.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.purged")).first()
    d = client.get(f"/review/claims/{cid}", headers=rev).json()
    assert client.get(d["evidence"][0]["preview_url"]).status_code == 410
    assert retention.purge_payment_data(session)["evidence"] == 0  # nothing left to do


def test_unfinished_claims_keep_their_files(client, session):
    admin = login(client, "admin")
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    _submit(
        client,
        sub,
        ob,
        make_receipt(ecocash_fields()),
        declared_amount="40.00",
        declared_reference=TXN,
    )
    _policy(client, admin, evidence_retention_days=30)
    session.execute(update(Evidence).values(created_at=datetime.now(UTC) - timedelta(days=90)))
    session.commit()
    assert retention.purge_payment_data(session)["evidence"] == 0


def test_alert_text_is_removed_after_its_window(client, session):
    from tests.test_alerts import ECOCASH_SMS, _sms, _source

    admin = login(client, "admin")
    src = _source(client)
    assert _sms(client, src["key"], ECOCASH_SMS).status_code == 200
    _policy(client, admin, alert_body_retention_days=30)
    session.execute(update(AlertMessage).values(created_at=datetime.now(UTC) - timedelta(days=60)))
    session.commit()
    assert retention.purge_payment_data(session)["alert_messages"] == 1
    session.commit()
    m = session.scalars(select(AlertMessage)).one()
    assert m.body == retention.REMOVED and m.purged_at is not None and m.body_sha256
