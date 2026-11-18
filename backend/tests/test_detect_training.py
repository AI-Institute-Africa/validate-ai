"""The classical detector's training loop, end to end and piece by piece (numpy only)."""

import hashlib
import io
import random

import numpy as np
import pytest
from PIL import Image

from app.core.config import Settings
from app.detect import registry, stats
from app.detect.linear_model import NpzScorer, load
from app.detect.manifest import file_sha256, load_manifest
from app.detect.onnx_runtime import ModelUnavailable
from app.kyc import calibration as cal
from training.detect import dataset, demo_loop, fit, synth
from training.detect.evaluate import auc_np
from training.detect.train_linear import features_for


def _noise(seed=0, size=96):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (size, size, 3), dtype=np.uint8))


# --- the feature vector ----------------------------------------------------------------------


def test_feature_vector_is_the_documented_shape_finite_and_repeatable():
    img = _noise(1, 128)
    v = stats.feature_vector(img)
    assert v.shape == (len(stats.FEATURE_NAMES),) and v.dtype == np.float32
    assert np.isfinite(v).all() and (stats.feature_vector(img) == v).all()
    assert len(set(stats.FEATURE_NAMES)) == len(stats.FEATURE_NAMES)  # every name is unique


def test_a_tiny_or_flat_picture_still_gives_finite_features():
    for img in (Image.new("RGB", (20, 20), (9, 9, 9)), Image.new("RGB", (300, 40), (200, 0, 0))):
        assert np.isfinite(stats.feature_vector(img)).all()


def test_the_jpeg_block_grid_feature_responds_to_compression():
    rng = np.random.default_rng(2)  # smooth enough that JPEG leaves a visible block grid
    base = Image.fromarray(rng.normal(128, 30, (256, 256, 3)).clip(0, 255).astype(np.uint8))
    buf = io.BytesIO()
    base.save(buf, "JPEG", quality=30)
    jpeg = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    i = stats.FEATURE_NAMES.index("jpeg_block_h")
    assert stats.feature_vector(jpeg)[i] > stats.feature_vector(base)[i] + 0.3


# --- the generators --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(synth.GENERATORS))
def test_every_generator_changes_the_picture_and_keeps_its_size(name):
    base, donor = _noise(3, 160), _noise(4, 160)
    out = synth.forge(name, base, donor, random.Random(5))
    assert out.size == base.size
    assert np.abs(np.asarray(out, float) - np.asarray(synth.as_jpeg(base), float)).max() > 0


def test_each_kind_lists_only_generators_that_exist():
    for names in synth.KIND_GENERATORS.values():
        assert set(names) <= set(synth.GENERATORS)


# --- the dataset and its split ---------------------------------------------------------------


def _samples(n_sources=10):
    out = []
    for i in range(n_sources):
        src = f"s{i}"
        out.append(dataset.Sample(f"{src}-g.jpg", 0, "genuine", src, "g", "receipt"))
        out += [
            dataset.Sample(f"{src}-{k}.jpg", 1, "double_jpeg", src, "g", "receipt")
            for k in range(3)
        ]
    return out


def test_the_split_is_by_source_so_a_forgery_never_sits_apart_from_its_original():
    parts = dataset.split_by_source(_samples(), seed=3)
    where = {}
    for name, rows in parts.items():
        for s in rows:
            assert where.setdefault(s.source, name) == name  # one part per source
    assert all(parts[k] for k in ("train", "calib", "test"))
    assert sum(len(v) for v in parts.values()) == 40


def test_the_split_is_reproducible_and_changes_with_the_seed():
    a = dataset.split_by_source(_samples(), seed=1)
    b = dataset.split_by_source(_samples(), seed=1)
    c = dataset.split_by_source(_samples(), seed=2)
    names = lambda p: {s.source for s in p["test"]}  # noqa: E731
    assert names(a) == names(b) and names(a) != names(c)


def test_evasion_variants_are_four_pictures_of_sensible_size():
    variants = dataset.evasion_variants(_noise(6, 200), random.Random(0))
    assert [t for t, _ in variants] == [
        "recompress_q55",
        "rescale_70",
        "added_noise",
        "screenshot_of_screenshot",
    ]
    assert all(v.width > 100 for _, v in variants)


# --- the numerical core ----------------------------------------------------------------------


def test_logistic_regression_recovers_known_weights():
    rng = np.random.default_rng(0)
    true_w = np.array([1.5, -2.0, 0.0, 0.7])
    x = rng.normal(size=(5000, 4))
    y = (rng.random(5000) < fit.sigmoid(x @ true_w + 0.3)).astype(float)
    w, b = fit.fit_logistic(x, y, l2=1e-3)
    assert np.allclose(w, true_w, atol=0.15) and abs(b - 0.3) < 0.15


def test_perfectly_separable_data_does_not_blow_up():
    rng = np.random.default_rng(1)
    x = np.vstack([rng.normal(-3, 0.3, (50, 2)), rng.normal(3, 0.3, (50, 2))])
    y = np.r_[np.zeros(50), np.ones(50)]
    w, b = fit.fit_logistic(x, y)
    assert np.isfinite(w).all() and np.isfinite(b) and (w > 0).all()


def test_platt_scaling_shrinks_an_overconfident_score():
    rng = np.random.default_rng(2)
    y = (rng.random(3000) < 0.5).astype(float)
    logits = (2 * y - 1) * 1.0 + rng.normal(0, 1.5, 3000)  # noisy
    a, b = fit.fit_platt(logits * 5.0, y)  # a deliberately overconfident scale
    assert 0 < a < 0.5 and abs(b) < 0.3


def test_the_cross_fitted_distance_does_not_flatter_the_training_genuine_rows():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(60, 20))
    is_genuine = np.ones(60, dtype=bool)
    in_sample = fit.distance_feature(x, *fit.fit_mahalanobis(x))
    honest = fit.cross_fitted_distance(x, is_genuine)
    assert honest.mean() > in_sample.mean()  # in-sample distances are optimistic


def test_forged_rows_are_farther_from_genuine_than_genuine_rows():
    rng = np.random.default_rng(4)
    genuine, forged = rng.normal(0, 1, (80, 10)), rng.normal(2.5, 1, (30, 10))
    x = np.vstack([genuine, forged])
    d = fit.cross_fitted_distance(x, np.r_[np.ones(80, bool), np.zeros(30, bool)])
    assert d[80:].mean() > d[:80].mean() + 0.5


def test_conformal_band_covers_the_true_class_at_the_stated_rate():
    rng = np.random.default_rng(5)

    def draw(n):
        y = (rng.random(n) < 0.5).astype(int)
        p = np.clip(0.5 + (2 * y - 1) * rng.normal(0.1, 0.25, n), 0.001, 0.999)  # unsure at times
        return p, y

    p_cal, y_cal = draw(2000)
    band = fit.conformal_band(p_cal, y_cal, alpha=0.1)
    assert band is not None and 0 < band[0] < 0.5 < band[1] < 1
    p, y = draw(5000)
    q = band[1]
    in_set = np.where(y == 1, 1 - p <= q, p <= q)  # the true class stays in the prediction set
    assert in_set.mean() >= 0.88  # 90% target, with sampling noise


def test_a_confident_model_has_no_uncertain_band():
    p = np.r_[np.full(50, 0.99), np.full(50, 0.01)]
    y = np.r_[np.ones(50), np.zeros(50)].astype(int)
    assert fit.conformal_band(p, y, alpha=0.1) is None


def test_auc_by_ranks_matches_the_reference_implementation_including_ties():
    rng = np.random.default_rng(6)
    pos, neg = rng.integers(0, 6, 40).astype(float), rng.integers(0, 6, 50).astype(float)
    assert auc_np(pos, neg) == pytest.approx(cal.auc(pos.tolist(), neg.tolist()))


# --- the model file's failure modes ----------------------------------------------------------


def _write_model(path, **over):
    d = len(stats.FEATURE_NAMES)
    arrays = dict(
        feature_version=np.array(stats.FEATURE_VERSION),
        mean=np.zeros(d),
        std=np.ones(d),
        coef=np.zeros(d),
        intercept=np.array(0.0),
        platt=np.array([1.0, 0.0]),
    )
    arrays.update(over)
    np.savez(path, **arrays)
    return file_sha256(path)


def test_a_valid_model_file_loads_and_scores():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "m.npz"
        sha = _write_model(p)
        assert load(p, sha).probability_of(np.zeros(len(stats.FEATURE_NAMES))) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"feature_version": np.array("stats-v0")}, "feature_version_mismatch"),
        ({"mean": np.zeros(3)}, "bad_shape"),
        ({"coef": np.zeros(5)}, "bad_shape"),
    ],
)
def test_a_model_that_does_not_fit_the_features_is_never_loaded(tmp_path, over, reason):
    p = tmp_path / "m.npz"
    sha = _write_model(p, **over)
    with pytest.raises(ModelUnavailable, match=reason):
        load(p, sha)


def test_missing_wrong_hash_and_garbage_files_are_refused(tmp_path):
    with pytest.raises(ModelUnavailable, match="file_missing"):
        load(tmp_path / "nope.npz", "a" * 64)
    p = tmp_path / "m.npz"
    _write_model(p)
    with pytest.raises(ModelUnavailable, match="hash_mismatch"):
        load(p, "b" * 64)
    junk = tmp_path / "junk.npz"
    junk.write_bytes(b"this is not a zip")
    with pytest.raises(ModelUnavailable, match="model_unreadable"):
        load(junk, hashlib.sha256(b"this is not a zip").hexdigest())


def test_a_pickled_model_file_is_refused_not_executed(tmp_path):
    p = tmp_path / "evil.npz"
    np.savez(p, feature_version=np.array([object()], dtype=object))  # needs pickle to read
    with pytest.raises(ModelUnavailable):
        load(p, file_sha256(p))


# --- the whole loop, in miniature ------------------------------------------------------------


def test_build_train_evaluate_install_and_score_in_one_go(tmp_path):
    res = demo_loop.run("receipt", tmp_path, n=18, seed=1, scale=0.3)
    models = tmp_path / "models"
    entry = load_manifest(models)["receipt"]
    assert entry.format == "npz-linear" and entry.label == "forged"
    assert entry.version == res["train"]["version"] and entry.sha256 == file_sha256(entry.file)
    assert entry.threshold is None or 0 < entry.threshold <= 1
    # the evaluation says it is synthetic and compares with the hand-written check
    assert "SYNTHETIC DATA ONLY" in res["report"] and "tamper check" in res["report"]
    assert 0.0 <= res["evaluation"]["test"]["auc"] <= 1.0
    assert (models / "model-card-receipt.md").read_text().startswith("# Model card")
    # the server loads it through the same registry as any other detector, and it scores
    registry.reset()
    s = Settings(_env_file=None, detect_mode="shadow", detect_model_dir=str(models))
    det = registry.build_detectors(s)["receipt"]
    r = det.score(Image.open(next((tmp_path / "data").glob("*genuine.jpg"))))
    assert r.skipped is None and r.label == "forged" and 0.0 <= r.score <= 1.0
    assert r.model_version == entry.version and r.model_sha256 == entry.sha256
    registry.reset()


def test_a_trained_model_with_a_changed_byte_is_not_loaded(tmp_path):
    demo_loop.run("receipt", tmp_path, n=18, seed=2, scale=0.3)
    entry = load_manifest(tmp_path / "models")["receipt"]
    with entry.file.open("ab") as f:
        f.write(b"\0")  # tampered after training
    with pytest.raises(ModelUnavailable, match="hash_mismatch"):
        NpzScorer(entry)


def test_features_are_cached_next_to_the_pictures(tmp_path):
    images, groups = [_noise(i, 64) for i in range(6)], ["a"] * 6
    samples = dataset.build("receipt", images, tmp_path, forged_per_source=1, groups=groups)
    first = features_for(tmp_path, samples)
    assert (tmp_path / f".features-{stats.FEATURE_VERSION}.npz").is_file()
    assert (features_for(tmp_path, samples) == first).all()
