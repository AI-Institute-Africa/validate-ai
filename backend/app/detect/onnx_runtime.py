"""Run one ONNX model on the CPU, after checking its hash.

The model contract: one image tensor in (float32, 1 x C x H x W), one probability out (0..1).
Anything else, a missing file, a wrong hash or a missing runtime raises `ModelUnavailable`, which
the detector turns into a recorded `skipped` result.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.detect import features
from app.detect.manifest import Entry, file_sha256


class ModelUnavailable(RuntimeError):
    """The detector cannot run; `args[0]` is a short machine-readable reason."""


def _rgb(img: Image.Image, size: int) -> np.ndarray:
    small = img.convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    return arr.transpose(2, 0, 1) / 255.0  # 3 x H x W


def _plane(
    fn: Callable[[Image.Image, int], np.ndarray],
) -> Callable[[Image.Image, int], np.ndarray]:
    def one(img: Image.Image, size: int) -> np.ndarray:
        return fn(img, size)[None, ...]  # 1 x H x W

    return one


# Input channels a model may ask for in its manifest: rgb is 3 planes, each forensic channel 1.
CHANNELS: dict[str, Callable[[Image.Image, int], np.ndarray]] = {
    "rgb": _rgb,
    "noise": _plane(features.noise_residual),
    "fft": _plane(features.fft_spectrum),
    "ela": _plane(features.ela_map),
}


def to_tensor(img: Image.Image, size: int, channels: tuple[str, ...]) -> np.ndarray:
    parts = []
    for name in channels:
        if name not in CHANNELS:
            raise ModelUnavailable(f"unknown_channel:{name}")
        parts.append(CHANNELS[name](img, size))
    return np.concatenate(parts, axis=0)[None, ...].astype(np.float32)


class OnnxScorer:
    def __init__(self, entry: Entry):
        self.entry = entry
        path: Path = entry.file
        if not path.is_file():
            raise ModelUnavailable("file_missing")
        if file_sha256(path) != entry.sha256:
            raise ModelUnavailable("hash_mismatch")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ModelUnavailable("onnxruntime_missing") from exc
        try:
            self._session: Any = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001 - a corrupt model must not stop intake
            raise ModelUnavailable("model_unreadable") from exc
        self._input = self._session.get_inputs()[0].name

    def probability(self, img: Image.Image) -> float:
        tensor = to_tensor(img, self.entry.size, self.entry.channels)
        out = self._session.run(None, {self._input: tensor})[0]
        value = float(np.asarray(out).reshape(-1)[0])
        if not np.isfinite(value):
            raise ModelUnavailable("bad_output")
        return min(1.0, max(0.0, value))


class OnnxEmbedder(OnnxScorer):
    """An ONNX model whose output is an embedding vector, returned L2-normalised.

    Used by the near-duplicate detector: similar pictures (the same receipt re-photographed, cropped
    or re-rendered) land close together under cosine similarity.
    """

    def embed(self, img: Image.Image) -> np.ndarray:
        tensor = to_tensor(img, self.entry.size, self.entry.channels)
        out = np.asarray(self._session.run(None, {self._input: tensor})[0], dtype=np.float32)
        vec = out.reshape(-1)
        norm = float(np.linalg.norm(vec))
        if vec.size == 0 or not np.isfinite(norm) or norm == 0.0:
            raise ModelUnavailable("bad_output")
        return vec / norm
