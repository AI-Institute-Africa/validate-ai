"""The measurement tools: the statistics are right, and the harnesses run end to end."""

import random
import sys
from pathlib import Path

import pytest
from PIL import Image

from app.kyc import calibration as cal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "eval"))
import tamper_eval as te  # noqa: E402


def test_auc_is_a_coin_toss_when_scores_do_not_separate_and_one_when_they_do():
    assert cal.auc([5, 6, 7], [1, 2, 3]) == 1.0
    assert cal.auc([1, 2, 3], [5, 6, 7]) == 0.0
    assert cal.auc([1, 2, 3], [1, 2, 3]) == 0.5  # identical scores: no information
    assert cal.auc([2, 2], [2, 2]) == 0.5  # ties count half
    with pytest.raises(ValueError):
        cal.auc([], [1])


def test_the_confidence_interval_is_wide_with_few_samples_and_tight_with_many():
    rnd = random.Random(1)
    few_a, few_b = [rnd.gauss(1, 1) for _ in range(8)], [rnd.gauss(0, 1) for _ in range(8)]
    many_a, many_b = [rnd.gauss(1, 1) for _ in range(400)], [rnd.gauss(0, 1) for _ in range(400)]
    lo1, hi1 = cal.bootstrap_ci(cal.auc, few_a, few_b)
    lo2, hi2 = cal.bootstrap_ci(cal.auc, many_a, many_b)
    assert (hi1 - lo1) > 2 * (hi2 - lo2)
    assert lo2 <= cal.auc(many_a, many_b) <= hi2
    assert cal.bootstrap_ci(cal.auc, few_a, few_b) == (lo1, hi1)  # reproducible


def test_flag_rates_and_the_threshold_that_limits_false_flags():
    forged, genuine = [0.9, 0.8, 0.7, 0.4], [0.5, 0.3, 0.2, 0.1, 0.1, 0.05, 0.02, 0.01, 0.0, 0.0]
    assert cal.flag_rates(0.6, forged, genuine) == (0.75, 0.0)
    t, caught, wrong = cal.threshold_for_false_flags(forged, genuine, max_false_flag=0.1)
    assert wrong <= 0.1 and caught >= 0.75
    # forged below genuine: the only threshold that spares every genuine one catches nothing
    t, caught, wrong = cal.threshold_for_false_flags([0.1], [0.5, 0.6], max_false_flag=0.0)
    assert caught == 0.0 and wrong == 0.0


@pytest.mark.parametrize("kind", te.FORGERIES)
def test_every_forgery_really_changes_the_picture(kind):
    rnd = random.Random(3)
    base = Image.effect_noise((400, 260), 40).convert("RGB")
    donor = Image.effect_noise((400, 260), 90).convert("RGB")
    out = {
        "crop_replace": lambda: te.crop_replace(base, donor, rnd),
        "text_edit": lambda: te.text_edit(base, rnd),
        "inpaint": lambda: te.inpaint(base, rnd),
        "recompress_region": lambda: te.recompress_region(base, rnd),
    }[kind]()
    assert out.size == base.size and out.tobytes() != base.tobytes()


def test_the_tamper_harness_runs_end_to_end_on_the_demo_set(capsys):
    genuine, forged, by_kind = te.demo_sets(12)
    assert genuine and forged and set(by_kind) == set(te.FORGERIES)
    te.report(genuine, forged, 0.05)
    out = capsys.readouterr().out
    assert "AUC" in out and "95% interval" in out and "smoke test" in out


def test_the_tamper_harness_reads_folders_of_real_files_and_skips_what_it_cannot(tmp_path, capsys):
    good = tmp_path / "a.png"
    Image.effect_noise((300, 300), 50).convert("RGB").save(good)
    (tmp_path / "notes.exe").write_bytes(b"MZ" + b"\0" * 100)
    scores = te.folder_scores(str(tmp_path))
    assert len(scores) == 1 and 0.0 <= scores[0] <= 1.0
    assert "skipped notes.exe" in capsys.readouterr().out


def test_the_demo_is_documented_as_checking_the_harness_only():
    """Guard against the demo numbers being quoted as detector quality."""
    assert "NOT how good the detector is" in te.__doc__ and "never commit its images" in te.__doc__
