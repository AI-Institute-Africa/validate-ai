"""Synthetic forgeries and re-captures for training and evaluating the detectors.

Every generator takes a genuine picture (and a donor picture, for the ones that paste) and returns a
manipulated copy. They stand in for what real fraud looks like until reviewers have confirmed real
fakes: a model trained on these learns THESE generators. Results on them are never real-world
accuracy; `evaluate.py` says so on every report.

The four basic edits (paste, retyped text, inpaint, recompressed region) are the ones in
tools/eval/tamper_eval.py; the rest are added here: double JPEG, resampling artefacts, a photo of a
screen, a print-and-scan, a noisy patch, and two face manipulations.
"""

import io
import random
import sys
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

_EVAL = Path(__file__).resolve().parents[2] / "tools" / "eval"
sys.path.insert(0, str(_EVAL))
import tamper_eval as te  # noqa: E402

Forger = Callable[[Image.Image, Image.Image, random.Random], Image.Image]


def as_jpeg(img: Image.Image, quality: int = 85) -> Image.Image:
    """Pictures arrive compressed. Every picture, genuine or forged, takes the same last save, so a
    detector cannot win just by spotting 'was saved as JPEG'."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _region(img: Image.Image, rnd: random.Random, frac=(0.25, 0.15)) -> tuple[int, int, int, int]:
    return te._box(img, rnd, frac)


def double_jpeg(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """Saved once, shifted a few pixels, saved again: the block grids no longer line up."""
    first = as_jpeg(img, rnd.choice([55, 65, 70]))
    dx, dy = rnd.randrange(1, 7), rnd.randrange(1, 7)
    shifted = first.crop((dx, dy, first.width, first.height)).resize(first.size, Image.BICUBIC)
    return shifted


def resample_artifacts(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """Shrunk with no smoothing and enlarged again, as upscalers and some generators do."""
    w, h = img.size
    scale = rnd.choice([0.4, 0.5, 0.6])
    small = img.resize((max(8, int(w * scale)), max(8, int(h * scale))), Image.NEAREST)
    return small.resize((w, h), Image.BICUBIC)


def screen_capture(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """A photo of a monitor: a faint periodic moire, a glare blob, softness and a gamma shift."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    period = rnd.choice([3.0, 4.0, 5.0])
    moire = 9.0 * (
        np.sin(xs * 2 * np.pi / period)[None, :] + np.sin(ys * 2 * np.pi / (period + 1))[:, None]
    )
    a += moire[..., None]
    cy, cx = rnd.randrange(h // 4, 3 * h // 4), rnd.randrange(w // 4, 3 * w // 4)
    yy, xx = np.ogrid[:h, :w]
    glare = np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * (min(h, w) * 0.12) ** 2)))
    a += 70.0 * glare[..., None]
    a = 255.0 * (np.clip(a, 0, 255) / 255.0) ** rnd.choice([0.9, 1.1])
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(rnd.choice([0.6, 0.9])))


def print_scan(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """Printed and scanned again: softer, noisier, flatter contrast."""
    a = np.asarray(img.convert("RGB").filter(ImageFilter.GaussianBlur(1.0)), dtype=np.float32)
    nrng = np.random.default_rng(rnd.randrange(2**31))
    a = (a - 128.0) * 0.9 + 128.0 + nrng.normal(0, 6.0, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def noise_patch(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """A region with a different noise floor, as a pasted or generated patch would have."""
    out = np.asarray(img.convert("RGB"), dtype=np.float32).copy()
    x0, y0, x1, y1 = _region(img, rnd)
    nrng = np.random.default_rng(rnd.randrange(2**31))
    out[y0:y1, x0:x1] += nrng.normal(0, 14.0, out[y0:y1, x0:x1].shape)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def face_blend(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """Blend another face into the middle of this one inside a soft ellipse (a crude swap)."""
    w, h = img.size
    other = donor.convert("RGB").resize((w, h))
    mask = Image.new("L", (w, h), 0)
    arr = np.zeros((h, w), np.uint8)
    cv2.ellipse(arr, (w // 2, h // 2), (int(w * 0.28), int(h * 0.36)), 0, 0, 360, 255, -1)
    mask = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(max(2, w // 40)))
    alpha = rnd.choice([0.55, 0.7, 0.85])
    blended = Image.composite(other, img.convert("RGB"), mask.point(lambda v: int(v * alpha)))
    return blended


def face_warp(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """A smooth non-rigid warp (the stretch a morph or a reenactment leaves)."""
    a = np.asarray(img.convert("RGB"))
    h, w = a.shape[:2]
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    amp = rnd.choice([2.0, 3.0, 4.0]) * (w / 256.0)
    fx = rnd.choice([2.0, 3.0]) * 2 * np.pi / w
    mapx = xx + amp * np.sin(yy * fx)
    mapy = yy + amp * np.cos(xx * fx)
    return Image.fromarray(
        cv2.remap(a, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    )


GENERATORS: dict[str, Forger] = {
    "crop_replace": lambda i, d, r: te.crop_replace(i, d, r),
    "text_edit": lambda i, d, r: te.text_edit(i, r),
    "inpaint": lambda i, d, r: te.inpaint(i, r),
    "recompress_region": lambda i, d, r: te.recompress_region(i, r),
    "double_jpeg": double_jpeg,
    "resample_artifacts": resample_artifacts,
    "screen_capture": screen_capture,
    "print_scan": print_scan,
    "noise_patch": noise_patch,
    "face_blend": face_blend,
    "face_warp": face_warp,
}

# which generators make sense for which kind of subject
KIND_GENERATORS: dict[str, tuple[str, ...]] = {
    "receipt": (
        "crop_replace",
        "text_edit",
        "inpaint",
        "recompress_region",
        "double_jpeg",
        "resample_artifacts",
        "screen_capture",
        "noise_patch",
    ),
    "doc": (
        "crop_replace",
        "text_edit",
        "inpaint",
        "double_jpeg",
        "resample_artifacts",
        "screen_capture",
        "print_scan",
        "noise_patch",
    ),
    "face": ("face_blend", "face_warp", "screen_capture", "print_scan", "resample_artifacts"),
}


def forge(name: str, img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    return as_jpeg(GENERATORS[name](img, donor, rnd))
