"""No outside AI services: the allow-list and the production start-up refusal (no database)."""

import httpx
import pytest

from app.core import ai_http
from app.core.config import ConfigError, Settings, validate_for_startup

STRONG = "x" * 40


def _prod(**over) -> Settings:
    base = dict(
        env="prod",
        data_region="ZA-test",
        jwt_secret=STRONG,
        clamav_host="clamav",
        pipeline_mode="celery",
        vlm_backend="ollama",
        ollama_url="http://ollama:11434",
        kyc_face_backend="onnx",
    )
    base.update(over)
    return Settings(**base)


def test_private_hosts_are_always_allowed():
    for url in (
        "http://ollama:11434",
        "http://10.0.0.5:11434",
        "http://192.168.1.2",
        "http://localhost:11434",
        "http://gpu.internal:8000",
        "http://172.20.1.1",
    ):
        assert ai_http.host_allowed(url, [])


def test_outside_hosts_need_to_be_listed():
    assert not ai_http.host_allowed("https://ollama.com", [])
    assert ai_http.host_allowed("https://ollama.com", ["ollama.com"])
    assert ai_http.host_allowed("https://api.models.example.org", ["example.org"])
    assert not ai_http.host_allowed("https://evilexample.org", ["example.org"])  # not a subdomain


def test_check_refuses_in_production_but_not_in_dev():
    prod = _prod()
    with pytest.raises(ai_http.AiBlocked):
        ai_http.check("https://ollama.com/api/chat", prod)
    ai_http.check("http://ollama:11434/api/chat", prod)
    ai_http.check("https://ollama.com/api/chat", Settings(env="dev"))


def test_blocked_call_is_an_http_error_so_readers_fail_closed():
    assert issubclass(ai_http.AiBlocked, httpx.HTTPError)


def test_post_sends_nothing_when_blocked(monkeypatch):
    sent = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(ai_http, "get_settings", lambda: _prod())
    with pytest.raises(ai_http.AiBlocked):
        ai_http.post("https://ollama.com/api/chat", json={})
    assert sent == []
    ai_http.post("http://ollama:11434/api/chat", json={})
    assert len(sent) == 1


def test_startup_refuses_an_outside_model_url_and_any_hosted_key():
    validate_for_startup(_prod())
    with pytest.raises(ConfigError, match="POPS_OLLAMA_URL"):
        validate_for_startup(_prod(ollama_url="https://ollama.com"))
    validate_for_startup(_prod(ollama_url="https://ollama.com", ai_allowed_hosts=["ollama.com"]))
    with pytest.raises(ConfigError, match="API_KEY"):
        validate_for_startup(_prod(ollama_api_key="secret"))


def test_startup_refuses_the_browser_lookup_until_its_model_is_confirmed():
    kw = dict(
        lookup_mode="shadow", lookup_backend="browser", lookup_allowed_domains=["pay.example"]
    )
    with pytest.raises(ConfigError, match="LOOKUP_BACKEND=browser"):
        validate_for_startup(_prod(**kw))
    validate_for_startup(_prod(lookup_browser_allowed=True, **kw))


def test_endpoint_listing_flags_external_ones():
    s = _prod(ollama_url="https://ollama.com")
    row = ai_http.endpoints(s)[0]
    assert row["external"] and not row["allowed"]
