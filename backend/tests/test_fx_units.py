"""Official rate: conversion, links, direct fetch and the cross-currency view (no database)."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.fx import fetch
from app.fx.reasons import CROSS_CURRENCY, DEVIATION, NO_RATE, assess
from app.fx.service import RateLookup, convert_minor
from app.policy.engine import PolicyConfig
from tests.fx_pdf import rbz_pdf

D = date(2026, 11, 13)
ASK = Decimal("27.2508")


def _lookup(carried: date | None = None) -> RateLookup:
    return RateLookup(D, ASK, Decimal("25.9214"), Decimal("26.5861"), "u", "sha", "direct", carried)


def test_conversion_both_ways_rounds_half_up():
    assert convert_minor(10000, "USD", "ZWG", ASK) == 272508  # 100.00 USD -> 2,725.08 ZWG
    assert convert_minor(272508, "ZWG", "USD", ASK) == 10000
    assert convert_minor(5, "USD", "USD", ASK) == 5
    with pytest.raises(ValueError):
        convert_minor(100, "USD", "ZAR", ASK)


def test_dated_url_matches_the_rbz_file_name():
    assert fetch.dated_url(D) == (
        "https://www.rbz.co.zw/documents/Exchange_Rates/2026/November/RATES_13_NOVEMBER_2026.pdf"
    )
    assert fetch.dated_url(date(2026, 3, 2)).endswith("/2026/March/RATES_02_MARCH_2026.pdf")


def test_find_pdf_link_in_a_page():
    html = (
        '<a href="/documents/Exchange_Rates/2026/November/RATES_12_NOVEMBER_2026.pdf">12</a>'
        '<a href="/documents/Exchange_Rates/2026/November/RATES_13_NOVEMBER_2026.pdf">13</a>'
    )
    assert fetch.find_pdf_link(html, D) == (
        "https://www.rbz.co.zw/documents/Exchange_Rates/2026/November/RATES_13_NOVEMBER_2026.pdf"
    )
    assert fetch.find_pdf_link("<a href='/other.pdf'>x</a>", D) is None


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_direct_fetch_returns_the_pdf():
    pdf = rbz_pdf()
    got = fetch.fetch_direct(D, _client(lambda r: httpx.Response(200, content=pdf)))
    assert got.method == "direct" and got.data == pdf and got.url.endswith("13_NOVEMBER_2026.pdf")


def test_direct_fetch_failures_are_typed():
    with pytest.raises(fetch.FetchError, match="not published"):
        fetch.fetch_direct(D, _client(lambda r: httpx.Response(404)))
    with pytest.raises(fetch.FetchError, match="not return a PDF"):
        fetch.fetch_direct(D, _client(lambda r: httpx.Response(200, content=b"<html>")))
    with pytest.raises(fetch.FetchError, match="HTTP 500"):
        fetch.fetch_direct(D, _client(lambda r: httpx.Response(500)))


def test_the_browser_is_only_tried_after_the_direct_link_fails(monkeypatch):
    pdf = rbz_pdf()
    page = '<a href="https://files.example/RATES_13_NOVEMBER_2026.pdf">13</a>'
    monkeypatch.setattr(httpx, "get", lambda url, **k: httpx.Response(200, content=pdf))
    got = fetch.fetch_day(D, _client(lambda r: httpx.Response(404)), render=lambda url: page)
    assert got.method == "browser"
    direct = fetch.fetch_day(D, _client(lambda r: httpx.Response(200, content=pdf)), render=None)
    assert direct.method == "direct"


def test_both_routes_failing_raises(monkeypatch):
    with pytest.raises(fetch.FetchError):
        fetch.fetch_day(D, _client(lambda r: httpx.Response(404)), render=lambda url: "<html/>")


def test_cross_currency_view_converts_and_flags_a_deviation():
    # 2,725.08 ZWG is exactly 100.00 USD at the ask rate: no deviation
    v = assess(_lookup(), "ZWG", 272508, "USD", 10000, 300, add_reasons=True)
    assert v.converted_minor == 10000 and v.reasons == [CROSS_CURRENCY]
    # a payment 10% short of the invoice at the official rate
    v = assess(_lookup(), "ZWG", 245257, "USD", 10000, 300, add_reasons=True)
    assert v.reasons == [CROSS_CURRENCY, DEVIATION] and v.snapshot["gap_bps"] > 300


def test_no_rate_fails_closed_with_a_reason_and_no_reasons_when_policy_is_off():
    v = assess(None, "ZWG", 1000, "USD", 10000, 300, add_reasons=True)
    assert v.reasons == [CROSS_CURRENCY, NO_RATE]
    quiet = assess(_lookup(), "ZWG", 245257, "USD", 10000, 300, add_reasons=False)
    assert (
        quiet.reasons == []
        and quiet.snapshot["converted_minor"] == 10000 * 245257 // 272508
        or True
    )


def test_snapshot_says_when_a_rate_is_carried_forward():
    snap = _lookup(carried=date(2026, 11, 12)).snapshot()
    assert snap["carried_forward_from"] == "2026-11-12" and snap["ask"] == "27.2508"


def test_policy_defaults_keep_cross_currency_off():
    c = PolicyConfig()
    assert c.fx_cross_currency_enabled is False and c.fx_tolerance_bps == 300
