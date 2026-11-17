"""Build the detectors from the settings and the model folder.

Every kind always gets an answer: a working detector, or one that reports why it cannot run. A
missing model is therefore a recorded `skipped`, never an exception in the pipeline.
"""

import logging
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.detect.base import DETECT_KINDS, Detector, DetectorResult, skipped
from app.detect.image_detector import OnnxImageDetector
from app.detect.manifest import Entry, ManifestError, load_manifest
from app.detect.onnx_runtime import ModelUnavailable, OnnxScorer

log = logging.getLogger(__name__)

# kinds that load straight from an ONNX image model; the others arrive with their own detector
IMAGE_KINDS = ("receipt", "doc")


class UnavailableDetector:
    def __init__(self, kind: str, reason: str, name: str | None = None):
        self.kind = kind
        self.name = name or kind
        self.reason = reason

    def score(self, subject: object) -> DetectorResult:
        return skipped(self.kind, self.name, self.reason)


@lru_cache(maxsize=8)
def _build(model_dir: str) -> dict[str, Detector]:
    try:
        manifest: dict[str, Entry] = load_manifest(model_dir)
    except ManifestError as exc:
        log.warning("detector manifest unusable: %s", exc)
        return {k: UnavailableDetector(k, "manifest_invalid") for k in DETECT_KINDS}
    out: dict[str, Detector] = {}
    for kind in DETECT_KINDS:
        entry = manifest.get(kind)
        if entry is None:
            out[kind] = UnavailableDetector(kind, "no_model")
        elif kind not in IMAGE_KINDS:
            out[kind] = UnavailableDetector(kind, "not_implemented", entry.name)
        else:
            try:
                out[kind] = OnnxImageDetector(entry, OnnxScorer(entry))
            except ModelUnavailable as exc:
                log.warning("detector %s not loaded: %s", kind, exc)
                out[kind] = UnavailableDetector(kind, str(exc), entry.name)
    return out


def build_detectors(settings: Settings | None = None) -> dict[str, Detector]:
    s = settings or get_settings()
    if s.detect_mode == "off":
        return {}
    return _build(s.detect_model_dir)


def reset() -> None:
    """Forget loaded models (after the folder changes, and in tests)."""
    _build.cache_clear()


def describe(settings: Settings | None = None) -> dict[str, object]:
    """What the admin screen shows: the mode, the manifest state and each detector's state."""
    s = settings or get_settings()
    manifest: dict[str, Entry] = {}
    manifest_state = "absent"
    try:
        manifest = load_manifest(s.detect_model_dir)
        manifest_state = "ok" if manifest else "absent"
    except ManifestError as exc:
        manifest_state = f"invalid: {exc}"
    loaded = _build(s.detect_model_dir) if s.detect_mode != "off" else {}
    rows = []
    for kind in DETECT_KINDS:
        entry = manifest.get(kind)
        det = loaded.get(kind)
        if s.detect_mode == "off":
            state, reason = "off", None
        elif isinstance(det, UnavailableDetector):
            state, reason = "skipped", det.reason
        else:
            state, reason = "loaded", None
        rows.append(
            {
                "kind": kind,
                "state": state,
                "reason": reason,
                "name": entry.name if entry else None,
                "version": entry.version if entry else None,
                "sha256": entry.sha256 if entry else None,
                "label": entry.label if entry else None,
                "default_threshold": entry.threshold if entry else None,
                "card": entry.card if entry else None,
            }
        )
    return {
        "mode": s.detect_mode,
        "model_dir": s.detect_model_dir,
        "manifest": manifest_state,
        "detectors": rows,
    }
