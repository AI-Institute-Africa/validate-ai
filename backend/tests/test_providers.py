"""Provider adapters: typed failures, matching answers only, one result per item."""

from app.providers.base import Adapter, LookupFailure
from app.providers.registry import ADAPTERS, adapter_for, verify_batch
from tests.conftest import login
from tests.test_flow import TXN

GOOD = {"txn_id": TXN, "amount_minor": 4000, "currency": "usd", "status": "Successful"}


def _eco(transport):
    return {"ECOCASH": Adapter("ECOCASH", ADAPTERS["ECOCASH"].id_pattern, transport=transport)}


def test_shape_hint_and_provider_choice():
    assert ADAPTERS["ECOCASH"].looks_like(TXN) is True
    assert ADAPTERS["ECOCASH"].looks_like("XYZ") is False
    assert ADAPTERS["PAYNOW"].looks_like("anything") is None  # no guessed formats
    assert adapter_for(None, TXN).name == "ECOCASH"
    assert adapter_for("Pay Now", TXN) is None and adapter_for("paynow", "x").name == "PAYNOW"
    assert adapter_for(None, "unrecognisable") is None


def test_every_failure_is_typed_and_never_a_match():
    def timeout(_):
        raise TimeoutError

    def boom(_):
        raise RuntimeError("secret detail must not leak")

    cases = [
        (lambda _: GOOD, None),
        (timeout, LookupFailure.TIMEOUT),
        (boom, LookupFailure.UPSTREAM_ERROR),
        (lambda _: {}, LookupFailure.NOT_FOUND),
        (lambda _: {**GOOD, "txn_id": "PP000000.0000.A00000"}, LookupFailure.MISMATCH),
        (lambda _: {"txn_id": TXN}, LookupFailure.UPSTREAM_ERROR),  # wrong shape
    ]
    for transport, failure in cases:
        (o,) = verify_batch([(None, TXN)], adapters=_eco(transport))
        assert o.failure == failure, (failure, o)
        assert (o.record is not None) == (failure is None)
        assert "secret" not in o.detail
    assert o.record is None


def test_no_transport_means_not_configured_not_a_guess():
    (o,) = verify_batch([("ecocash", TXN)])
    assert o.failure == LookupFailure.NOT_CONFIGURED
    (o,) = verify_batch([("ecocash", "garbage")])
    assert o.failure == LookupFailure.BAD_FORMAT


def test_batch_keeps_order_and_reports_every_item():
    items = [(None, TXN), ("nobody", "A1"), ("ecocash", "bad"), (None, TXN)]
    out = verify_batch(items, adapters=_eco(lambda _: GOOD))
    assert [o.reference for o in out] == [r for _, r in items]
    assert [o.failure for o in out] == [
        None,
        LookupFailure.NOT_CONFIGURED,
        LookupFailure.BAD_FORMAT,
        None,
    ]


def test_batch_api_is_reviewer_only_bounded_and_evidence_only(client):
    sub, rev = login(client, "submitter"), login(client, "reviewer")
    body = {"items": [{"provider": "ecocash", "reference": TXN}, {"reference": "zzz"}]}
    assert client.post("/providers/verify-batch", headers=sub, json=body).status_code == 403
    r = client.post("/providers/verify-batch", headers=rev, json=body)
    assert r.status_code == 200 and r.json()["count"] == 2
    assert r.json()["decision_effect"] == "none"
    assert [x["failure"] for x in r.json()["results"]] == ["NOT_CONFIGURED", "NOT_CONFIGURED"]
    assert (
        client.post("/providers/verify-batch", headers=rev, json={"items": []}).status_code == 422
    )
    big = {"items": [{"reference": "a"}] * 201}
    assert client.post("/providers/verify-batch", headers=rev, json=big).status_code == 422
