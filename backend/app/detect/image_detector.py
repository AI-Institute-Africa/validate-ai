"""A detector backed by an ONNX image model described in the manifest."""

import time

from PIL import Image

from app.detect.base import DetectorResult, skipped
from app.detect.manifest import Entry
from app.detect.onnx_runtime import ModelUnavailable, OnnxScorer


class OnnxImageDetector:
    def __init__(self, entry: Entry, scorer: OnnxScorer):
        self.kind = entry.kind
        self.name = entry.name
        self.entry = entry
        self.default_threshold = entry.threshold
        self._scorer = scorer

    def score(self, subject: Image.Image) -> DetectorResult:
        started = time.perf_counter()
        try:
            p = self._scorer.probability(subject)
        except ModelUnavailable as exc:
            return skipped(self.kind, self.name, str(exc))
        band = self.entry.uncertain_band
        return DetectorResult(
            kind=self.kind,
            detector=self.name,
            model_version=self.entry.version,
            model_sha256=self.entry.sha256,
            score=p,
            label=self.entry.label,
            uncertain=band is not None and band[0] <= p < band[1],
            latency_ms=(time.perf_counter() - started) * 1000,
        )
