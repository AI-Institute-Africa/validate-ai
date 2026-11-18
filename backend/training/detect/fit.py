"""The numerical core of the classical detector, in plain numpy (no scikit-learn, no torch).

Logistic regression by Newton's method, a genuine-only distance (the one-class part), Platt
calibration and a conformal uncertainty band. Small and exact enough to test against known answers.
"""

import time
from collections.abc import Sequence

import numpy as np


def sigmoid(z: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def standardise_fit(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    return mean, np.where(std < 1e-9, 1.0, std)


def _loss(xb: np.ndarray, y: np.ndarray, w: np.ndarray, l2: float, mask: np.ndarray) -> float:
    z = xb @ w
    # numerically stable log-loss: log(1 + e^z) - y z
    return float(np.sum(np.logaddexp(0.0, z) - y * z) + 0.5 * l2 * np.sum(mask * w * w))


def fit_logistic(
    x: np.ndarray,
    y: np.ndarray,
    l2: float = 1.0,
    max_iter: int = 100,
    tol: float = 1e-7,
    deadline: float | None = None,
) -> tuple[np.ndarray, float]:
    """L2-regularised logistic regression (the intercept is not penalised). Returns (weights, bias).

    Newton's method with a backtracking line search, so separable data cannot make it diverge.
    `deadline` is a `time.monotonic()` value after which it stops with what it has.
    """
    n, d = x.shape
    xb = np.hstack([x, np.ones((n, 1))])
    mask = np.ones(d + 1)
    mask[-1] = 0.0
    w = np.zeros(d + 1)
    for _ in range(max_iter):
        p = sigmoid(xb @ w)
        grad = xb.T @ (p - y) + l2 * mask * w
        weight = np.clip(p * (1 - p), 1e-6, None)
        hess = xb.T @ (xb * weight[:, None]) + l2 * np.diag(mask) + 1e-9 * np.eye(d + 1)
        step = np.linalg.solve(hess, grad)
        base = _loss(xb, y, w, l2, mask)
        t = 1.0
        while t > 1e-4 and _loss(xb, y, w - t * step, l2, mask) > base + 1e-12:
            t *= 0.5
        w = w - t * step
        if float(np.max(np.abs(t * step))) < tol:
            break
        if deadline is not None and time.monotonic() > deadline:
            break
    return w[:-1], float(w[-1])


def fit_platt(logits: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Calibrate raw scores on held-out data: p = sigmoid(a * logit + b)."""
    w, b = fit_logistic(logits.reshape(-1, 1), y, l2=1e-3)
    return float(w[0]), b


def fit_mahalanobis(
    genuine: np.ndarray, shrink: float = 0.1
) -> tuple[np.ndarray, np.ndarray, float]:
    """(mean, precision matrix, scale) of genuine examples. The covariance is shrunk toward a
    scaled identity so a small sample cannot make it singular. `scale` is the median distance."""
    mean = genuine.mean(axis=0)
    cov = np.cov(genuine.T) if genuine.shape[0] > 1 else np.eye(genuine.shape[1])
    d = cov.shape[0]
    cov = (1 - shrink) * cov + shrink * (np.trace(cov) / d) * np.eye(d)
    prec = np.linalg.pinv(cov)
    diff = genuine - mean
    dist = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", diff, prec, diff), 0.0))
    return mean, prec, float(max(np.median(dist), 1e-9))


def distance_feature(x: np.ndarray, mean: np.ndarray, prec: np.ndarray, scale: float) -> np.ndarray:
    diff = x - mean
    dist = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", diff, prec, diff), 0.0))
    return np.log1p(dist / scale)


def cross_fitted_distance(
    x: np.ndarray, is_genuine: np.ndarray, folds: int = 4, seed: int = 0
) -> np.ndarray:
    """The genuine-distance feature for training rows, without flattering the training data.

    A genuine row's distance is measured from a model fitted on the OTHER genuine folds, so it
    looks the way a new genuine picture will at serving time. Forged rows use a model fitted on
    all genuine rows (they were never in it).
    """
    out = np.zeros(len(x))
    gi = np.flatnonzero(is_genuine)
    rng = np.random.default_rng(seed)
    order = rng.permutation(gi)
    parts = np.array_split(order, max(2, min(folds, len(order))))
    for part in parts:
        rest = np.setdiff1d(gi, part)
        m, p, s = fit_mahalanobis(x[rest])
        out[part] = distance_feature(x[part], m, p, s)
    m, p, s = fit_mahalanobis(x[gi])
    fi = np.flatnonzero(~is_genuine)
    out[fi] = distance_feature(x[fi], m, p, s)
    return out


def conformal_band(
    probs: Sequence[float], labels: Sequence[int], alpha: float = 0.1
) -> tuple[float, float] | None:
    """The band of scores where the model should say "cannot tell".

    Split-conformal for two classes: the non-conformity of an example is 1 - (probability of its
    true class). `q` is the (1 - alpha) quantile over the calibration set. A new score p is
    uncertain when both classes stay in the prediction set, which is exactly 1 - q <= p <= q. If q
    is at most 0.5 the model is confident everywhere at this coverage, and there is no band.
    """
    p = np.asarray(probs, dtype=np.float64)
    y = np.asarray(labels)
    if p.size == 0:
        return None
    score = np.where(y == 1, 1.0 - p, p)
    k = int(np.ceil((p.size + 1) * (1 - alpha)))
    q = float(np.sort(score)[min(k, p.size) - 1])
    if q <= 0.5:
        return None
    return round(1.0 - q, 6), round(q, 6)


def operating_point(
    raw_logits: np.ndarray, y: np.ndarray, max_false_flag: float = 0.05, alpha: float = 0.1
) -> dict:
    """Everything the manifest needs, from a model's raw scores on the CALIBRATION part:

    Platt calibration (a, b), the escalation threshold at the stated false-flag rate on genuine
    pictures (None if it cannot be reached), the conformal uncertainty band and the calibration
    error.
    Both trainers call this, so they behave the same way.
    """
    from app.kyc import calibration as cal

    out: dict = {
        "platt": (1.0, 0.0),
        "threshold": None,
        "band": None,
        "caught_at_threshold": None,
        "false_flag_at_threshold": None,
        "ece": None,
    }
    if raw_logits.size == 0 or len(set(y.tolist())) < 2:
        return out
    a, b = fit_platt(raw_logits, y)
    p = np.asarray(sigmoid(a * raw_logits + b))
    picked = cal.threshold_for_false_flags(
        [float(v) for v in p[y == 1]], [float(v) for v in p[y == 0]], max_false_flag
    )
    out["platt"] = (a, b)
    if picked is not None and picked[0] <= 1.0:
        out["threshold"] = round(float(picked[0]), 6)
        out["caught_at_threshold"], out["false_flag_at_threshold"] = picked[1], picked[2]
    out["band"] = conformal_band(p.tolist(), y.astype(int).tolist(), alpha)
    out["ece"] = round(expected_calibration_error(p, y), 4)
    return out


def expected_calibration_error(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """How far stated probabilities are from observed frequencies, averaged over bins."""
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            total += m.mean() * abs(float(p[m].mean()) - float(y[m].mean()))
    return float(total)
