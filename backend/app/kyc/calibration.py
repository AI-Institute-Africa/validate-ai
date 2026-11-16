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
