"""Authenticity detectors without a database: manifest, model loader, escalation rules."""

import hashlib
import json

import pytest
from PIL import Image

from app.core.config import ConfigError, Settings, validate_for_startup
from app.detect import features, registry
from app.detect.base import DetectorResult, skipped
from app.detect.image_detector import OnnxImageDetector, tta_views
from app.detect.manifest import ManifestError, file_sha256, load_manifest
from app.detect.near_duplicate import top_matches
from app.detect.onnx_runtime import ModelUnavailable, OnnxScorer, to_tensor
from app.detect.runner import escalation_reason, safe_score, versions_from_checks
from app.policy.engine import PolicyConfig


def _write(folder, detectors, name="manifest.json"):
    (folder / name).write_text(json.dumps({"detectors": detectors}))


def _entry_json(file="receipt_forgery.onnx", sha=None, **over):
    return {
        "file": file,
        "version": "v1",
        "sha256": sha or "a" * 64,
        "label": "forged",
        **over,
    }


# --- manifest -------------------------------------------------------------------------------------


def test_absent_manifest_means_nothing_installed(tmp_path):
    assert load_manifest(tmp_path) == {}


def test_a_valid_manifest_loads(tmp_path):
    (tmp_path / "receipt_forgery.onnx").write_bytes(b"x")
    _write(
        tmp_path,
        {"receipt": _entry_json(threshold=0.7, uncertain_band=[0.4, 0.6], input={"size": 128})},
    )
    e = load_manifest(tmp_path)["receipt"]
    assert (e.kind, e.label, e.threshold, e.size) == ("receipt", "forged", 0.7, 128)
    assert e.uncertain_band == (0.4, 0.6) and e.name == "receipt_forgery"


@pytest.mark.parametrize(
    "bad",
    [
        {"receipt": _entry_json(sha="zz")},  # not hex
        {"receipt": _entry_json(label="evil")},  # not a known meaning
        {"receipt": _entry_json(threshold=0)},
        {"receipt": _entry_json(threshold=1.5)},
        {"receipt": _entry_json(uncertain_band=[0.7, 0.3])},
        {"receipt": _entry_json(file="../outside.onnx")},  # escapes the folder
        {"receipt": _entry_json(file="/etc/passwd")},
        {"banana": _entry_json()},  # unknown kind
        {"receipt": {"file": "x.onnx"}},  # missing fields
    ],
)
def test_an_unsafe_or_incomplete_manifest_is_refused(tmp_path, bad):
    _write(tmp_path, bad)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_garbage_manifest_is_refused(tmp_path):
    (tmp_path / "manifest.json").write_text("{not json")
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


# --- loader ---------------------------------------------------------------------------------------


def test_a_missing_file_or_wrong_hash_is_never_loaded(tmp_path):
    _write(tmp_path, {"receipt": _entry_json()})
    with pytest.raises(ModelUnavailable, match="file_missing"):
        OnnxScorer(load_manifest(tmp_path)["receipt"])
    (tmp_path / "receipt_forgery.onnx").write_bytes(b"not the model that was published")
    with pytest.raises(ModelUnavailable, match="hash_mismatch"):
        OnnxScorer(load_manifest(tmp_path)["receipt"])


def test_input_tensor_has_the_declared_shape_and_range():
    t = to_tensor(Image.new("RGB", (300, 120), (200, 10, 30)), 64, ("rgb",))
    assert t.shape == (1, 3, 64, 64) and t.dtype.name == "float32"
    assert 0.0 <= float(t.min()) and float(t.max()) <= 1.0
    with pytest.raises(ModelUnavailable, match="unknown_channel"):
        to_tensor(Image.new("RGB", (10, 10)), 8, ("rgb", "hologram"))


def test_registry_reports_why_a_detector_cannot_run(tmp_path):
    registry.reset()
    blob = b"pretend model"
    (tmp_path / "receipt_forgery.onnx").write_bytes(blob)
    _write(
        tmp_path,
        {
            "receipt": _entry_json(sha=hashlib.sha256(b"something else").hexdigest()),
            "face": _entry_json(file="face.onnx", label="deepfake"),
        },
    )
    s = Settings(_env_file=None, detect_mode="shadow", detect_model_dir=str(tmp_path))
    dets = registry.build_detectors(s)
    assert set(dets) == {"receipt", "doc", "face", "duplicate", "text"}
    assert dets["receipt"].score(Image.new("RGB", (8, 8))).skipped == "hash_mismatch"
    assert dets["doc"].score(None).skipped == "no_model"
    assert dets["face"].score(None).skipped == "file_missing"  # the manifest names it; no file
    info = {r["kind"]: r for r in registry.describe(s)["detectors"]}  # type: ignore[union-attr]
    assert info["receipt"]["state"] == "skipped" and info["receipt"]["reason"] == "hash_mismatch"
    assert info["doc"]["reason"] == "no_model"
    registry.reset()


def test_off_means_off(tmp_path):
    registry.reset()
    s = Settings(_env_file=None, detect_mode="off", detect_model_dir=str(tmp_path))
    assert registry.build_detectors(s) == {}
    assert all(r["state"] == "off" for r in registry.describe(s)["detectors"])  # type: ignore[union-attr]


def test_a_broken_manifest_skips_every_detector(tmp_path):
    registry.reset()
    (tmp_path / "manifest.json").write_text("{nope")
    s = Settings(_env_file=None, detect_mode="shadow", detect_model_dir=str(tmp_path))
    assert {d.score(None).skipped for d in registry.build_detectors(s).values()} == {
        "manifest_invalid"
    }
    registry.reset()


def test_a_real_onnx_model_scores_and_is_hash_checked(tmp_path):
    onnx = pytest.importorskip("onnx")
    helper, tp = onnx.helper, onnx.TensorProto
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["x"], ["m"], axes=[1, 2, 3], keepdims=0),
            helper.make_node("Sigmoid", ["m"], ["y"]),
        ],
        "tiny",
        [helper.make_tensor_value_info("x", tp.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info("y", tp.FLOAT, [1])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    path = tmp_path / "receipt_forgery.onnx"
    onnx.save(model, str(path))
    registry.reset()
    _write(
        tmp_path,
        {
            "receipt": _entry_json(
                sha=file_sha256(path), input={"size": 32}, uncertain_band=[0.6, 0.8]
            )
        },
    )
    s = Settings(_env_file=None, detect_mode="shadow", detect_model_dir=str(tmp_path))
    r = registry.build_detectors(s)["receipt"].score(Image.new("RGB", (50, 50), (255, 255, 255)))
    assert r.skipped is None and r.label == "forged"
    assert r.score is not None and 0.7 < r.score < 0.75  # sigmoid(1.0)
    assert r.uncertain and r.model_version == "v1" and r.latency_ms is not None
    registry.reset()


# --- what a score may do --------------------------------------------------------------------------


def _res(**kw):
    base = dict(kind="receipt", detector="d", score=0.95, label="forged")
    base.update(kw)
    return DetectorResult(**base)


def test_only_a_confident_high_score_in_escalate_mode_escalates():
    assert escalation_reason(_res(), 0.7, "escalate") == "FORGED_POP_SUSPECTED"
    assert escalation_reason(_res(label="ai_generated"), 0.7, "escalate") == (
        "AI_GENERATED_SUSPECTED"
    )
    assert escalation_reason(_res(kind="face", label="deepfake"), 0.7, "escalate") == (
        "DEEPFAKE_SUSPECTED"
    )
    # shadow records only
    assert escalation_reason(_res(), 0.7, "shadow") is None
    assert escalation_reason(_res(), 0.7, "off") is None
    # below the threshold, no threshold, uncertain, skipped, no score: nothing
    assert escalation_reason(_res(score=0.5), 0.7, "escalate") is None
    assert escalation_reason(_res(), None, "escalate") is None
    assert escalation_reason(_res(uncertain=True), 0.7, "escalate") is None
    assert escalation_reason(skipped("receipt", "d", "no_model"), 0.7, "escalate") is None
    assert escalation_reason(_res(score=None), 0.7, "escalate") is None
    # a label the engine does not know is never turned into a reason
    assert escalation_reason(_res(label="near_duplicate"), 0.7, "escalate") is None


def test_a_detector_that_raises_is_recorded_as_skipped():
    class Boom:
        kind, name = "receipt", "boom"

        def score(self, subject):
            raise RuntimeError("bad tensor")

    r = safe_score(Boom(), None)
    assert r.skipped == "error:RuntimeError" and r.score is None


def test_versions_come_only_from_detectors_that_scored():
    checks = [
        {"check": "tamper"},
        {
            "check": "authenticity",
            "results": [
                {"detector": "a", "model_version": "v2", "model_sha256": "f" * 64, "skipped": None},
                {"detector": "b", "model_version": "v1", "model_sha256": "e" * 64, "skipped": "x"},
                {"detector": "c", "model_version": None, "skipped": "no_model"},
            ],
        },
    ]
    assert versions_from_checks(checks) == {"a": "v2@ffffffffffff"}


# --- policy and settings --------------------------------------------------------------------------


def test_policy_accepts_known_kinds_and_sane_thresholds():
    c = PolicyConfig()
    assert set(c.detect_enabled_kinds) == {"receipt", "doc", "face", "duplicate", "text"}
    assert c.detect_thresholds == {}
    ok = PolicyConfig(detect_enabled_kinds=["receipt"], detect_thresholds={"receipt": 0.8})
    assert ok.detect_thresholds["receipt"] == 0.8
    for bad in (
        dict(detect_enabled_kinds=["banana"]),
        dict(detect_thresholds={"banana": 0.5}),
        dict(detect_thresholds={"receipt": 0}),
        dict(detect_thresholds={"receipt": 1.2}),
    ):
        with pytest.raises(ValueError):
            PolicyConfig(**bad)


def test_production_refuses_a_detector_folder_that_is_a_url():
    base = dict(
        env="prod",
        jwt_secret="x" * 40,
        clamav_host="clamav",
        pipeline_mode="celery",
        vlm_backend="ollama",
        kyc_face_backend="onnx",
        ollama_url="http://ollama:11434",
        data_region="ZA-test",
    )
    validate_for_startup(Settings(_env_file=None, **base))
    with pytest.raises(ConfigError, match="POPS_DETECT_MODEL_DIR"):
        validate_for_startup(
            Settings(_env_file=None, detect_model_dir="https://models.example.com/x", **base)
        )


# --- near-duplicate search ------------------------------------------------------------------------


def test_top_matches_ranks_by_cosine_and_drops_unrelated_rows():
    import uuid

    import numpy as np

    ids = [uuid.uuid4() for _ in range(3)]
    matrix = np.asarray([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]], dtype=np.float32)
    got = top_matches(matrix, ids, np.asarray([1.0, 0.0], dtype=np.float32))
    assert [g[0] for g in got] == [ids[0], ids[1]]  # the orthogonal row is below the floor
    assert got[0][1] == 1.0 and abs(got[1][1] - 0.8) < 1e-6
    assert top_matches(np.zeros((0, 2), dtype=np.float32), [], np.asarray([1.0, 0.0])) == []


# --- forensic channels ----------------------------------------------------------------------------


def _noise_image(seed=0, size=96):
    import numpy as np

    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (size, size, 3), dtype=np.uint8))


@pytest.mark.parametrize("fn", [features.noise_residual, features.fft_spectrum, features.ela_map])
def test_each_forensic_channel_is_a_deterministic_plane_in_range(fn):
    img = _noise_image()
    a, b = fn(img, 64), fn(img, 64)
    assert a.shape == (64, 64) and a.dtype.name == "float32"
    assert float(a.min()) >= 0.0 and float(a.max()) <= 1.0
    assert (a == b).all()


def test_a_flat_picture_has_no_noise_residual_but_noise_has_plenty():
    import numpy as np

    flat = features.noise_residual(Image.new("RGB", (96, 96), (120, 120, 120)), 64)
    noisy = features.noise_residual(_noise_image(), 64)
    assert float(np.abs(flat - 0.5).max()) < 1e-6  # centred on 0.5 with no signal
    assert float(np.abs(noisy - 0.5).mean()) > 0.1


def test_a_periodic_pattern_leaves_a_spectral_peak_away_from_the_centre():
    import numpy as np

    xs = np.arange(128)
    stripes = (np.sin(xs * 2 * np.pi / 4)[None, :] * 100 + 128).repeat(128, axis=0)
    img = Image.fromarray(stripes.astype(np.uint8)).convert("RGB")
    spec = features.fft_spectrum(img, 128)
    spec[60:68, 60:68] = 0  # ignore the centre
    assert float(spec.max()) > 0.5


def test_six_channel_input_for_a_forensic_model():
    t = to_tensor(_noise_image(), 48, ("rgb", "noise", "fft", "ela"))
    assert t.shape == (1, 6, 48, 48) and t.dtype.name == "float32"


# --- test-time augmentation -----------------------------------------------------------------------


class _Seq:
    def __init__(self, values):
        self.values, self.calls = list(values), 0

    def probability(self, img):
        v = self.values[self.calls % len(self.values)]
        self.calls += 1
        return v


def _entry(tta=1):
    from pathlib import Path

    from app.detect.manifest import Entry

    return Entry(
        kind="receipt",
        name="r",
        file=Path("x"),
        version="v1",
        sha256="a" * 64,
        label="forged",
        tta=tta,
    )


def test_tta_makes_the_asked_number_of_views_of_the_same_size():
    img = Image.new("RGB", (120, 90), (255, 255, 255))
    for n in (1, 2, 3, 5):
        views = tta_views(img, n)
        assert len(views) == n and all(v.size == img.size for v in views)
    assert len(tta_views(Image.new("RGB", (10, 10)), 5)) == 1  # too small to vary safely


def test_the_detector_averages_over_its_views_and_says_how_many():
    d = OnnxImageDetector(_entry(tta=3), _Seq([0.9, 0.6, 0.3]))
    r = d.score(Image.new("RGB", (120, 90)))
    assert r.score == pytest.approx(0.6) and r.signals == ["tta:3"]
    one = OnnxImageDetector(_entry(tta=1), _Seq([0.8])).score(Image.new("RGB", (120, 90)))
    assert one.score == pytest.approx(0.8) and one.signals == []


def test_tta_must_be_between_one_and_five(tmp_path):
    (tmp_path / "m.onnx").write_bytes(b"x")
    _write(tmp_path, {"receipt": _entry_json(file="m.onnx", tta=9)})
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_the_registry_knows_the_face_kind(tmp_path):
    registry.reset()
    (tmp_path / "face.onnx").write_bytes(b"not the model")
    _write(
        tmp_path,
        {"face": _entry_json(file="face.onnx", label="deepfake")},
    )
    s = Settings(_env_file=None, detect_mode="shadow", detect_model_dir=str(tmp_path))
    r = registry.build_detectors(s)["face"].score(Image.new("RGB", (8, 8)))
    assert r.skipped == "hash_mismatch"  # it tried to load it, and the hash did not match
    registry.reset()
