"""Make a labelled dataset of genuine pictures and synthetic forgeries.

    python -m training.detect.build_dataset --kind receipt --out DIR --n 60
    python -m training.detect.build_dataset --kind doc --out DIR --source-dir my_genuine_images/

With --source-dir the genuine pictures are YOUR images (a folder of PNG/JPEG); without it, fictional
demo documents are drawn (no data needed, SAMPLE on their face). Forgeries are made from each source
by the generators in synth.py. Writes index.jsonl; the split is made later, by source.
"""

import argparse
from pathlib import Path

from PIL import Image

from training.detect import dataset
from training.detect.demo_sources import demo_genuine

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_folder(folder: Path, limit: int | None = None) -> list[Image.Image]:
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    return [Image.open(p).convert("RGB") for p in files[:limit]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", required=True, choices=["receipt", "doc", "face"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=60, help="number of demo sources (no --source-dir)")
    ap.add_argument("--source-dir", help="folder of genuine pictures to use instead of the demo")
    ap.add_argument("--forged-per-source", type=int, default=3)
    ap.add_argument("--scale", type=float, default=0.5, help="demo picture scale")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.out)
    if a.source_dir:
        images, groups = load_folder(Path(a.source_dir)), None
    else:
        images, groups = demo_genuine(a.kind, a.n, a.seed, a.scale)
    if len(images) < 6:
        raise SystemExit(
            "need at least 6 source pictures to split into train, calibration and test"
        )
    samples = dataset.build(
        a.kind, images, out, forged_per_source=a.forged_per_source, groups=groups, seed=a.seed
    )
    existing = []
    index = out / "index.jsonl"
    if index.is_file():  # several kinds can share one folder
        existing = [s for s in dataset.read_index(index) if s.kind != a.kind]
    dataset.write_index([*existing, *samples], index)
    forged = sum(s.label for s in samples)
    print(f"{len(samples)} pictures: {len(samples) - forged} genuine, {forged} forged -> {out}")


if __name__ == "__main__":
    main()
