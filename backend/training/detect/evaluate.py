"""Measure a trained detector on the held-out test part, and write its model card.

    python -m training.detect.evaluate --data DIR --kind receipt --model MODEL_DIR [--card CARD.md]

Reports, on pictures the model never trained or calibrated on (split by source):
  - AUC with a 95% bootstrap interval, for the model and for the existing hand-written tamper check
  - at the threshold the manifest carries (chosen on the calibration part, not here): the share of
    forgeries caught and of genuine pictures wrongly flagged
  - recall per forgery generator, and rates per group
  - the same on the evasion set (re-compressed, rescaled, noised, re-photographed copies)

Every report starts with a banner when the data is synthetic, because those numbers describe the
generators, not real fraud.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from app.detect.linear_model import NpzScorer
from app.detect.manifest import load_manifest
from app.extraction import tamper
from training.detect import dataset

BANNER = (
    "SYNTHETIC DATA ONLY: these numbers describe how well the detector separates the forgery\n"
    "generators in training/detect/synth.py from the genuine sources, NOT how it performs on real\n"
    "fraud. Real accuracy needs reviewer-confirmed fakes from this deployment."
)


def auc_np(pos: np.ndarray, neg: np.ndarray) -> float:
    """Same value as `calibration.auc` (ties count half), by ranks: fast enough to bootstrap."""
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, allv.size + 1)
    for v in np.unique(allv):  # average the ranks of tied values
        m = allv == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return float((ranks[: pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def auc_ci(
    pos: np.ndarray, neg: np.ndarray, rounds: int = 300, seed: int = 0
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    vals = sorted(
        auc_np(rng.choice(pos, pos.size), rng.choice(neg, neg.size)) for _ in range(rounds)
    )
    return vals[int(0.025 * (rounds - 1))], vals[int(0.975 * (rounds - 1))]


def _rate(scores: np.ndarray, t: float | None) -> float | None:
    return None if t is None or scores.size == 0 else float((scores >= t).mean())


def _table(rows: list[tuple]) -> str:
    return "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)


def score_set(folder: Path, samples: list[dataset.Sample], scorer: NpzScorer) -> np.ndarray:
    return np.array([scorer.probability(Image.open(folder / s.path)) for s in samples])


def tamper_scores(folder: Path, samples: list[dataset.Sample]) -> np.ndarray:
    out = []
    for s in samples:
        r = tamper.analyse(Image.open(folder / s.path))
        out.append(0.0 if r.skipped else r.score)
    return np.array(out)


def section(
    name: str,
    samples: list[dataset.Sample],
    probs: np.ndarray,
    threshold: float | None,
    baseline: np.ndarray | None = None,
) -> tuple[str, dict]:
    y = np.array([s.label for s in samples])
    pos, neg = probs[y == 1], probs[y == 0]
    lo, hi = auc_ci(pos, neg)
    result = {
        "pictures": len(samples),
        "genuine": int((y == 0).sum()),
        "forged": int((y == 1).sum()),
        "auc": auc_np(pos, neg),
        "auc_ci": [lo, hi],
        "caught": _rate(pos, threshold),
        "false_flag": _rate(neg, threshold),
    }
    lines = [
        f"### {name}",
        f"{result['pictures']} pictures ({result['genuine']} genuine, {result['forged']} forged)",
        "",
        f"- AUC {result['auc']:.3f} (95% interval {lo:.3f} to {hi:.3f})",
    ]
    if baseline is not None:
        bp, bn = baseline[y == 1], baseline[y == 0]
        blo, bhi = auc_ci(bp, bn)
        result["tamper_auc"] = auc_np(bp, bn)
        result["tamper_auc_ci"] = [blo, bhi]
        lines.append(
            f"- the existing tamper check on the same pictures: AUC {result['tamper_auc']:.3f} "
            f"(95% interval {blo:.3f} to {bhi:.3f})"
        )
    if threshold is None:
        lines.append(
            "- no threshold in the manifest (the target false-flag rate was not reachable)"
        )
    else:
        lines.append(
            f"- at threshold {threshold:.3f}: caught {result['caught']:.1%} of forged, "
            f"wrongly flagged {result['false_flag']:.1%} of genuine"
        )
    return "\n".join(lines), result


def per_generator(samples, probs, threshold) -> tuple[str, dict]:
    y = np.array([s.label for s in samples])
    neg = probs[y == 0]
    rows = [("generator", "pictures", "AUC vs genuine", "caught at threshold")]
    detail = {}
    for gen in sorted({s.generator.split("+")[0] for s in samples if s.label == 1}):
        idx = [i for i, s in enumerate(samples) if s.label == 1 and s.generator.startswith(gen)]
        p = probs[idx]
        a = auc_np(p, neg)
        r = _rate(p, threshold)
        rows.append((gen, len(idx), f"{a:.3f}", "n/a" if r is None else f"{r:.0%}"))
        detail[gen] = {"pictures": len(idx), "auc": a, "caught": r}
    return _table([rows[0], ("---", "---", "---", "---"), *rows[1:]]), detail


def per_group(samples, probs, threshold) -> tuple[str, dict]:
    rows = [("group", "genuine", "wrongly flagged", "forged", "caught")]
    detail = {}
    for g in sorted({s.group for s in samples}):
        gi = [i for i, s in enumerate(samples) if s.group == g and s.label == 0]
        fi = [i for i, s in enumerate(samples) if s.group == g and s.label == 1]
        ff, ca = _rate(probs[gi], threshold), _rate(probs[fi], threshold)
        fmt = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
        rows.append((g, len(gi), fmt(ff), len(fi), fmt(ca)))
        detail[g] = {"genuine": len(gi), "false_flag": ff, "forged": len(fi), "caught": ca}
    return _table([rows[0], ("---",) * 5, *rows[1:]]), detail


def evaluate(
    folder: Path, kind: str, model_dir: Path, seed: int = 0, evasion: bool = True
) -> tuple[str, dict]:
    entry = load_manifest(model_dir)[kind]
    scorer = NpzScorer(entry)
    samples = [s for s in dataset.read_index(folder / "index.jsonl") if s.kind == kind]
    test = dataset.split_by_source(samples, seed)["test"]
    if not test:
        raise SystemExit("no test pictures: the dataset is too small to hold any back")
    probs = score_set(folder, test, scorer)
    base = tamper_scores(folder, test)
    parts = [BANNER, "", f"## {kind}: {entry.version}", ""]
    main_md, main = section("Held-out test part", test, probs, entry.threshold, base)
    gen_md, gen = per_generator(test, probs, entry.threshold)
    grp_md, grp = per_group(test, probs, entry.threshold)
    parts += [main_md, "", "Per forgery generator:", "", gen_md, "", "Per group:", "", grp_md]
    out: dict = {"version": entry.version, "test": main, "generators": gen, "groups": grp}
    if evasion:
        ev = dataset.build_evasion(test, folder, seed)
        evp = score_set(folder, ev, scorer)
        ev_md, ev_res = section("Evasion set (cheap ways of hiding)", ev, evp, entry.threshold)
        parts += ["", ev_md]
        out["evasion"] = ev_res
    out["synthetic_only"] = True
    return "\n".join(parts) + "\n", out


def model_card(report: dict, train_report: dict | None, kind: str) -> str:
    t = report["test"]
    tr = train_report or {}
    return f"""# Model card: {report["version"]}

**SYNTHETIC DATA ONLY.** Nothing below is real-world accuracy.

| Field | Value |
| --- | --- |
| Purpose | {kind} authenticity detector (classical baseline) |
| Base model and licence | none: logistic regression fitted from scratch on forensic statistics |
| How it was obtained | trained from scratch with `training/detect/train_linear.py` |
| Where it runs | the server that loads it, on the CPU, no network |
| Version string recorded on decisions | `{report["version"]}` |
| Training data | synthetic forgeries from `training/detect/synth.py`; {tr.get("train_pictures", "?")} training pictures; no real fakes; no consent record needed |
| Held-out test set | {t["pictures"]} pictures, split by source; no real documents |
| Evaluated | {datetime.now(UTC):%Y-%m-%d} |

## Accuracy on the held-out synthetic test part

- AUC {t["auc"]:.3f} (95% interval {t["auc_ci"][0]:.3f} to {t["auc_ci"][1]:.3f})
- the existing hand-written tamper check: AUC {t.get("tamper_auc", float("nan")):.3f}
- at the manifest threshold: caught {_pct(t["caught"])}, wrongly flagged {_pct(t["false_flag"])}
- conformal uncertainty band: {tr.get("uncertain_band")} (alpha {tr.get("conformal_alpha")})
- calibration error (ECE) on the calibration part: {tr.get("ece")}

Evasion set: AUC {report.get("evasion", {}).get("auc", float("nan")):.3f}.

## Acceptance gates (docs/authenticity-detectors.md)

| Gate | Met? |
| --- | --- |
| AUC lower bound above the agreed target on a held-out set that includes real documents | no: no real documents |
| False-flag rate at the agreed level on genuine documents | not shown on real documents |
| Per-group gap within the agreed bound (faces) | not applicable: groups here are templates and drawn personas, not demographic groups |
| Evasion split reported | yes, synthetic |
| Signed by a named person | no |

**Stays in `shadow` mode.** Do not move to `escalate` on this card.

## Known limits

It sees summary statistics, not the picture. It learned these generators and nothing else. It has
never seen a real phone photo, a real receipt or a real face.
"""  # noqa: E501


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--kind", required=True, choices=["receipt", "doc", "face"])
    ap.add_argument("--model", required=True, help="model folder with manifest.json")
    ap.add_argument("--card", help="write a filled model card here")
    ap.add_argument("--json", help="write the numbers here")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    md, res = evaluate(Path(a.data), a.kind, Path(a.model), a.seed)
    sys.stdout.write(md)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2, default=str) + "\n")
    if a.card:
        tr_path = Path(a.model) / f"train-report-{a.kind}.json"
        train_report = json.loads(tr_path.read_text()) if tr_path.is_file() else None
        Path(a.card).write_text(model_card(res, train_report, a.kind))


if __name__ == "__main__":
    main()
