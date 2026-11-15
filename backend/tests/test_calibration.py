import pytest

from app.kyc import calibration as c


def test_curve_and_threshold():
    gen = [0.80, 0.85, 0.90, 0.95]
    imp = [0.10, 0.20, 0.30, 0.60]
    pts = c.curve(gen, imp)
    assert pts[0].far == 1.0 and pts[0].frr == 0.0  # accept everything
    assert pts[-1].far <= 0.25 and pts[-1].frr > 0.5  # accept almost nothing
    pick = c.threshold_for_far(gen, imp, target_far=0.0)
    assert (
        pick is not None and 0.60 < pick.threshold <= 0.80 and pick.far == 0.0 and pick.frr == 0.0
    )


def test_overlapping_scores_show_real_errors():
    gen, imp = [0.5, 0.7, 0.9], [0.4, 0.6, 0.8]
    pick = c.threshold_for_far(gen, imp, target_far=0.0)
    assert pick is not None and pick.frr > 0  # zero false accepts costs false rejects


def test_a_tiny_target_needs_many_pairs_and_empty_input_is_refused():
    assert c.min_pairs_for(0.001) >= 3000
    with pytest.raises(ValueError):
        c.curve([], [0.1])
