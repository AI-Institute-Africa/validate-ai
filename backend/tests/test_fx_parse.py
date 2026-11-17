"""RBZ rate PDF parsing and validation: no database."""

from datetime import date
from decimal import Decimal

import pytest

from app.fx.parse import LayoutChanged, parse_date_line, parse_pdf, validate
from tests.fx_pdf import rbz_pdf

D = date(2026, 11, 13)


def test_reads_the_ask_rate_of_the_13_november_2026_layout():
    r = parse_pdf(rbz_pdf())
    assert r.rate_date == D
    assert r.ask == Decimal("27.2508")
    assert r.bid == Decimal("25.9214")
    assert r.mid == Decimal("26.5861")


def test_ask_is_taken_from_the_ask_rate_column_not_the_index_ask():
    # the index columns also say 1 and 1.0000; the rate columns are the ones that matter
    assert parse_pdf(rbz_pdf()).ask != Decimal("1")


def test_date_line_variants():
    assert parse_date_line("Monday, 3 November 2026") == date(2026, 11, 3)
    assert parse_date_line("Friday 13 NOVEMBER 2026") == D
    with pytest.raises(LayoutChanged):
        parse_date_line("Exchange rates for today")


def test_changed_layouts_fail_loudly():
    with pytest.raises(LayoutChanged, match="headings"):
        parse_pdf(rbz_pdf(headings=False))
    with pytest.raises(LayoutChanged, match="INTERBANK"):
        parse_pdf(rbz_pdf(interbank=False))
    with pytest.raises(LayoutChanged, match="date"):
        parse_pdf(rbz_pdf(date_line="Rates"))
    with pytest.raises(LayoutChanged, match="PDF"):
        parse_pdf(b"not a pdf")


def test_usd_row_is_found_even_with_another_currency_above_it():
    assert parse_pdf(rbz_pdf(extra_row_first=True)).ask == Decimal("27.2508")


def test_validate_date_sign_order_and_daily_move():
    r = parse_pdf(rbz_pdf())
    validate(r, D)
    validate(r, D, previous_ask=Decimal("27.0000"))
    with pytest.raises(LayoutChanged, match="dated"):
        validate(r, date(2026, 11, 12))
    with pytest.raises(LayoutChanged, match="moved"):
        validate(r, D, previous_ask=Decimal("10.0"), max_move_pct=25.0)
    with pytest.raises(LayoutChanged, match="below bid"):
        validate(parse_pdf(rbz_pdf(usd=("1", "1", "1", "30.0000", "27.0000", "28.0"))), D)
