"""Forensic input channels for the detector models (numpy and OpenCV only).

Generators, upscalers and editors leave traces that are weak in the pixels but strong in the
residual and the spectrum: unnatural high-frequency noise, periodic peaks, compression history that
differs across a picture. Each function returns one float32 plane in [0, 1] of size x size, from a
fixed, deterministic recipe, so the training tool and the server prepare the input identically.
"""

import io

import cv2
import numpy as np
from PIL import Image

# Fixed high-pass kernels in the spirit of SRM steganalysis filters: first-order, second-order and a
# 5x5 "KV" kernel. They are constants, not learned, so a model file never depends on them changing.
_K1 = np.array([[0, 0, 0], [0, -1, 1], [0, 0, 0]], dtype=np.float32)
_K2 = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
_KV = (
    np.array(
        [
            [-1, 2, -2, 2, -1],
            [2, -6, 8, -6, 2],
            [-2, 8, -12, 8, -2],
            [2, -6, 8, -6, 2],
            [-1, 2, -2, 2, -1],
        ],
        dtype=np.float32,
    )
    / 12.0
)
_TRUNC = 3.0  # residuals beyond +-3 grey levels are clipped: the model sees texture, not edges


def _gray(img: Image.Image, size: int) -> np.ndarray:
    small = img.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.float32)


def noise_residual(img: Image.Image, size: int) -> np.ndarray:
    """Truncated high-pass residual, averaged over the three fixed kernels, scaled to [0, 1]."""
    g = _gray(img, size)
    out = np.zeros_like(g)
    for k in (_K1, _K2, _KV):
        out += np.clip(cv2.filter2D(g, -1, k), -_TRUNC, _TRUNC)
    out /= 3.0 * 2.0 * _TRUNC
    return np.clip(out + 0.5, 0.0, 1.0).astype(np.float32)


def fft_spectrum(img: Image.Image, size: int) -> np.ndarray:
    """Hann-windowed log-magnitude spectrum with the zero frequency in the centre, in [0, 1]."""
    g = _gray(img, size)
    g -= float(g.mean())
    win = np.outer(np.hanning(size), np.hanning(size)).astype(np.float32)
    mag = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(g * win)))).astype(np.float32)
    top = float(mag.max())
    return (mag / top if top > 0 else mag).astype(np.float32)


def ela_map(img: Image.Image, size: int, quality: int = 90) -> np.ndarray:
    """Error-level analysis: how much re-saving as JPEG at `quality` changes each pixel, in [0, 1].

    Regions compressed differently from the rest (a pasted-in amount, an inpainted patch) respond
    differently. This is the channel only; the reviewer heatmap is `app/fraud/forensics.py`.
    """
    rgb = img.convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    again = Image.open(buf).convert("RGB")
    diff = np.abs(np.asarray(rgb, dtype=np.float32) - np.asarray(again, dtype=np.float32))
    return np.clip(diff.mean(axis=2) / 32.0, 0.0, 1.0).astype(np.float32)
