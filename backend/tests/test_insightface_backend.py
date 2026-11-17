"""The InsightFace-style matcher: faces are aligned onto the ArcFace template before embedding.

No model weights are needed here: the alignment maths and the fail-closed behaviour are what we can
check, and what decides whether matching is as good as the model allows.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.kyc.cv import face
from app.kyc.cv.face import ARCFACE_TEMPLATE, FaceUnavailable, align_face


def _canonical() -> Image.Image:
    """A 112 px 'face': a dot of a different colour at each template point."""
    img = Image.new("RGB", (112, 112), "white")
    d = ImageDraw.Draw(img)
    colours = ["red", "green", "blue", "magenta", "orange"]
    for (x, y), c in zip(ARCFACE_TEMPLATE, colours, strict=True):
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c)
    return img


def _scene(angle_deg: float, scale: float, shift: tuple[float, float]):
    """The canonical face pasted into a larger photo, rotated, shrunk and moved. Returns the photo
    and where its five landmarks ended up (what a detector would report)."""
    import cv2

    canvas = np.full((480, 640, 3), 255, np.uint8)
    base = np.asarray(_canonical())
    m = cv2.getRotationMatrix2D((56, 56), angle_deg, scale)
    m[:, 2] += shift
    warped = cv2.warpAffine(base, m, (640, 480), borderValue=(255, 255, 255))
    pts = np.hstack([ARCFACE_TEMPLATE, np.ones((5, 1), np.float32)]) @ m.T
    del canvas
    return Image.fromarray(warped), pts.astype(np.float32)


def test_a_face_that_is_already_aligned_is_left_alone():
    out = align_face(_canonical(), ARCFACE_TEMPLATE)
    assert np.abs(np.asarray(out, float) - np.asarray(_canonical(), float)).mean() < 2.0


@pytest.mark.parametrize(
    ("angle", "scale", "shift"),
    [(0, 1.0, (200, 100)), (20, 0.6, (300, 150)), (-25, 1.8, (100, 60)), (8, 0.4, (500, 300))],
)
def test_a_turned_shrunk_or_moved_face_is_brought_back_to_the_template(angle, scale, shift):
    photo, landmarks = _scene(angle, scale, shift)
    aligned = np.asarray(align_face(photo, landmarks), float)
    # each landmark colour is back where the template says it should be
    ref = np.asarray(_canonical(), float)
    assert np.abs(aligned - ref).mean() < 12.0, (angle, scale, shift)
    for (x, y), colour in zip(
        ARCFACE_TEMPLATE, [(255, 0, 0), (0, 128, 0), (0, 0, 255)], strict=False
    ):
        patch = aligned[int(y) - 1 : int(y) + 2, int(x) - 1 : int(x) + 2].reshape(-1, 3).mean(0)
        assert np.abs(patch - colour).max() < 90, ((x, y), patch)


def test_the_embedding_input_has_the_size_the_model_expects(monkeypatch):
    photo, landmarks = _scene(10, 0.7, (250, 120))
    assert align_face(photo, landmarks, side=112).size == (112, 112)
    assert align_face(photo, landmarks, side=160).size == (
        160,
        160,
    )  # other model sizes scale along


class _Detector:
    def __init__(self, yunet: bool, landmarks):
        self.yunet, self._landmarks = yunet, landmarks

    def landmarks(self, img):
        if not self.yunet:
            raise FaceUnavailable("needs YuNet")
        return [((0, 0, 10, 10), self._landmarks)] if self._landmarks is not None else []


def _stub_init(detector):
    def init(self):
        self.detector, self.side, self.version = detector, 112, "onnx:stub.onnx"

    return init


def test_without_yunet_landmarks_the_backend_refuses_rather_than_matching_worse(monkeypatch):
    monkeypatch.setattr(face.OnnxFaceMatcher, "__init__", _stub_init(_Detector(False, None)))
    with pytest.raises(FaceUnavailable, match="YuNet"):
        face.InsightFaceMatcher()


def test_faces_are_returned_aligned_and_a_missing_face_is_reported(monkeypatch):
    photo, landmarks = _scene(15, 0.8, (260, 140))
    monkeypatch.setattr(face.OnnxFaceMatcher, "__init__", _stub_init(_Detector(True, landmarks)))
    m = face.InsightFaceMatcher()
    assert m.version.startswith("insightface:")
    aligned = m.selfie_faces(photo)
    assert len(aligned) == 1 and aligned[0].size == (112, 112)
    assert m.id_portrait(photo).size == (112, 112)
    monkeypatch.setattr(face.OnnxFaceMatcher, "__init__", _stub_init(_Detector(True, None)))
    empty = face.InsightFaceMatcher()
    assert empty.id_portrait(photo) is None and empty.selfie_faces(photo) == []


def test_the_backend_is_selectable_and_nothing_is_bundled(monkeypatch):
    monkeypatch.setattr(get_settings(), "kyc_face_backend", "insightface")
    monkeypatch.setattr(get_settings(), "kyc_face_model_path", "/nonexistent/w600k_r50.onnx")
    with pytest.raises(FaceUnavailable):  # no weights on this machine: fail closed
        face.build_matcher()
