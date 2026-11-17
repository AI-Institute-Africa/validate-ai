"""Measure face-match error rates and suggest a threshold.

    python tools/eval/face_eval.py --demo                 # self-test on the synthetic demo faces
    python tools/eval/face_eval.py --pairs pairs.csv   # your own: columns card,selfie,same (1/0)

Uses the configured POPS_KYC_FACE_BACKEND. Prints false-accept / false-reject by threshold and
the lowest threshold meeting --far. Too few impostor pairs for that target is said, not hidden.
"""

import argparse
import csv
import random
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.kyc import calibration  # noqa: E402


def _scores_from_csv(path: str, matcher) -> tuple[list[float], list[float]]:
    from app.kyc.cv import face
    from app.kyc.doc import detect

    gen, imp = [], []
    base = Path(path).parent
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            card = detect.find_card(Image.open(base / row["card"]).convert("RGB"))
            selfie = Image.open(base / row["selfie"]).convert("RGB")
            m = face.match(matcher, card.image if card.found else selfie, selfie)
            if m.score is not None:  # pairs with no face are counted separately by the pipeline
                (gen if row["same"].strip() == "1" else imp).append(m.score)
    return gen, imp


def _scores_demo() -> tuple[list[float], list[float]]:
    import io

    from app.demo import art
    from app.demo.sim import DemoFaceMatcher
    from app.kyc.cv import face
    from app.kyc.doc import detect

    rnd = random.Random(7)  # noqa: S311 - reproducible test data, not security
    m = DemoFaceMatcher()
    keys = list(art.PERSONAS)
    gen, imp = [], []

    def load(png: bytes) -> Image.Image:
        return Image.open(io.BytesIO(png)).convert("RGB")

    for k in keys:
        card = detect.find_card(load(art.id_card_png(art.id_fields(k, "VD-1000001"), k, seed=1)))
        for _ in range(6):
            gen.append(
                face.match(
                    m, card.image, load(art.selfie_png(k, seed=rnd.randrange(1, 10**6)))
                ).score
            )
        for other in keys:
            if other != k:
                imp.append(
                    face.match(
                        m, card.image, load(art.selfie_png(other, seed=rnd.randrange(1, 10**6)))
                    ).score
                )
    return [s for s in gen if s is not None], [s for s in imp if s is not None]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--pairs")
    ap.add_argument("--far", type=float, default=0.001)
    a = ap.parse_args()
    if a.demo:
        gen, imp = _scores_demo()
    elif a.pairs:
        from app.kyc.cv import face

        gen, imp = _scores_from_csv(a.pairs, face.build_matcher())
    else:
        sys.exit("give --demo or --pairs")
    print(f"genuine pairs: {len(gen)}   impostor pairs: {len(imp)}")
    for p in calibration.curve(gen, imp, steps=11):
        print(
            f"  threshold {p.threshold:6.3f}   false accept {p.far:6.1%}"
            f"   false reject {p.frr:6.1%}"
        )
    auc = calibration.auc(gen, imp)
    lo, hi = calibration.bootstrap_ci(calibration.auc, gen, imp)
    print(f"\nAUC {auc:.4f}  (95% interval {lo:.4f} to {hi:.4f}; 0.5 is a coin toss)")
    # how much the answer could move: the threshold again on resampled pairs
    picks = []
    import random

    rnd = random.Random(0)  # noqa: S311 - reproducible statistics
    for _ in range(200):
        g = [rnd.choice(gen) for _ in gen]
        i = [rnd.choice(imp) for _ in imp]
        p = calibration.threshold_for_far(g, i, a.far)
        if p:
            picks.append(p.threshold)
    if picks:
        picks.sort()
        print(
            f"Threshold for FAR <= {a.far:.2%} moves between "
            f"{picks[int(0.025 * len(picks))]:.3f} and "
            f"{picks[int(0.975 * len(picks)) - 1]:.3f} (95%) when the pairs are resampled."
        )
    print("Protocol for collecting real pairs: docs/kyc.md, 'Calibrating the face threshold'.")
    need = calibration.min_pairs_for(a.far)
    pick = calibration.threshold_for_far(gen, imp, a.far)
    if len(imp) < need:
        print(
            f"\nOnly {len(imp)} impostor pairs: a false-accept rate of {a.far:.2%} "
            f"needs about {need} to be measurable."
        )
    print(
        f"Suggested kyc_min_face_score for FAR <= {a.far:.2%}: "
        f"{pick.threshold if pick else 'none reachable'}"
    )


if __name__ == "__main__":
    main()
