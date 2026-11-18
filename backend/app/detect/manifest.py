"""manifest.json: which model file serves which detector, and what it was published as.

The manifest lives in the model folder next to the files. A file is only loaded if its SHA-256
matches the manifest, so a swapped or corrupted model is never run. Paths must stay inside
the folder.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.detect.base import DETECT_KINDS, LABELS

_SHA = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_NAME = "manifest.json"


class ManifestError(ValueError):
    """The manifest is missing parts or unsafe. Every detector is then recorded as skipped."""


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    file: Path
    version: str
    sha256: str
    label: str
    size: int = 224
    channels: tuple[str, ...] = ("rgb",)
    threshold: float | None = None
    uncertain_band: tuple[float, float] | None = None
    tta: int = 1  # test-time augmentation: how many mild views to average (1 = just the image)
    card: str | None = None  # pointer to the model card
    extra: dict[str, Any] = field(default_factory=dict)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(folder: Path, name: str) -> Path:
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents:
        raise ManifestError(f"model file {name!r} is outside the model folder")
    return path


def load_manifest(folder: str | Path) -> dict[str, Entry]:
    """Entries by kind. An absent manifest is an empty result (nothing installed), not an error."""
    root = Path(folder)
    path = root / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
        detectors = raw["detectors"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ManifestError(f"cannot read {MANIFEST_NAME}: {exc}") from exc
    out: dict[str, Entry] = {}
    for kind, d in detectors.items():
        if kind not in DETECT_KINDS:
            raise ManifestError(f"unknown detector kind {kind!r}")
        try:
            sha = str(d["sha256"]).lower()
            label = str(d["label"])
            if not _SHA.match(sha):
                raise ManifestError(f"{kind}: sha256 must be 64 hex characters")
            if label not in LABELS:
                raise ManifestError(f"{kind}: label {label!r} is not one of {', '.join(LABELS)}")
            band = d.get("uncertain_band")
            if band is not None and not (0.0 <= band[0] < band[1] <= 1.0):
                raise ManifestError(f"{kind}: uncertain_band must be [low, high] within 0..1")
            thr = d.get("threshold")
            if thr is not None and not 0.0 < float(thr) <= 1.0:
                raise ManifestError(f"{kind}: threshold must be above 0 and at most 1")
            inp = d.get("input", {})
            tta = int(d.get("tta", 1))
            if not 1 <= tta <= 5:
                raise ManifestError(f"{kind}: tta must be between 1 and 5")
            out[kind] = Entry(
                kind=kind,
                name=str(d.get("name") or Path(d["file"]).stem),
                file=_inside(root, str(d["file"])),
                version=str(d["version"]),
                sha256=sha,
                label=label,
                size=int(inp.get("size", 224)),
                channels=tuple(inp.get("channels", ["rgb"])),
                threshold=None if thr is None else float(thr),
                uncertain_band=None if band is None else (float(band[0]), float(band[1])),
                tta=tta,
                card=d.get("card"),
            )
        except KeyError as exc:
            raise ManifestError(f"{kind}: missing {exc.args[0]!r}") from exc
    return out
