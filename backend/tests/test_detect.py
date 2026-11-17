"""Authenticity detectors in the pipeline: shadow records only, escalate sends to a person."""

import numpy as np
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.detect import registry
from app.detect.base import DetectorResult
from app.detect.near_duplicate import NearDuplicateDetector
from app.models import DetectorScore, Evidence, EvidenceEmbedding
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import _obligation, _submit


class Fake:
    kind = "receipt"
    name = "fake_receipt"
    default_threshold = 0.7

    def __init__(self, score=0.97, label="forged", skip=None, boom=False, uncertain=False):
        self._r = (score, label, skip, uncertain)
        self._boom = boom

    def score(self, subject):
        if self._boom:
            raise RuntimeError("model crashed")
        score, label, skip, uncertain = self._r
        if skip:
            return DetectorResult(kind="receipt", detector=self.name, skipped=skip)
        return DetectorResult(
            kind="receipt",
            detector=self.name,
            model_version="t1",
            model_sha256="c" * 64,
            score=score,
            label=label,
            uncertain=uncertain,
            latency_ms=1.0,
        )


def _mode(monkeypatch, mode, detector=None, **named):
    monkeypatch.setattr(get_settings(), "detect_mode", mode)
    dets = {"receipt": detector} if detector is not None else {}
    dets.update(named)
    monkeypatch.setattr(registry, "build_detectors", lambda s=None: dets)


def _claim(client, txn="PP251021.1432.A12345"):
    """The claim as staff see it (reason codes the payer never gets are included)."""
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    made = _submit(client, sub, ob, make_receipt(ecocash_fields(txn=txn)), declared_amount="40.00")
    return client.get(f"/claims/{made['claim_id']}", headers=login(client, "reviewer")).json()


def _rows(session):
    return session.scalars(select(DetectorScore)).all()


def test_off_records_nothing(client, session, monkeypatch):
    _mode(monkeypatch, "off", Fake())
    c = _claim(client)
    assert _rows(session) == []
    assert not {"FORGED_POP_SUSPECTED"} & set(c["reason_codes"])


def test_shadow_records_the_score_and_changes_nothing(client, session, monkeypatch):
    _mode(monkeypatch, "shadow", Fake(score=0.99))
    c = _claim(client)
    assert c["state"] == "AWAITING_FINANCIAL_CONFIRMATION"  # the same as with no detector
    assert "FORGED_POP_SUSPECTED" not in c["reason_codes"]
    (row,) = _rows(session)
    assert (row.kind, row.mode, row.label, row.escalated) == ("receipt", "shadow", "forged", False)
    assert row.score == pytest.approx(0.99) and row.model_sha256 == "c" * 64
    rev = login(client, "reviewer")
    runs = client.get(f"/review/claims/{c['claim_id']}/runs", headers=rev).json()
    assert runs[0]["model_versions"]["detectors"] == {"fake_receipt": "t1@cccccccccccc"}


def test_escalate_sends_a_high_score_to_a_person_and_never_to_approval(
    client, session, monkeypatch
):
    _mode(monkeypatch, "escalate", Fake(score=0.97))
    c = _claim(client)
    assert "FORGED_POP_SUSPECTED" in c["reason_codes"]
    assert c["state"] == "PENDING_REVIEW"
    (row,) = _rows(session)
    assert row.escalated is True and row.mode == "escalate"


@pytest.mark.parametrize(
    "det",
    [
        Fake(score=0.2),  # below the threshold
        Fake(uncertain=True),  # the model says it cannot tell
        Fake(skip="no_model"),
        Fake(boom=True),  # a crash is a skipped detector, not a failed claim
    ],
    ids=["low", "uncertain", "skipped", "crash"],
)
def test_the_payer_is_never_shown_a_forgery_or_ai_signal(client, monkeypatch):
    _mode(monkeypatch, "escalate", Fake(score=0.97, label="ai_generated"))
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    made = _submit(client, sub, ob, make_receipt(ecocash_fields()), declared_amount="40.00")
    staff = client.get(f"/claims/{made['claim_id']}", headers=login(client, "reviewer")).json()
    assert "AI_GENERATED_SUSPECTED" in staff["reason_codes"]
    payer = client.get(f"/claims/{made['claim_id']}", headers=sub).json()
    assert "AI_GENERATED_SUSPECTED" not in payer["reason_codes"]
    assert not any("generated" in m.lower() or "fake" in m.lower() for m in payer["messages"])


def test_escalate_ignores_low_uncertain_skipped_and_crashed(client, session, monkeypatch, det):
    _mode(monkeypatch, "escalate", det)
    c = _claim(client)
    assert c["state"] == "AWAITING_FINANCIAL_CONFIRMATION"
    assert "FORGED_POP_SUSPECTED" not in c["reason_codes"]
    (row,) = _rows(session)
    assert row.escalated is False


def test_an_organisation_can_switch_a_kind_off_or_set_its_own_threshold(
    client, session, monkeypatch
):
    admin = login(client, "admin")
    _mode(monkeypatch, "escalate", Fake(score=0.97))
    r = client.post(
        "/admin/policy",
        headers=admin,
        json={"version": "detect-off", "config": {"detect_enabled_kinds": ["doc"]}},
    )
    assert r.status_code == 201, r.text
    _claim(client)
    assert _rows(session) == []  # receipt detector switched off for this organisation
    r = client.post(
        "/admin/policy",
        headers=admin,
        json={"version": "detect-strict", "config": {"detect_thresholds": {"receipt": 0.99}}},
    )
    assert r.status_code == 201, r.text
    c = _claim(client, txn="PP251021.1433.B22222")
    assert "FORGED_POP_SUSPECTED" not in c["reason_codes"]  # 0.97 is under the stricter 0.99


def test_only_admins_see_detector_status(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "detect_mode", "shadow")
    registry.reset()
    assert client.get("/admin/detectors", headers=login(client, "reviewer")).status_code == 403
    r = client.get("/admin/detectors", headers=login(client, "admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "shadow"
    assert {d["kind"] for d in body["detectors"]} == {"receipt", "doc", "face", "duplicate", "text"}
    assert all(d["state"] == "skipped" for d in body["detectors"])  # nothing installed here
    registry.reset()


def test_detector_scores_are_append_only(client, session, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    _mode(monkeypatch, "shadow", Fake())
    _claim(client)
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE detector_scores SET score = 0"))
    session.rollback()


# --- near-duplicate embeddings -------------------------------------------------------------------


class Fixed:
    """Embeds every picture to the same unit vector: each receipt is a near-copy of the last."""

    def __init__(self, vec=(1.0, 0.0, 0.0, 0.0)):
        v = np.asarray(vec, dtype=np.float32)
        self._v = v / np.linalg.norm(v)

    def embed(self, img):
        return self._v


def _dup(embedder=None, **kw):
    return NearDuplicateDetector(
        name="fake_dup",
        version="d1",
        sha256="d" * 64,
        embedder=embedder or Fixed(),
        default_threshold=0.9,
        scan_limit=1000,
        days=30,
        **kw,
    )


def _two(client, first_txn="PP251021.1432.A11111", second_txn="PP251021.1433.B22222"):
    return _claim(client, first_txn), _claim(client, second_txn)


def test_shadow_stores_embeddings_and_records_the_match_but_holds_nothing(
    client, session, monkeypatch
):
    _mode(monkeypatch, "shadow", duplicate=_dup())
    first, second = _two(client)
    assert "NEAR_DUPLICATE_EMBEDDING" not in second["reason_codes"]
    assert len(session.scalars(select(EvidenceEmbedding)).all()) == 2
    rows = {r.claim_id: r for r in session.scalars(select(DetectorScore)).all()}
    assert str(sorted(rows.values(), key=lambda r: r.created_at)[0].score) == "0.0"
    latest = sorted(rows.values(), key=lambda r: r.created_at)[-1]
    assert latest.label == "near_duplicate" and latest.score == pytest.approx(1.0, abs=1e-3)
    assert latest.escalated is False and latest.signals == ["compared:1"]


def test_escalate_holds_both_claims_for_a_near_duplicate(client, session, monkeypatch):
    _mode(monkeypatch, "escalate", duplicate=_dup())
    first, second = _two(client)
    assert "NEAR_DUPLICATE_EMBEDDING" in second["reason_codes"]
    assert second["state"] == "DUPLICATE_HOLD"
    rev = login(client, "reviewer")
    again = client.get(f"/claims/{first['claim_id']}", headers=rev).json()
    assert again["state"] == "DUPLICATE_HOLD"  # the earlier receipt is held too, a person decides
    assert "NEAR_DUPLICATE_EMBEDDING" in again["reason_codes"]


def test_a_different_picture_does_not_escalate(client, session, monkeypatch):
    class Alternating:
        def __init__(self):
            self.n = 0

        def embed(self, img):
            self.n += 1
            return np.asarray([1.0, 0.0] if self.n % 2 else [0.0, 1.0], dtype=np.float32)

    _mode(monkeypatch, "escalate", duplicate=_dup(Alternating()))
    _, second = _two(client)
    assert "NEAR_DUPLICATE_EMBEDDING" not in second["reason_codes"]


def test_embeddings_are_never_compared_across_models(client, session, monkeypatch):
    _mode(monkeypatch, "escalate", duplicate=_dup())
    _claim(client, "PP251021.1432.A11111")
    session.execute(update(EvidenceEmbedding).values(model_sha256="e" * 64))  # an older model
    session.commit()
    second = _claim(client, "PP251021.1433.B22222")
    assert "NEAR_DUPLICATE_EMBEDDING" not in second["reason_codes"]


def test_retention_removes_the_embedding_with_the_file(client, session, monkeypatch):
    from app.compliance import retention
    from tests.test_compliance import _policy

    _mode(monkeypatch, "shadow", duplicate=_dup())
    admin, rev = login(client, "admin"), login(client, "reviewer")
    c = _claim(client)
    assert len(session.scalars(select(EvidenceEmbedding)).all()) == 1
    client.post(
        f"/review/claims/{c['claim_id']}/reject",
        headers=rev,
        json={"reason": "OTHER", "note": None},
    )
    _policy(client, admin, evidence_retention_days=30)
    from datetime import UTC, datetime, timedelta

    session.execute(update(Evidence).values(received_at=datetime.now(UTC) - timedelta(days=45)))
    session.commit()
    assert retention.purge_payment_data(session)["evidence"] == 1
    session.commit()
    assert session.scalars(select(EvidenceEmbedding)).all() == []
