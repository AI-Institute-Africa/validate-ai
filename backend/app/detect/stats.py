"""A fixed forensic feature vector for one picture (numpy and OpenCV only).

This is the input of the classical detector (`linear_model.py`): a few dozen numbers that
summarise what generators, editors and re-captures tend to disturb: how uniform the sensor-like
noise is across the picture, how the spectrum falls off and whether it has periodic peaks, how
error-level analysis varies by region, how strong the JPEG block grid is, and how even the
sharpness is.

Training and serving call the same function, and `FEATURE_VERSION` is stored in every model file,
so a model is never fed features computed by a different recipe.
"""

import cv2
import numpy as np
from PIL import Image

from app.detect import features

FEATURE_VERSION = "stats-v1"
SIZE = 256  # analysis resolution for the noise, spectrum and error-level features
GRID = 3  # the picture is split into GRID x GRID regions to see how uneven a statistic is
RADIAL_BINS = 12


def _cells(plane: np.ndarray) -> list[np.ndarray]:
    h, w = plane.shape
    ys = np.linspace(0, h, GRID + 1, dtype=int)
    xs = np.linspace(0, w, GRID + 1, dtype=int)
    return [plane[ys[i] : ys[i + 1], xs[j] : xs[j + 1]] for i in range(GRID) for j in range(GRID)]


def _kurtosis(x: np.ndarray) -> float:
    s = float(x.std())
    return float(((x - x.mean()) ** 4).mean() / (s**4)) if s > 1e-9 else 0.0


def _ratio(a: float, b: float) -> float:
    return float(a / b) if abs(b) > 1e-9 else 0.0


def _noise_stats(img: Image.Image) -> list[float]:
    r = np.abs(features.noise_residual(img, SIZE) - 0.5)
    cells = _cells(r)
    means = [float(c.mean()) for c in cells]
    stds = [float(c.std()) for c in cells]
    return [
        *means,
        *stds,
        float(r.mean()),
        float(r.std()),
        _kurtosis(r),
        float(np.percentile(r, 99)),
        _ratio(max(stds), float(np.median(stds))),
    ]


def _spectrum_stats(img: Image.Image) -> list[float]:
    s = features.fft_spectrum(img, SIZE)
    yy, xx = np.indices(s.shape)
    r = np.hypot(yy - SIZE / 2, xx - SIZE / 2) / (SIZE / 2)  # 0 at the centre, 1 at the edge
    edges = np.linspace(0.05, 1.0, RADIAL_BINS + 1)
    profile = [
        float(s[(r >= lo) & (r < hi)].mean()) if ((r >= lo) & (r < hi)).any() else 0.0
        for lo, hi in zip(edges[:-1], edges[1:], strict=True)
    ]
    high = s[(r > 0.35) & (r < 0.95)]
    rows, cols = float(s.mean(axis=1).std()), float(s.mean(axis=0).std())
    return [*profile, _ratio(float(high.max()), float(high.mean())), _ratio(rows, cols)]


def _ela_stats(img: Image.Image) -> list[float]:
    e = features.ela_map(img, SIZE)
    means = [float(c.mean()) for c in _cells(e)]
    return [
        *means,
        float(e.mean()),
        float(e.std()),
        float(np.percentile(e, 99)),
        _ratio(max(means), float(np.median(means))),
    ]


def _blockiness(img: Image.Image) -> list[float]:
    """JPEG block-grid strength: pixel jumps across 8-pixel boundaries compared with inside blocks.
    Measured on a centre crop at the original resolution, because resizing erases the grid."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    g = g[: min(h, 1024) // 8 * 8, : min(w, 1024) // 8 * 8]
    if g.shape[0] < 16 or g.shape[1] < 16:
        return [0.0, 0.0]
    dx = np.abs(np.diff(g, axis=1))  # jumps between horizontal neighbours; boundaries at 7, 15, ...
    dy = np.abs(np.diff(g, axis=0))
    on_x, in_x = dx[:, 7::8].mean(), np.delete(dx, np.s_[7::8], axis=1).mean()
    on_y, in_y = dy[7::8, :].mean(), np.delete(dy, np.s_[7::8], axis=0).mean()
    return [_ratio(float(on_x), float(in_x)), _ratio(float(on_y), float(in_y))]


def _colour_and_sharpness(img: Image.Image) -> list[float]:
    small = np.asarray(img.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR))
    ycc = cv2.cvtColor(small, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV).astype(np.float32)
    chroma = [float(np.abs(cv2.Laplacian(ycc[..., i], cv2.CV_32F)).mean()) for i in (1, 2)]
    gray = ycc[..., 0]
    lap = [float(cv2.Laplacian(c, cv2.CV_32F).var()) for c in _cells(gray)]
    return [
        float(hsv[..., 1].mean() / 255.0),
        *chroma,
        _ratio(float(np.std(lap)), float(np.mean(lap))),
        _ratio(min(lap), max(lap)),
    ]


def _names() -> list[str]:
    cells = [f"c{i}" for i in range(GRID * GRID)]
    return [
        *[f"noise_mean_{c}" for c in cells],
        *[f"noise_std_{c}" for c in cells],
        "noise_mean",
        "noise_std",
        "noise_kurtosis",
        "noise_p99",
        "noise_cell_unevenness",
        *[f"fft_radial_{i}" for i in range(RADIAL_BINS)],
        "fft_high_peakiness",
        "fft_row_col_ratio",
        *[f"ela_mean_{c}" for c in cells],
        "ela_mean",
        "ela_std",
        "ela_p99",
        "ela_cell_unevenness",
        "jpeg_block_h",
        "jpeg_block_v",
        "saturation_mean",
        "chroma_noise_cr",
        "chroma_noise_cb",
        "sharpness_unevenness",
        "sharpness_min_max",
    ]


FEATURE_NAMES = _names()


def feature_vector(img: Image.Image) -> np.ndarray:
    """The picture as `len(FEATURE_NAMES)` finite float32 numbers."""
    img = img.convert("RGB")
    vec = np.asarray(
        [
            *_noise_stats(img),
            *_spectrum_stats(img),
            *_ela_stats(img),
            *_blockiness(img),
            *_colour_and_sharpness(img),
        ],
        dtype=np.float64,
    )
    if vec.size != len(FEATURE_NAMES):  # a recipe change that forgot the names
        raise RuntimeError(
            f"feature recipe makes {vec.size} numbers, names list {len(FEATURE_NAMES)}"
        )
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
