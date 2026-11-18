"""Run the face detector on a selfie and on the ID portrait (docs/authenticity-detectors.md).

The aligned face crops come from the face matcher. Two scores are recorded, one per subject, so a
reviewer can see which picture was flagged. The reasons it returns (escalate mode only) are KYC
integrity flags: they send a verification to a person. They can never verify one, and a face
detector that did not run (`skipped`) is recorded, not treated as a pass.
"""

import uuid
from dataclasses import dataclass, field

from PIL import Image
from sqlalchemy.orm import Session

from app.detect import runner
from app.detect.base import DetectorResult
from app.policy.engine import PolicyConfig


@dataclass
class FaceReport:
    results: list[DetectorResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    mode: str = "off"

    def check(self) -> dict:
        return {
            "name": "face_authenticity",
            "ok": not self.reasons,
            "mode": self.mode,
            "results": [r.as_dict() for r in self.results],
        }


def assess_faces(
    session: Session,
    *,
    selfie_face: Image.Image | None,
    portrait: Image.Image | None,
    org_id: uuid.UUID,
    kyc_id: uuid.UUID,
    cfg: PolicyConfig,
    detectors=None,
    settings=None,
) -> FaceReport:
    report = FaceReport()
    for subject, crop in (("selfie", selfie_face), ("portrait", portrait)):
        if crop is None:
            continue
        one = runner.assess(
            session,
            kind="face",
            subject=crop,
            org_id=org_id,
            cfg=cfg,
            kyc_id=kyc_id,
            subject_tag=subject,
            detectors=detectors,
            settings=settings,
        )
        report.mode = one.mode
        report.results += one.results
        report.reasons += [r for r in one.reasons if r not in report.reasons]
    return report
