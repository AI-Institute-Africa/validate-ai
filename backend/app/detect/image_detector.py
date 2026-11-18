"""A detector backed by an ONNX image model described in the manifest."""

import time
from typing import Protocol

from PIL import Image

from app.detect.base import DetectorResult, skipped
from app.detect.manifest import Entry
from app.detect.onnx_runtime import ModelUnavailable


class Scorer(Protocol):
    def probability(self, img: Image.Image) -> float: ...


def tta_views(img: Image.Image, n: int) -> list[Image.Image]:
    """The image plus up to four mild variations (small shifts and centre crops, resized back).

    Averaging a model over views that a real capture could differ by makes one lucky or unlucky
    pixel pattern matter less. n = 1 is just the image.
    """
    w, h = img.size
    boxes = [
        (4, 4, w, h),
        (int(w * 0.025), int(h * 0.025), int(w * 0.975), int(h * 0.975)),
        (0, 0, w - 4, h - 4),
        (int(w * 0.05), int(h * 0.05), int(w * 0.95), int(h * 0.95)),
    ]
    views = [img]
    for box in boxes[: max(0, min(n, 5) - 1)]:
        if box[2] - box[0] >= 16 and box[3] - box[1] >= 16:
            views.append(img.crop(box).resize((w, h), Image.Resampling.BILINEAR))
    return views


class OnnxImageDetector:
    def __init__(self, entry: Entry, scorer: Scorer):
        self.kind = entry.kind
        self.name = entry.name
        self.entry = entry
        self.default_threshold = entry.threshold
        self._scorer = scorer

    def score(self, subject: Image.Image) -> DetectorResult:
        started = time.perf_counter()
        views = tta_views(subject, self.entry.tta)
        try:
            p = sum(self._scorer.probability(v) for v in views) / len(views)
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
            signals=[f"tta:{len(views)}"] if len(views) > 1 else [],
        )
