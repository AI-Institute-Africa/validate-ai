"""The classical detector: forensic statistics -> logistic regression, from a small .npz file.

This is the trainable baseline that needs nothing but numpy to train and to run
(training/detect/train_linear.py). It is NOT the deep model: it sees a few dozen summary numbers,
not the picture, and it is only as good as those numbers and the data it was fitted on. It fills
the same slot as an ONNX model: same manifest entry, same hash check, same recorded `skipped` when
anything is wrong.

File contents (loaded without pickle, so a model file cannot run code):
  feature_version  must equal `stats.FEATURE_VERSION`
  mean, std        per-feature standardisation (length d)
  coef, intercept  logistic weights; length d, or d + 1 when the genuine-only distance is added
  maha_mean, maha_prec, maha_scale   optional: the one-class part (distance from genuine,
                   measured on the standardised features)
  platt            two numbers (a, b): the final probability is sigmoid(a * logit + b)
"""

from pathlib import Path

import numpy as np
from PIL import Image

from app.detect import stats
from app.detect.manifest import Entry, file_sha256
from app.detect.onnx_runtime import ModelUnavailable

_REQUIRED = ("feature_version", "mean", "std", "coef", "intercept", "platt")


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0))))


def mahalanobis(x: np.ndarray, mean: np.ndarray, prec: np.ndarray, scale: float) -> float:
    d = x.astype(np.float64) - mean
    return float(np.log1p(np.sqrt(max(float(d @ prec @ d), 0.0)) / max(scale, 1e-9)))


class LinearModel:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.mean = arrays["mean"].astype(np.float64)
        self.std = np.where(arrays["std"] < 1e-9, 1.0, arrays["std"]).astype(np.float64)
        self.coef = arrays["coef"].astype(np.float64)
        self.intercept = float(arrays["intercept"])
        self.platt = (float(arrays["platt"][0]), float(arrays["platt"][1]))
        self.one_class = "maha_mean" in arrays
        if self.one_class:
            self.m_mean = arrays["maha_mean"].astype(np.float64)
            self.m_prec = arrays["maha_prec"].astype(np.float64)
            self.m_scale = float(arrays["maha_scale"])
        d = self.mean.size
        if self.coef.size != d + (1 if self.one_class else 0):
            raise ModelUnavailable("bad_shape")

    def logit(self, x: np.ndarray) -> float:
        z = (x.astype(np.float64) - self.mean) / self.std
        if self.one_class:
            z = np.append(z, mahalanobis(z, self.m_mean, self.m_prec, self.m_scale))
        return float(z @ self.coef + self.intercept)

    def probability_of(self, x: np.ndarray) -> float:
        a, b = self.platt
        return _sigmoid(a * self.logit(x) + b)


def load(path: Path, expected_sha: str) -> LinearModel:
    if not path.is_file():
        raise ModelUnavailable("file_missing")
    if file_sha256(path) != expected_sha:
        raise ModelUnavailable("hash_mismatch")
    try:
        with np.load(path, allow_pickle=False) as z:
            arrays = {k: z[k] for k in z.files}
    except Exception as exc:  # noqa: BLE001 - a corrupt model must not stop intake
        raise ModelUnavailable("model_unreadable") from exc
    if any(k not in arrays for k in _REQUIRED):
        raise ModelUnavailable("bad_shape")
    if str(arrays["feature_version"]) != stats.FEATURE_VERSION:
        raise ModelUnavailable("feature_version_mismatch")
    if arrays["mean"].size != len(stats.FEATURE_NAMES):
        raise ModelUnavailable("bad_shape")
    return LinearModel(arrays)


class NpzScorer:
    """Same `probability(img)` contract as the ONNX scorer."""

    def __init__(self, entry: Entry):
        self.entry = entry
        self._model = load(entry.file, entry.sha256)

    def probability(self, img: Image.Image) -> float:
        p = self._model.probability_of(stats.feature_vector(img))
        if not np.isfinite(p):
            raise ModelUnavailable("bad_output")
        return min(1.0, max(0.0, p))
