"""Official rate service on a real database: the daily run, history, carry-forward, manual entry."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app.core.db import get_sessionmaker
from app.fx import fetch, service
from app.models import FxFetchLog, FxRate, OutboxEvent
from tests.conftest import login
from tests.fx_pdf import rbz_pdf

FRI = date(2026, 11, 13)


def _fetcher(pdf: bytes):
    return lambda d: fetch.Fetched(pdf, fetch.dated_url(d), "direct")


def _org(client):
    login(client, "admin")  # creates the organisation the alerts go to


def test_daily_run_stores_the_ask_rate_and_the_pdf(client, session):
    out = service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf()))
    session.commit()
    assert out == "stored"
    row = session.scalars(select(FxRate)).one()
    assert row.rate_date == FRI and row.ask == Decimal("27.2508") and row.pdf_sha256
    assert session.scalars(select(FxFetchLog)).one().outcome == "stored"
    assert service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf())) == "already"


def test_weekends_are_skipped(client, session):
    assert service.run_daily(session, date(2026, 11, 14), fetch=_fetcher(rbz_pdf())) == "skipped"
    assert session.scalars(select(FxRate)).first() is None


def test_missing_file_is_logged_and_alerts_only_on_the_last_attempt(client, session):
    _org(client)

    def gone(d):
        raise fetch.FetchError("not published")

    assert service.run_daily(session, FRI, fetch=gone) == "missing"
    assert (
        session.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "ops.fx_alert")).first()
        is None
    )
    assert service.run_daily(session, FRI, fetch=gone, last_attempt=True) == "missing"
    session.commit()
    assert session.scalars(
        select(OutboxEvent).where(OutboxEvent.event_type == "ops.fx_alert")
    ).first()


def test_a_changed_layout_is_not_used_and_alerts(client, session):
    _org(client)
    out = service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf(headings=False)))
    session.commit()
    assert out == "layout_changed"
    assert session.scalars(select(FxRate)).first() is None
    assert session.scalars(
        select(OutboxEvent).where(OutboxEvent.event_type == "ops.fx_alert")
    ).first()


def test_a_big_jump_is_refused(client, session):
    service.run_daily(
        session,
        FRI - timedelta(days=1),
        fetch=_fetcher(
            rbz_pdf(
                date_line="Thursday, 12 November 2026", usd=("1", "1", "1", "10.0", "11.0", "10.5")
            )
        ),
    )
    session.commit()
    assert service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf())) == "layout_changed"


def test_carry_forward_over_a_weekend_is_flagged_and_limited(client, session):
    service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf()))
    session.commit()
    sat = service.get_rate(session, date(2026, 11, 14))
    assert sat and sat.ask == Decimal("27.2508") and sat.carried_from == FRI
    assert service.get_rate(session, FRI).carried_from is None
    assert service.get_rate(session, date(2026, 11, 20), max_age_days=4) is None


def test_rates_are_append_only(client, session):
    service.run_daily(session, FRI, fetch=_fetcher(rbz_pdf()))
    session.commit()
    s2 = get_sessionmaker()()
    try:
        try:
            s2.execute(text("UPDATE fx_rates SET ask = 1"))
            s2.commit()
            raise AssertionError("update should have been refused")
        except AssertionError:
            raise
        except Exception:
            s2.rollback()
    finally:
        s2.close()


def test_manual_rate_needs_an_approver_and_a_reason_and_wins_for_its_day(client, session):
    rev, appr = login(client, "reviewer"), login(client, "approver")
    body = {
        "rate_date": "2026-11-13",
        "ask": "27.5",
        "reason": "RBZ site down; rate read from the bulletin",
    }
    assert client.post("/admin/fx/manual", headers=rev, json=body).status_code == 403
    assert (
        client.post("/admin/fx/manual", headers=appr, json={**body, "reason": "short"}).status_code
        == 422
    )
    ok = client.post("/admin/fx/manual", headers=appr, json=body)
    assert ok.status_code == 201, ok.text
    got = client.get("/fx/rates?on=2026-11-13", headers=rev).json()
    assert got["ask"] == "27.500000" and got["method"] == "manual"
    assert client.get("/fx/rates?on=2030-01-01", headers=rev).status_code == 404
