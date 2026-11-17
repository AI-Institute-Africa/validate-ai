"""Turn scores from known-genuine and known-impostor pairs into error rates and a threshold.

Pure functions, no model needed. The face threshold in the policy (`kyc_min_face_score`) should come
from this on YOUR OWN ID/selfie pairs, not from a published default: faces on old, small ID photos
score lower than benchmark pairs, and error rates differ by population.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    threshold: float
    far: float  # impostors wrongly accepted
    frr: float  # genuine people wrongly sent to a person


def curve(genuine: list[float], impostor: list[float], steps: int = 101) -> list[Point]:
    if not genuine or not impostor:
        raise ValueError("need at least one genuine and one impostor score")
    lo = min(*genuine, *impostor)
    hi = max(*genuine, *impostor)
    out = []
    for i in range(steps):
        t = lo + (hi - lo) * i / (steps - 1)
        far = sum(s >= t for s in impostor) / len(impostor)
        frr = sum(s < t for s in genuine) / len(genuine)
        out.append(Point(round(t, 4), far, frr))
    return out


def threshold_for_far(
    genuine: list[float], impostor: list[float], target_far: float = 0.001
) -> Point | None:
    """The lowest threshold whose false-accept rate is at or under the target. With few impostor
    pairs a tiny target cannot be shown, so say so rather than pretend (see `min_pairs_for`)."""
    ok = [p for p in curve(genuine, impostor, steps=401) if p.far <= target_far]
    return min(ok, key=lambda p: p.threshold) if ok else None


def min_pairs_for(target_far: float) -> int:
    """Impostor pairs needed before a false-accept rate of `target_far` is even measurable
    (rule of three: zero errors in 3/rate trials bounds the rate at 95%)."""
    return int(3 / target_far) + 1


# --- how sure are we? -----------------------------------------------------------------------------


def auc(positive: list[float], negative: list[float]) -> float:
    """Chance that a random positive scores higher than a random negative (ties count half).
    0.5 is a coin toss, 1.0 separates them perfectly."""
    if not positive or not negative:
        raise ValueError("need at least one positive and one negative score")
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def bootstrap_ci(
    stat,  # a function of (list_a, list_b) -> float
    a: list[float],
    b: list[float],
    rounds: int = 500,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float]:
    """A confidence interval by resampling both score lists with replacement. With few samples it is
    wide, and that width is the honest message."""
    import random

    rnd = random.Random(seed)  # noqa: S311 - reproducible statistics, not security
    out = sorted(
        stat([rnd.choice(a) for _ in a], [rnd.choice(b) for _ in b]) for _ in range(rounds)
    )
    lo = out[int(((1 - level) / 2) * (rounds - 1))]
    hi = out[int((1 - (1 - level) / 2) * (rounds - 1))]
    return lo, hi


def flag_rates(threshold: float, forged: list[float], genuine: list[float]) -> tuple[float, float]:
    """For a detector that flags a document when its score is at or above `threshold`:
    (share of forged documents caught, share of genuine documents wrongly flagged)."""
    caught = sum(s >= threshold for s in forged) / len(forged)
    wrong = sum(s >= threshold for s in genuine) / len(genuine)
    return caught, wrong


def threshold_for_false_flags(
    forged: list[float], genuine: list[float], max_false_flag: float = 0.05
) -> tuple[float, float, float] | None:
    """The lowest threshold that wrongly flags at most `max_false_flag` of genuine documents, with
    (threshold, share of forged caught, share of genuine wrongly flagged). None if none exists."""
    best = None
    scores = [*forged, *genuine]
    # the last candidate is just above every score: flag nothing, so a threshold always exists
    for t in [*sorted(set(scores)), max(scores) + 1e-9]:
        caught, wrong = flag_rates(t, forged, genuine)
        if wrong <= max_false_flag and (best is None or caught > best[1]):
            best = (t, caught, wrong)
    return best
