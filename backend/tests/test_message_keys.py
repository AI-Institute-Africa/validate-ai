"""Payer messages can be shown in the payer's language: a neutral key per message, no accusation."""

import re
from pathlib import Path

from app.claims.service import PAYER_MESSAGE_KEY, REASON_TEXT, explain, explain_keys
from tests.conftest import ecocash_fields, login, make_receipt
from tests.test_flow import _obligation, _submit


def test_one_key_per_message_in_the_same_order():
    codes = [
        "AWAITING_CREDIT",
        "NOT_A_PAYER_REASON",
        "SUSPECTED_FAKE",
        "CREDIT_DISPUTED",
        "PARTIAL_PAYMENT",
    ]
    assert len(explain(codes)) == len(explain_keys(codes)) == 4
    assert explain_keys(codes) == [
        "AWAITING_CREDIT",
        "MANUAL_CHECK",
        "MANUAL_CHECK",
        "PARTIAL_PAYMENT",
    ]


def test_keys_never_hint_at_suspicion():
    for key in set(PAYER_MESSAGE_KEY.values()):
        assert not re.search(r"fake|fraud|suspect|tamper|forg", key, re.I), key


def test_a_payer_gets_keys_that_match_their_messages(client):
    h = login(client, "submitter")
    ob = _obligation(client, h)
    claim = _submit(client, h, ob, make_receipt(ecocash_fields()), declared_amount="40.00")
    assert len(claim["message_keys"]) == len(claim["messages"])
    assert (
        "SUSPECTED_FAKE" not in claim["reason_codes"]
        and "SUSPECTED_FAKE" not in claim["message_keys"]
    )


def test_every_message_has_an_english_screen_text_that_matches_the_server():
    """The console shows `msg.<KEY>` from its dictionaries. English there must equal what the server
    says, or English payers would see different words depending on which side wrote them."""
    src = Path(__file__).resolve().parents[2].joinpath("frontend/src/i18n.tsx").read_text()
    en = src[src.index("export const EN") :]
    for code, text in REASON_TEXT.items():
        key = PAYER_MESSAGE_KEY.get(code, code)
        m = re.search(r'"msg\.' + re.escape(key) + r'":\s*"((?:[^"\\]|\\.)*)"', en)
        assert m, f"frontend has no msg.{key}"
        assert m.group(1).encode().decode("unicode_escape") == text.replace("’", "’"), key
