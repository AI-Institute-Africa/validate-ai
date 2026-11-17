"""Pilot scorecard helpers and the training-consent rule (no database)."""

from datetime import timedelta

import pytest

from app.analytics.pilot import estimate_minutes_saved, median_minutes
from app.analytics.training import ConsentMissing, require_consent
from app.policy.engine import PolicyConfig


def test_median_minutes():
    assert median_minutes([]) is None
    assert (
        median_minutes([timedelta(minutes=2), timedelta(minutes=10), timedelta(minutes=4)]) == 4.0
    )
    assert median_minutes([timedelta(seconds=90), timedelta(seconds=30)]) == 1.0


def test_time_saved_is_a_labelled_estimate_that_never_goes_negative():
    assert estimate_minutes_saved(800, 2) == 1600
    assert estimate_minutes_saved(-3, 2) == 0
    assert estimate_minutes_saved(10, -1) == 0


def test_training_export_is_off_until_consent_is_on_record():
    cfg = PolicyConfig()
    assert cfg.training_export_consent is False and cfg.pilot_minutes_per_manual_check == 2
    with pytest.raises(ConsentMissing):
        require_consent(cfg)
    with pytest.raises(ConsentMissing):
        require_consent(PolicyConfig(training_export_consent=True))
    with pytest.raises(ConsentMissing):
        require_consent(PolicyConfig(training_export_consent=True, training_consent_ref="  "))
    ok = PolicyConfig(training_export_consent=True, training_consent_ref="AGR-2026-014")
    assert require_consent(ok) == "AGR-2026-014"
