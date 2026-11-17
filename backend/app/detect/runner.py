"""Run the detectors for one subject, record the scores, and say whether anything escalates.

shadow mode: scores are recorded and nothing else changes. escalate mode: a score at or above the
threshold adds a reason code, which sends the claim (or verification) to a person. Nothing here can
approve or reject, and a skipped, uncertain or below-threshold result adds nothing.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.detect import registry
from app.detect.base import Detector, DetectorResult, skipped
from app.models import DetectorScore
from app.policy.engine import PolicyConfig

log = logging.getLogger(__name__)

# (kind, what a high score means) -> the reason code that sends the case to a person
ESCALATION: dict[tuple[str, str], str] = {
    ("receipt", "forged"): "FORGED_POP_SUSPECTED",
    ("receipt", "ai_generated"): "AI_GENERATED_SUSPECTED",
    ("doc", "forged"): "DOC_TAMPER_SUSPECTED",
    ("doc", "ai_generated"): "AI_GENERATED_SUSPECTED",
    ("face", "deepfake"): "DEEPFAKE_SUSPECTED",
    ("face", "synthetic_face"): "SYNTHETIC_FACE_SUSPECTED",
    ("duplicate", "near_duplicate"): "NEAR_DUPLICATE_EMBEDDING",
    ("text", "ai_text"): "AI_TEXT_SUSPECTED",
}


@dataclass
class Report:
    mode: str = "off"
    results: list[DetectorResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def check(self, **extra: Any) -> dict[str, Any]:
        """The entry written into a run's checks."""
        return {
            "layer": 6,
            "check": "authenticity",
            "mode": self.mode,
            "results": [r.as_dict() for r in self.results],
            **extra,
        }


def threshold_for(kind: str, cfg: PolicyConfig, detector: Detector | None) -> float | None:
    """The organisation's threshold, else the one the model was published with, else none (a
    detector with no threshold never escalates)."""
    if kind in cfg.detect_thresholds:
        return cfg.detect_thresholds[kind]
    return getattr(detector, "default_threshold", None)


def escalation_reason(result: DetectorResult, threshold: float | None, mode: str) -> str | None:
    if (
        mode != "escalate"
        or threshold is None
        or result.skipped
        or result.uncertain
        or result.score is None
        or result.label is None
        or result.score < threshold
    ):
        return None
    return ESCALATION.get((result.kind, result.label))


def safe_score(detector: Detector, subject: Any) -> DetectorResult:
    """A detector that raises is a skipped detector: intake and decisions carry on unchanged."""
    try:
        return detector.score(subject)
    except Exception as exc:  # noqa: BLE001 - a detector must never break a claim
        log.exception("detector %s failed", getattr(detector, "name", "?"))
        return skipped(detector.kind, detector.name, f"error:{type(exc).__name__}")


def assess(
    session: Session,
    *,
    kind: str,
    subject: Any,
    org_id: uuid.UUID,
    cfg: PolicyConfig,
    claim_id: uuid.UUID | None = None,
    kyc_id: uuid.UUID | None = None,
    evidence_id: uuid.UUID | None = None,
    settings: Settings | None = None,
    detectors: dict[str, Detector] | None = None,
) -> Report:
    s = settings or get_settings()
    report = Report(mode=s.detect_mode)
    if s.detect_mode == "off" or kind not in cfg.detect_enabled_kinds:
        return report
    dets = detectors if detectors is not None else registry.build_detectors(s)
    detector = dets.get(kind)
    if detector is None:
        return report
    result = safe_score(detector, subject)
    report.results.append(result)
    reason = escalation_reason(result, threshold_for(kind, cfg, detector), s.detect_mode)
    if reason:
        report.reasons.append(reason)
    session.add(
        DetectorScore(
            org_id=org_id,
            claim_id=claim_id,
            kyc_id=kyc_id,
            evidence_id=evidence_id,
            kind=result.kind,
            detector=result.detector,
            model_version=result.model_version,
            model_sha256=result.model_sha256,
            score=result.score,
            label=result.label,
            skipped=result.skipped,
            uncertain=result.uncertain,
            mode=s.detect_mode,
            signals=result.signals,
            escalated=bool(reason),
        )
    )
    return report


def versions_from_checks(checks: list[dict[str, Any]]) -> dict[str, str]:
    """{detector: version@sha12} for the detectors that actually scored, for model_versions."""
    out: dict[str, str] = {}
    for c in checks:
        if c.get("check") != "authenticity":
            continue
        for r in c.get("results", []):
            if r.get("model_version") and not r.get("skipped"):
                out[r["detector"]] = f"{r['model_version']}@{(r.get('model_sha256') or '')[:12]}"
    return out
