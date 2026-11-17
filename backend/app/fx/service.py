"""Official daily exchange rates: store, look up, convert, and the daily fetch run.

The rate used is the RBZ interbank ASK rate, ZWG per 1 USD. This module never moves money: it
supplies a number and its evidence. Callers that find no rate treat the case as unknown and let a
person decide; nothing here guesses or reuses an old rate silently (an older rate is returned only
inside `max_age_days`, and says which day it is from).
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.security import Principal
from app.entitlements.outbox import enqueue_event
from app.fx import fetch as fetcher
from app.fx.parse import LayoutChanged, RbzRate, parse_pdf, validate
from app.intake.storage import get_storage
from app.models import FxFetchLog, FxRate, Organisation

log = logging.getLogger(__name__)

PAIR = ("USD", "ZWG")


@dataclass(frozen=True)
class RateLookup:
    rate_date: date  # the day the rate is for
    ask: Decimal
    bid: Decimal
    mid: Decimal
    source_url: str | None
    pdf_sha256: str | None
    method: str
    carried_from: date | None  # set when no rate exists for the asked day and this is older

    def snapshot(self) -> dict[str, Any]:
        return {
            "pair": "USD/ZWG",
            "rate_date": self.rate_date.isoformat(),
            "ask": str(self.ask),
            "source_sha256": self.pdf_sha256,
            "method": self.method,
            "carried_forward_from": self.carried_from.isoformat() if self.carried_from else None,
        }


def _latest(session: Session, on: date) -> FxRate | None:
    return session.scalars(
        select(FxRate)
        .where(FxRate.rate_date == on)
        .order_by(FxRate.fetched_at.desc(), FxRate.rate_id)
        .limit(1)
    ).first()


def _lookup(row: FxRate, asked: date) -> RateLookup:
    return RateLookup(
        rate_date=asked,
        ask=row.ask,
        bid=row.bid,
        mid=row.mid,
        source_url=row.source_url,
        pdf_sha256=row.pdf_sha256,
        method=row.method,
        carried_from=None if row.rate_date == asked else row.rate_date,
    )


def get_rate(session: Session, on: date, max_age_days: int = 4) -> RateLookup | None:
    """The official rate for `on`, or the newest earlier one within `max_age_days` (flagged)."""
    row = _latest(session, on)
    if row is None:
        row = session.scalars(
            select(FxRate)
            .where(FxRate.rate_date < on, FxRate.rate_date >= on - timedelta(days=max_age_days))
            .order_by(FxRate.rate_date.desc(), FxRate.fetched_at.desc())
            .limit(1)
        ).first()
    return _lookup(row, on) if row else None


def convert_minor(amount_minor: int, src: str, dst: str, ask: Decimal) -> int:
    """Convert minor units between USD and ZWG at the ask rate (ZWG per USD), half-up."""
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return amount_minor
    if (src, dst) == PAIR:
        value = Decimal(amount_minor) * ask
    elif (src, dst) == (PAIR[1], PAIR[0]):
        value = Decimal(amount_minor) / ask
    else:
        raise ValueError(f"no official rate for {src} to {dst}")
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def store_rate(
    session: Session, rate: RbzRate, *, url: str, data: bytes, method: str
) -> tuple[FxRate, bool]:
    """Save a day's rate and its PDF. Returns (row, republished): True when the same day was
    already stored from a different file, which an administrator should look at."""
    sha = hashlib.sha256(data).hexdigest()
    existing = _latest(session, rate.rate_date)
    if existing is not None and existing.pdf_sha256 == sha:
        return existing, False
    key = f"fx/{rate.rate_date.isoformat()}/{sha[:16]}.pdf"
    get_storage().put(key, data, "application/pdf")
    row = FxRate(
        rate_date=rate.rate_date,
        bid=rate.bid,
        ask=rate.ask,
        mid=rate.mid,
        source_url=url,
        pdf_sha256=sha,
        pdf_object_key=key,
        method=method,
    )
    session.add(row)
    session.flush()
    return row, existing is not None and existing.method != "manual"


def record_manual(
    session: Session, p: Principal, on: date, ask: Decimal, bid: Decimal | None, reason: str
) -> FxRate:
    """An approver enters a rate by hand (for example while the RBZ site is down)."""
    if ask <= 0:
        raise ValueError("the rate must be positive")
    row = FxRate(
        rate_date=on,
        bid=bid or ask,
        ask=ask,
        mid=((bid or ask) + ask) / 2,
        method="manual",
        entered_by=p.actor,
        reason=reason,
    )
    session.add(row)
    session.flush()
    audit(
        session,
        actor=p.actor,
        action="fx.manual_rate",
        entity_type="fx_rate",
        entity_id=row.rate_id,
        org_id=p.org_id,
        after={"rate_date": on.isoformat(), "ask": str(ask), "reason": reason},
    )
    return row


def notify_admins(session: Session, text: str, key: str) -> None:
    """Tell every organisation's admins (once per key). The rate is platform-wide."""
    for org_id in session.scalars(select(Organisation.org_id)):
        enqueue_event(session, org_id, "ops.fx_alert", f"{key}:{org_id}", {"text": text})


def _log(session: Session, d: date, outcome: str, detail: str | None, method: str | None) -> None:
    session.add(FxFetchLog(for_date=d, outcome=outcome, detail=detail, method=method))


def run_daily(
    session: Session,
    d: date,
    *,
    fetch: Callable[[date], fetcher.Fetched] = fetcher.fetch_day,
    max_move_pct: float = 25.0,
    last_attempt: bool = False,
) -> str:
    """Fetch, check and store the rate for working day `d`. Returns the outcome word:
    skipped | already | stored | republished | missing | layout_changed.
    """
    if d.weekday() >= 5:
        return "skipped"  # weekends: the last published rate carries forward
    current = _latest(session, d)
    if current is not None and current.method != "manual":
        return "already"
    try:
        got = fetch(d)
    except fetcher.FetchError as exc:
        _log(session, d, "missing", str(exc), None)
        if last_attempt:
            notify_admins(
                session,
                f"The RBZ exchange rate for {d} could not be fetched today ({exc}). "
                "Enter it by hand if it is needed.",
                f"fx:{d}:missing",
            )
        return "missing"
    try:
        parsed = parse_pdf(got.data)
        prev = session.scalars(
            select(FxRate.ask)
            .where(FxRate.rate_date < d)
            .order_by(FxRate.rate_date.desc(), FxRate.fetched_at.desc())
            .limit(1)
        ).first()
        validate(parsed, d, previous_ask=prev, max_move_pct=max_move_pct)
    except LayoutChanged as exc:
        _log(session, d, "layout_changed", str(exc), got.method)
        notify_admins(
            session,
            f"The RBZ exchange-rate file for {d} did not look as expected ({exc}). The rate was "
            "not used.",
            f"fx:{d}:layout",
        )
        return "layout_changed"
    row, republished = store_rate(session, parsed, url=got.url, data=got.data, method=got.method)
    _log(session, d, "republished" if republished else "stored", None, got.method)
    if republished:
        notify_admins(
            session,
            f"The RBZ exchange-rate file for {d} changed after it was first stored.",
            f"fx:{d}:republished:{row.pdf_sha256}",
        )
    return "republished" if republished else "stored"
