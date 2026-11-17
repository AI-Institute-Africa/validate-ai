"""How well does the tamper check separate edited documents from genuine ones?

    python tools/eval/tamper_eval.py --genuine real_ids/ --forged forged_ids/   # your own data
    python tools/eval/tamper_eval.py --demo                                  # synthetic self-test

Folders hold images (PNG, JPEG, ...) or PDFs. Higher score = more suspicious
(app.extraction.tamper).
Prints the share of forged documents caught and genuine ones wrongly flagged at each threshold, the
AUC with a 95% bootstrap interval, and the lowest threshold that keeps false flags under
--max-false-flag.

The --demo set is synthetic and flat: it checks that the harness runs, NOT how good the detector is
on real documents. For that, use a labelled real set such as SIDTD (European IDs: Crop and Replace,
Inpainting, printed and filmed counterfeits). Read its licence first (reports conflict between
CC BY-SA and CC BY-NC-ND), use it for evaluation only, and never commit its images.
"""

import argparse
import io
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.extraction import tamper  # noqa: E402
from app.intake.files import prepare  # noqa: E402
from app.kyc import calibration as cal  # noqa: E402

MAX = 40 * 1024 * 1024


# --- ways to forge a picture (the kinds SIDTD uses), so the demo has something to catch ----------


def _box(img: Image.Image, rnd: random.Random, frac=(0.18, 0.12)) -> tuple[int, int, int, int]:
    w, h = img.size
    bw, bh = int(w * frac[0]), int(h * frac[1])
    x, y = rnd.randrange(int(w * 0.1), w - bw - 5), rnd.randrange(int(h * 0.1), h - bh - 5)
    return x, y, x + bw, y + bh


def crop_replace(img: Image.Image, donor: Image.Image, rnd: random.Random) -> Image.Image:
    """Paste a patch from a different picture over a region."""
    out = img.copy()
    box = _box(out, rnd)
    dw, dh = donor.size
    px, py = rnd.randrange(0, dw - (box[2] - box[0])), rnd.randrange(0, dh - (box[3] - box[1]))
    out.paste(donor.crop((px, py, px + box[2] - box[0], py + box[3] - box[1])), box[:2])
    return out


def text_edit(img: Image.Image, rnd: random.Random) -> Image.Image:
    """Cover a region and type different text over it."""
    out = img.copy()
    box = _box(out, rnd, (0.22, 0.07))
    d = ImageDraw.Draw(out)
    bg = out.getpixel((box[0] - 2, box[1] + 2))
    d.rectangle(box, fill=bg)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", max(12, (box[3] - box[1]) - 4))
    except OSError:
        font = ImageFont.load_default()
    d.text((box[0] + 2, box[1]), str(rnd.randrange(10**6, 10**7)), fill="black", font=font)
    return out


def inpaint(img: Image.Image, rnd: random.Random) -> Image.Image:
    """Erase a region and let the picture fill it in."""
    bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    x0, y0, x1, y1 = _box(img, rnd)
    mask = np.zeros(bgr.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = 255
    return Image.fromarray(
        cv2.cvtColor(cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
    )


def recompress_region(img: Image.Image, rnd: random.Random) -> Image.Image:
    """Re-save one region at low quality and put it back (a different compression history)."""
    out = img.copy()
    box = _box(out, rnd)
    buf = io.BytesIO()
    out.crop(box).save(buf, "JPEG", quality=25)
    out.paste(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), box[:2])
    return out


FORGERIES = ("crop_replace", "text_edit", "inpaint", "recompress_region")


def _as_jpeg(img: Image.Image, quality=90) -> Image.Image:
    """Documents arrive compressed; every picture, genuine or forged, takes the same last save."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def score(img: Image.Image) -> float | None:
    r = tamper.analyse(img)
    return None if r.skipped else r.score


def demo_sets(n: int, seed: int = 11) -> tuple[list[float], list[float], dict[str, list[float]]]:
    from app.demo import art

    rnd = random.Random(seed)  # noqa: S311 - reproducible test data
    keys = list(art.PERSONAS)
    cards = []
    for i in range(n):
        k = keys[i % len(keys)]
        png = art.id_card_png(
            art.id_fields(k, f"VD-{1000000 + i}"), k, seed=rnd.randrange(1, 10**6)
        )
        # a real photo of a document has been through JPEG once (the camera); edits start there
        cards.append(_as_jpeg(Image.open(io.BytesIO(png)), 75))
    genuine = [s for c in cards if (s := score(_as_jpeg(c))) is not None]
    forged: list[float] = []
    by_kind: dict[str, list[float]] = {k: [] for k in FORGERIES}
    for i, c in enumerate(cards):
        kind = FORGERIES[i % len(FORGERIES)]
        donor = cards[(i + 3) % len(cards)]
        edited = {
            "crop_replace": lambda c=c, d=donor: crop_replace(c, d, rnd),
            "text_edit": lambda c=c: text_edit(c, rnd),
            "inpaint": lambda c=c: inpaint(c, rnd),
            "recompress_region": lambda c=c: recompress_region(c, rnd),
        }[kind]()
        if (s := score(_as_jpeg(edited))) is not None:
            forged.append(s)
            by_kind[kind].append(s)
    return genuine, forged, by_kind


def folder_scores(folder: str) -> list[float]:
    out = []
    for p in sorted(Path(folder).rglob("*")):
        if not p.is_file():
            continue
        try:
            prepared = prepare(p.read_bytes(), MAX)
        except Exception as exc:  # noqa: BLE001 - say which file, keep going
            print(f"  skipped {p.name}: {exc}")
            continue
        if (s := score(prepared.image)) is not None:
            out.append(s)
    return out


def report(genuine: list[float], forged: list[float], max_false_flag: float) -> None:
    print(f"genuine documents: {len(genuine)}   forged documents: {len(forged)}")
    lo, hi = min(*genuine, *forged), max(*genuine, *forged)
    print("  threshold   forged caught   genuine wrongly flagged")
    for i in range(11):
        t = lo + (hi - lo) * i / 10
        caught, wrong = cal.flag_rates(t, forged, genuine)
        print(f"  {t:9.3f}   {caught:12.1%}   {wrong:22.1%}")
    a = cal.auc(forged, genuine)
    ci = cal.bootstrap_ci(cal.auc, forged, genuine)
    print(f"\nAUC {a:.3f}  (95% interval {ci[0]:.3f} to {ci[1]:.3f}; 0.5 is a coin toss)")
    pick = cal.threshold_for_false_flags(forged, genuine, max_false_flag)
    if pick:
        print(
            f"Lowest threshold keeping false flags at or under {max_false_flag:.0%}: "
            f"{pick[0]:.3f} (catches {pick[1]:.0%}, wrongly flags {pick[2]:.0%}). "
            "Policy field: tamper_review_score."
        )
    else:
        print(f"No threshold keeps false flags under {max_false_flag:.0%}.")
    if min(len(genuine), len(forged)) < 100:
        print("Fewer than 100 of one kind: treat these numbers as a smoke test, not a measurement.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--genuine")
    ap.add_argument("--forged")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--n", type=int, default=40, help="demo documents")
    ap.add_argument("--max-false-flag", type=float, default=0.05)
    a = ap.parse_args()
    if a.demo:
        genuine, forged, by_kind = demo_sets(a.n)
        report(genuine, forged, a.max_false_flag)
        print("\nBy kind of edit (AUC against all genuine):")
        for kind, scores in by_kind.items():
            if scores and genuine:
                print(f"  {kind:18s} n={len(scores):3d}  AUC {cal.auc(scores, genuine):.3f}")
        print("\nSynthetic and flat: this checks the harness, not the detector on real documents.")
    elif a.genuine and a.forged:
        report(folder_scores(a.genuine), folder_scores(a.forged), a.max_false_flag)
    else:
        sys.exit("give --demo, or --genuine and --forged folders")


if __name__ == "__main__":
    main()
