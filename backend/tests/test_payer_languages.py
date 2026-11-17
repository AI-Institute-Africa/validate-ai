"""Messages sent outside the console speak the payer's language once it is switched on."""

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.claims import messages as pm
from app.claims.service import _payer_text
from app.core.config import get_settings
from app.models import Claim, ClaimState, PayerPref
from tests.conftest import login
from tests.test_flow import _obligation
from tests.test_whatsapp import SENDER, _image, _post, _text, graph  # noqa: F401 - fixture


def _slots(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_every_message_exists_in_all_three_languages_with_the_same_placeholders():
    for key, entry in pm.TEXTS.items():
        assert set(entry) == {"en", "sn", "nd"}, key
        for lang in ("sn", "nd"):
            assert entry[lang].strip() and entry[lang] != entry["en"], (key, lang)
            assert _slots(entry[lang]) == _slots(entry["en"]), (key, lang)


def test_nothing_in_any_language_says_verified_or_hints_at_suspicion():
    for key, entry in pm.TEXTS.items():
        for lang, text in entry.items():
            assert not re.search(r"fake|fraud|suspect|forg|tamper", text, re.I), (key, lang)
        assert "verified" not in entry["en"].lower(), key


def test_language_is_english_until_it_is_switched_on_or_signed_off(monkeypatch):
    s = get_settings()
    assert pm.render("payer.approved", "sn") == pm.TEXTS["payer.approved"]["en"]
    monkeypatch.setattr(s, "payer_message_languages_live", ["sn"])
    assert pm.render("payer.approved", "sn") == pm.TEXTS["payer.approved"]["sn"]
    assert pm.render("payer.approved", "nd") == pm.TEXTS["payer.approved"]["en"]  # not on
    monkeypatch.setattr(s, "payer_message_languages_live", [])
    monkeypatch.setitem(pm.REVIEWED, "nd", {"payer.approved"})  # one signed-off string
    assert pm.render("payer.approved", "nd") == pm.TEXTS["payer.approved"]["nd"]
    assert pm.render("payer.rejected", "nd") == pm.TEXTS["payer.rejected"]["en"]
    monkeypatch.setattr(s, "allow_draft_payer_messages", True)  # staging preview
    assert pm.render("payer.rejected", "nd") == pm.TEXTS["payer.rejected"]["nd"]
    assert pm.render("payer.approved", "xx") == pm.TEXTS["payer.approved"]["en"]  # unknown language
    assert pm.render("payer.approved", None) == pm.TEXTS["payer.approved"]["en"]


def test_production_refuses_to_send_unreviewed_translations():
    from app.core.config import Settings, validate_for_startup

    s = Settings(
        _env_file=None,
        env="prod",
        allow_draft_payer_messages=True,
        jwt_secret="x" * 40,
        clamav_host="clamav",
        vlm_backend="ollama",
        pipeline_mode="celery",
        kyc_face_backend="onnx",
    )
    with pytest.raises(Exception, match="DRAFT_PAYER_MESSAGES"):
        validate_for_startup(s)


def _claim(lang):
    return Claim(payer_lang=lang, reason_codes=["AWAITING_CREDIT"], channel="whatsapp")


def test_state_texts_follow_the_claims_language(monkeypatch):
    monkeypatch.setattr(get_settings(), "payer_message_languages_live", ["sn", "nd"])
    for state, key in (
        (ClaimState.APPROVED, "payer.approved"),
        (ClaimState.REJECTED, "payer.rejected"),
        (ClaimState.NEEDS_INFORMATION, "AWAITING_CREDIT"),
    ):
        for lang in ("en", "sn", "nd"):
            assert _payer_text(_claim(lang), state) == pm.TEXTS[key][lang], (state, lang)
    # a claim with no stored language is English
    assert _payer_text(_claim(None), ClaimState.APPROVED) == pm.TEXTS["payer.approved"]["en"]


def test_a_payer_can_ask_for_a_language_by_name_on_whatsapp(client, graph, session, monkeypatch):  # noqa: F811
    r = _post(client, _text("l1", "Shona"))
    assert r.status_code == 200
    # not switched on: the reply is honest and in English, and the choice is remembered
    assert "not switched on" in graph[-1]["text"]["body"] and "Shona" in graph[-1]["text"]["body"]
    session.rollback()
    row = session.scalars(select(PayerPref)).one()
    assert row.lang == "sn" and SENDER not in row.wa_hash  # a hash, never the number

    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    _post(client, _text("l2", ob["payment_code"]))
    assert "Now send the proof" in graph[-1]["text"]["body"]  # still English while gated

    monkeypatch.setattr(get_settings(), "payer_message_languages_live", ["sn"])
    _post(client, _text("l3", ob["payment_code"]))
    assert graph[-1]["text"]["body"] == pm.TEXTS["wa.send_proof"]["sn"].format(
        code=ob["payment_code"]
    )
    _post(client, _text("l4", "english"))
    assert graph[-1]["text"]["body"] == pm.TEXTS["wa.lang_set"]["en"]
    _post(client, _text("l5", "ndebele"))  # not live: English notice, preference still stored
    assert "Ndebele" in graph[-1]["text"]["body"] and "not switched on" in graph[-1]["text"]["body"]


def test_the_claim_remembers_the_language_the_payer_chose(client, graph, session, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "payer_message_languages_live", ["nd"])
    sub = login(client, "submitter")
    ob = _obligation(client, sub)
    _post(client, _text("m1", "nd"))
    assert graph[-1]["text"]["body"] == pm.TEXTS["wa.lang_set"]["nd"]
    r = _post(client, _image("m2", ob["payment_code"]))
    assert r.json()["claims"] == 1
    assert graph[-1]["text"]["body"] == pm.TEXTS["wa.received"]["nd"].format(
        code=ob["payment_code"]
    )
    session.rollback()
    assert session.scalars(select(Claim)).one().payer_lang == "nd"


def test_console_and_server_use_the_same_words():
    """The console's msg.* drafts and this catalogue must not drift apart."""
    src = Path(__file__).resolve().parents[2].joinpath("frontend/src/i18n.tsx").read_text()

    def block(name):
        start = src.index(
            ("export " if name == "EN" else "") + f"const {name}: Record<string, string> = {{"
        )
        body = src[start : src.index("\n};", start)]
        return {
            k: json.loads('"' + v + '"')
            for k, v in re.findall(r'"(msg\.[A-Z_]+)":\s*"((?:[^"\\]|\\.)*)"', body)
        }

    fe = {"en": block("EN"), "sn": block("SN"), "nd": block("ND")}
    for code in pm._REASON_CODES:
        key = pm.message_key(code)
        for lang in ("en", "sn", "nd"):
            assert fe[lang][f"msg.{key}"] == pm.TEXTS[key][lang], (key, lang)
