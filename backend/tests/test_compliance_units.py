"""Incident clock, config rules and the docs switch (no database)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.compliance.incidents import stage_for
from app.core.config import ConfigError, Settings, validate_for_startup
from app.policy.engine import PolicyConfig


def test_reminder_stages_follow_the_24_hour_clock():
    t0 = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)
    at = lambda h: t0 + timedelta(hours=h)  # noqa: E731
    assert stage_for(t0, at(1)) is None
    assert stage_for(t0, at(11.9)) is None
    assert stage_for(t0, at(12)) == "12h"
    assert stage_for(t0, at(19.9)) == "12h"
    assert stage_for(t0, at(20)) == "20h"
    assert stage_for(t0, at(24)) == "overdue"
    assert stage_for(t0, at(100)) == "overdue"


def test_retention_is_off_by_default_and_has_a_floor():
    c = PolicyConfig()
    assert c.evidence_retention_days is None and c.alert_body_retention_days is None
    with pytest.raises(ValueError):
        PolicyConfig(evidence_retention_days=5)
    assert PolicyConfig(evidence_retention_days=90).evidence_retention_days == 90


def _prod(**kw) -> Settings:
    base = dict(
        env="prod",
        jwt_secret="x" * 40,
        clamav_host="clamav",
        pipeline_mode="celery",
        vlm_backend="ollama",
        kyc_face_backend="onnx",
        ollama_url="http://ollama:11434",
    )
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_production_must_name_where_the_data_lives():
    with pytest.raises(ConfigError, match="POPS_DATA_REGION"):
        validate_for_startup(_prod())
    validate_for_startup(_prod(data_region="ZA-af-south-1"))


def test_api_docs_are_on_in_dev_and_off_in_production_unless_asked():
    assert Settings(_env_file=None, env="dev").docs_on is True
    assert _prod().docs_on is False
    assert _prod(docs_enabled=True).docs_on is True
    assert Settings(_env_file=None, env="dev", docs_enabled=False).docs_on is False
