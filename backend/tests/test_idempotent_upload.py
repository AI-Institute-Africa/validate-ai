"""A retried upload must never create a second claim (flaky mobile connections)."""

from sqlalchemy import func, select

from app.models import Claim
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import _obligation

KEY = "retry-key-0001"


def _post(client, h, ob, png, key=None, **form):
    data = {"obligation_id": ob["obligation_id"], "claimant_ref": "learner-1", "channel": "ecocash"}
    data.update(form)
    headers = {**h, **({"Idempotency-Key": key} if key else {})}
    return client.post(
        "/claims", headers=headers, data=data, files={"file": ("pop.png", png, "image/png")}
    )


def _count(session):
    session.rollback()
    return session.scalar(select(func.count()).select_from(Claim))


def test_same_key_returns_the_same_claim(client, session):
    h = login(client, "submitter")
    ob = _obligation(client, h)
    png = make_receipt(ecocash_fields())
    first = _post(client, h, ob, png, KEY)
    again = _post(client, h, ob, png, KEY)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["claim_id"] == again.json()["claim_id"]
    assert _count(session) == 1


def test_different_keys_or_no_key_behave_as_before(client, session):
    h = login(client, "submitter")
    ob = _obligation(client, h)
    a = _post(client, h, ob, make_receipt(ecocash_fields()), "key-aaaaaaaa")
    b = _post(client, h, ob, make_receipt(ecocash_fields(), seed=2), "key-bbbbbbbb")
    assert a.status_code == b.status_code == 201
    assert a.json()["claim_id"] != b.json()["claim_id"]
    assert _post(client, h, ob, make_receipt(ecocash_fields(), seed=3)).status_code == 201


def test_reusing_a_key_for_different_content_is_refused(client, session):
    h = login(client, "submitter")
    ob = _obligation(client, h)
    assert _post(client, h, ob, make_receipt(ecocash_fields()), KEY).status_code == 201
    other = _post(client, h, ob, make_receipt(ecocash_fields(), seed=9), KEY)
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    changed = _post(client, h, ob, make_receipt(ecocash_fields()), KEY, claimant_ref="someone-else")
    assert changed.status_code == 409
    assert _count(session) == 1


def test_a_malformed_key_is_rejected(client):
    h = login(client, "submitter")
    ob = _obligation(client, h)
    for bad in ("short", "has spaces in it!", "x" * 81):
        r = _post(client, h, ob, make_receipt(ecocash_fields()), bad)
        assert r.status_code in (422,), (bad, r.status_code)


def test_keys_do_not_leak_across_organisations(client, session):
    ha = login(client, "submitter", org="Alpha")
    hb = login(client, "submitter", org="Beta")
    oa, ob_ = _obligation(client, ha), _obligation(client, hb)
    png = make_receipt(ecocash_fields())
    assert _post(client, ha, oa, png, KEY).status_code == 201
    assert _post(client, hb, ob_, png, KEY).status_code == 201  # same key, other org: a new claim
    assert _count(session) == 2
