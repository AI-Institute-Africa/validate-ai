"""Train the classical detector (numpy only) and write its model file and manifest entry.

    python -m training.detect.train_linear --data DIR --kind receipt --out MODEL_DIR

DIR is a folder made by `build_dataset` (an index.jsonl and the pictures). Steps: split by source,
standardise, add a genuine-only distance (the one-class part, cross-fitted), fit a logistic
regression, calibrate on the held-out calibration part (Platt), pick the escalation threshold at a
stated false-flag rate, and the uncertainty band by split-conformal prediction. Everything runs on
a laptop in seconds to minutes and nothing leaves the machine.

The model sees summary statistics, not the picture. It is a baseline; the deep model (train_cnn.py)
is the higher-capacity path. Numbers from either, on synthetic data, are not real-world accuracy.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.detect import stats
from app.detect.manifest import MANIFEST_NAME
from training.detect import dataset, fit

DEFAULT_LABEL = {"receipt": "forged", "doc": "forged", "face": "synthetic_face"}


def features_for(folder: Path, samples: list[dataset.Sample]) -> np.ndarray:
    """Feature vectors for `samples`, cached next to the pictures (computing them is slow)."""
    cache_path = folder / f".features-{stats.FEATURE_VERSION}.npz"
    cache: dict[str, np.ndarray] = {}
    if cache_path.is_file():
        with np.load(cache_path, allow_pickle=False) as z:
            cache = {k: z[k] for k in z.files}
    changed = False
    rows = []
    for s in samples:
        key = s.path.replace("/", "__")
        if key not in cache:
            cache[key] = stats.feature_vector(Image.open(folder / s.path))
            changed = True
        rows.append(cache[key])
    if changed:
        np.savez(cache_path, **cache)
    return np.vstack(rows) if rows else np.zeros((0, len(stats.FEATURE_NAMES)), np.float32)


def train(
    folder: Path,
    kind: str,
    out_dir: Path,
    *,
    label: str | None = None,
    max_false_flag: float = 0.05,
    alpha: float = 0.1,
    l2: float = 1.0,
    seed: int = 0,
    max_minutes: float = 30.0,
    augment: bool = True,
) -> dict:
    deadline = time.monotonic() + max_minutes * 60
    samples = [s for s in dataset.read_index(folder / "index.jsonl") if s.kind == kind]
    parts = dataset.split_by_source(samples, seed)
    tr, ca = parts["train"], parts["calib"]
    if not any(s.label == 0 for s in tr) or not any(s.label == 1 for s in tr):
        raise SystemExit("the training part needs both genuine and forged pictures")
    if augment:
        # copies that look like a forward, a resize or a re-photograph, with the same label: the
        # model must learn that a genuine receipt that was re-saved is still genuine
        tr = [*tr, *dataset.build_evasion(tr, folder, seed + 1)]
    xtr, ytr = features_for(folder, tr), np.array([s.label for s in tr], dtype=float)
    mean, std = fit.standardise_fit(xtr)
    ztr = (xtr - mean) / std
    genuine = ytr == 0

    # the one-class part: distance from genuine, measured the way a new picture will be
    d_tr = fit.cross_fitted_distance(ztr, genuine, seed=seed)
    m_mean, m_prec, m_scale = fit.fit_mahalanobis(ztr[genuine])
    w, b = fit.fit_logistic(np.hstack([ztr, d_tr[:, None]]), ytr, l2=l2, deadline=deadline)

    def logits(x: np.ndarray) -> np.ndarray:
        z = (x - mean) / std
        d = fit.distance_feature(z, m_mean, m_prec, m_scale)
        return np.hstack([z, d[:, None]]) @ w + b

    op = {"platt": (1.0, 0.0), "threshold": None, "band": None, "ece": None}
    if ca:
        xca, yca = features_for(folder, ca), np.array([s.label for s in ca], dtype=float)
        op = fit.operating_point(logits(xca), yca, max_false_flag, alpha)
    a_platt, b_platt = op["platt"]
    threshold, band = op["threshold"], op["band"]
    cal_report: dict = {
        "calibration_pictures": len(ca),
        "caught_at_threshold": op.get("caught_at_threshold"),
        "false_flag_at_threshold": op.get("false_flag_at_threshold"),
        "ece": op["ece"],
        "conformal_alpha": alpha,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"linear_{kind}.npz"
    np.savez(
        model_path,
        feature_version=np.array(stats.FEATURE_VERSION),
        mean=mean,
        std=std,
        coef=w,
        intercept=np.array(b),
        platt=np.array([a_platt, b_platt]),
        maha_mean=m_mean,
        maha_prec=m_prec,
        maha_scale=np.array(m_scale),
    )
    sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    version = f"linear-{kind}-{stats.FEATURE_VERSION}-{sha[:8]}"
    entry = {
        "name": f"linear_{kind}",
        "file": model_path.name,
        "version": version,
        "sha256": sha,
        "format": "npz-linear",
        "label": label or DEFAULT_LABEL[kind],
        "input": {"size": stats.SIZE, "channels": ["rgb"]},
        "tta": 1,
        "card": f"model-card-{kind}.md",
    }
    if threshold is not None:
        entry["threshold"] = threshold
    if band is not None:
        entry["uncertain_band"] = list(band)
    manifest_path = out_dir / MANIFEST_NAME
    manifest = (
        json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"detectors": {}}
    )
    manifest["detectors"][kind] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    top = np.argsort(-np.abs(w[:-1]))[:6]
    report = {
        "kind": kind,
        "version": version,
        "sha256": sha,
        "train_pictures": len(tr),
        "train_genuine": int(genuine.sum()),
        "train_forged": int((~genuine).sum()),
        "threshold": threshold,
        "uncertain_band": band,
        "platt": [a_platt, b_platt],
        "distance_weight": float(w[-1]),
        "top_features": [(stats.FEATURE_NAMES[i], round(float(w[i]), 3)) for i in top],
        **cal_report,
    }
    (out_dir / f"train-report-{kind}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="folder made by build_dataset")
    ap.add_argument("--kind", required=True, choices=sorted(DEFAULT_LABEL))
    ap.add_argument("--out", required=True, help="model folder (gets the .npz and manifest.json)")
    ap.add_argument("--label", help="what a high score means (default: per kind)")
    ap.add_argument("--max-false-flag", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=0.1, help="conformal miscoverage")
    ap.add_argument("--l2", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument(
        "--no-augment", action="store_true", help="do not train on evasion-style copies"
    )
    a = ap.parse_args()
    report = train(
        Path(a.data),
        a.kind,
        Path(a.out),
        label=a.label,
        max_false_flag=a.max_false_flag,
        alpha=a.alpha,
        l2=a.l2,
        seed=a.seed,
        max_minutes=a.max_minutes,
        augment=not a.no_augment,
    )
    json.dump(report, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
