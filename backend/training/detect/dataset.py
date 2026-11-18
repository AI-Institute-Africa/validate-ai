"""A labelled set of pictures on disk, split so the numbers mean something.

The split is by SOURCE: a genuine picture and every forgery made from it stay together, in the
train, calibration or test part. Splitting random rows instead would put a forgery in training and
its original in the test set, and the score would measure memory, not skill. A fourth set, the
EVASION set, is made only from test sources: the same pictures re-compressed, rescaled or noised, to
see whether the detector survives the cheap ways of hiding.
"""

import io
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from training.detect import synth


@dataclass(frozen=True)
class Sample:
    path: str  # relative to the dataset folder
    label: int  # 1 = forged / synthetic / duplicate, 0 = genuine
    generator: str  # "genuine" or the forger's name
    source: str  # the original picture this one came from
    group: str  # a grouping for the per-group table (template, persona, lighting ...)
    kind: str  # receipt | doc | face


def write_index(samples: list[Sample], path: Path) -> None:
    path.write_text("".join(json.dumps(asdict(s)) + "\n" for s in samples))


def read_index(path: Path) -> list[Sample]:
    return [Sample(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def split_by_source(
    samples: list[Sample], seed: int = 0, fractions: tuple[float, float, float] = (0.6, 0.2, 0.2)
) -> dict[str, list[Sample]]:
    """train / calib / test, with every sample of one source in the same part."""
    sources = sorted({s.source for s in samples})
    random.Random(seed).shuffle(sources)  # noqa: S311 - reproducible split, not security
    n = len(sources)
    n_train = max(1, round(n * fractions[0]))
    n_calib = max(1, round(n * fractions[1])) if n >= 3 else 0
    part = {}
    for i, src in enumerate(sources):
        part[src] = "train" if i < n_train else "calib" if i < n_train + n_calib else "test"
    if n >= 3 and "test" not in part.values():  # tiny sets: keep something to test on
        part[sources[-1]] = "test"
    out: dict[str, list[Sample]] = {"train": [], "calib": [], "test": []}
    for s in samples:
        out[part[s.source]].append(s)
    return out


def evasion_variants(img: Image.Image, rnd: random.Random) -> list[tuple[str, Image.Image]]:
    """The cheap ways to hide an edit: save badly, shrink, add noise, photograph a screenshot."""
    w, h = img.size

    def jpeg(im: Image.Image, q: int) -> Image.Image:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=q)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")

    nrng = np.random.default_rng(rnd.randrange(2**31))
    noisy = np.asarray(img.convert("RGB"), dtype=np.float32) + nrng.normal(0, 3.0, (h, w, 3))
    return [
        ("recompress_q55", jpeg(img, 55)),
        ("rescale_70", img.resize((int(w * 0.7), int(h * 0.7)), Image.BILINEAR)),
        ("added_noise", Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))),
        (
            "screenshot_of_screenshot",
            jpeg(
                img.resize((int(w * 0.8), int(h * 0.8)), Image.BILINEAR).filter(
                    ImageFilter.GaussianBlur(0.8)
                ),
                70,
            ),
        ),
    ]


def build(
    kind: str,
    genuine: list[Image.Image],
    out_dir: Path,
    *,
    forged_per_source: int = 3,
    groups: list[str] | None = None,
    seed: int = 0,
    jpeg_quality: int = 85,
) -> list[Sample]:
    """Write genuine pictures and forgeries made from them under `out_dir`, and return the index."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)  # noqa: S311 - reproducible test data
    names = synth.KIND_GENERATORS[kind]
    samples: list[Sample] = []
    for i, base in enumerate(genuine):
        source, group = f"{kind}-{i:05d}", (groups[i] if groups else "default")
        donor = genuine[(i + 3) % len(genuine)]
        g = synth.as_jpeg(base, jpeg_quality)
        rel = f"{source}-genuine.jpg"
        g.save(out_dir / rel, "JPEG", quality=95)
        samples.append(Sample(rel, 0, "genuine", source, group, kind))
        for j, name in enumerate(rnd.sample(names, min(forged_per_source, len(names)))):
            forged = synth.forge(name, base, donor, rnd)
            rel = f"{source}-{j}-{name}.jpg"
            forged.save(out_dir / rel, "JPEG", quality=95)
            samples.append(Sample(rel, 1, name, source, group, kind))
    return samples


def build_evasion(test: list[Sample], folder: Path, seed: int = 0) -> list[Sample]:
    """Evasion copies of every test picture, labelled like the original."""
    rnd = random.Random(seed)  # noqa: S311
    out = []
    for s in test:
        img = Image.open(folder / s.path).convert("RGB")
        for tag, variant in evasion_variants(img, rnd):
            rel = f"{Path(s.path).stem}--{tag}.jpg"
            variant.save(folder / rel, "JPEG", quality=92)
            out.append(Sample(rel, s.label, f"{s.generator}+{tag}", s.source, s.group, s.kind))
    return out


def by_source(samples: list[Sample]) -> dict[str, list[Sample]]:
    d: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        d[s.source].append(s)
    return d
