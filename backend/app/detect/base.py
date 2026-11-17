"""The shared shape of every authenticity detector (docs/authenticity-detectors.md).

A detector looks at one subject (an image, or text) and returns a score from 0 to 1 for "this is
what the detector is looking for" (forged, AI-generated, a deepfake, a near-duplicate). It never
approves or rejects anything: a score is evidence for a person. Nothing here imports the rest of the
engine, so the policy and the pipeline can both depend on it.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

# receipt: payment proofs. doc: ID cards and passports. face: selfie / ID portrait.
# duplicate: near-duplicate embedding. text: AI-written text.
DETECT_KINDS = ("receipt", "doc", "face", "duplicate", "text")

# what a high score means, as written by the model's manifest
LABELS = ("forged", "ai_generated", "deepfake", "synthetic_face", "near_duplicate", "ai_text")


@dataclass(frozen=True)
class DetectorResult:
    kind: str
    detector: str  # the model's name, for example "receipt_forgery"
    model_version: str | None = None
    model_sha256: str | None = None
    score: float | None = None  # 0..1, None when skipped
    label: str | None = None  # what a high score means (one of LABELS)
    skipped: str | None = None  # why nothing was scored; the existing rules then run unchanged
    uncertain: bool = False  # the score sits in the model's "cannot tell" band
    latency_ms: float | None = None
    signals: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detector": self.detector,
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "score": None if self.score is None else round(self.score, 4),
            "label": self.label,
            "skipped": self.skipped,
            "uncertain": self.uncertain,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "signals": list(self.signals),
        }


def skipped(kind: str, detector: str, reason: str) -> DetectorResult:
    """A detector that could not run. Recorded, never treated as a pass or a fail."""
    return DetectorResult(kind=kind, detector=detector, skipped=reason)


class Detector(Protocol):
    kind: str
    name: str

    def score(self, subject: Any) -> DetectorResult: ...
