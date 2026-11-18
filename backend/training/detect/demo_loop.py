"""The whole loop on a laptop, with nothing downloaded: build, train, evaluate, install.

    python -m training.detect.demo_loop --kind receipt --out ./var/detect-demo --n 60

Used by the test-suite on a tiny set. The model it writes is trained on fictional demo documents and
synthetic forgeries only: it exists to prove the pipeline works end to end, not to be used.
"""

import argparse
import sys
from pathlib import Path

from training.detect import dataset, evaluate, train_linear
from training.detect.demo_sources import demo_genuine


def run(kind: str, out: Path, n: int = 60, seed: int = 0, scale: float = 0.5) -> dict:
    data, models = out / "data", out / "models"
    images, groups = demo_genuine(kind, n, seed, scale)
    samples = dataset.build(kind, images, data, forged_per_source=3, groups=groups, seed=seed)
    dataset.write_index(samples, data / "index.jsonl")
    train_report = train_linear.train(data, kind, models, seed=seed)
    md, result = evaluate.evaluate(data, kind, models, seed)
    card = evaluate.model_card(result, train_report, kind)
    (models / f"model-card-{kind}.md").write_text(card)
    (models / f"evaluation-{kind}.md").write_text(md)
    return {"train": train_report, "evaluation": result, "report": md, "models": str(models)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", default="receipt", choices=["receipt", "doc", "face"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    res = run(a.kind, Path(a.out), a.n, a.seed)
    sys.stdout.write(res["report"])
    print(f"\nmodel folder: {res['models']}")
    print("use it: POPS_DETECT_MODEL_DIR=<that folder> POPS_DETECT_MODE=shadow")


if __name__ == "__main__":
    main()
