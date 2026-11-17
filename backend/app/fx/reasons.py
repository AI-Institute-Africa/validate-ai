"""What the official rate says about a claim paid in a different currency from its invoice.

The currency gate in matching stays strict: a ZWG credit never settles a USD invoice by itself. With
the service on, such a claim gets an explanation a reviewer can use: the amount converted at the
official ask rate and how far it is from the invoice. Reasons are only added when the organisation's
policy turns `fx_cross_currency_enabled` on; the snapshot is recorded either way.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.fx.service import PAIR, RateLookup, convert_minor, get_rate
from app.policy.engine import PolicyConfig

CROSS_CURRENCY = "CROSS_CURRENCY_AT_OFFICIAL_RATE"
DEVIATION = "RATE_DEVIATION"
NO_RATE = "NO_OFFICIAL_RATE"


@dataclass
class CrossCurrencyView:
    reasons: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)
    converted_minor: int | None = None


def assess(
    lookup: RateLookup | None,
    payment_currency: str,
    payment_minor: int | None,
    invoice_currency: str,
    invoice_minor: int,
    tolerance_bps: int,
    *,
    add_reasons: bool,
) -> CrossCurrencyView:
    """Pure core: compare the payment, converted into the invoice currency, with the invoice."""
    view = CrossCurrencyView()
    if lookup is None:
        view.snapshot = {"pair": "USD/ZWG", "available": False}
        if add_reasons:
            view.reasons = [CROSS_CURRENCY, NO_RATE]
        return view
    view.snapshot = lookup.snapshot()
    if payment_minor is None:
        if add_reasons:
            view.reasons = [CROSS_CURRENCY]
        return view
    converted = convert_minor(payment_minor, payment_currency, invoice_currency, lookup.ask)
    view.converted_minor = converted
    view.snapshot.update(
        {
            "payment": {"currency": payment_currency, "minor": payment_minor},
            "converted_minor": converted,
            "invoice_minor": invoice_minor,
        }
    )
    if add_reasons:
        view.reasons = [CROSS_CURRENCY]
        gap_bps = abs(converted - invoice_minor) * 10000 / max(invoice_minor, 1)
        view.snapshot["gap_bps"] = round(gap_bps, 1)
        if gap_bps > tolerance_bps:
            view.reasons.append(DEVIATION)
    return view


def cross_currency_view(
    session: Session,
    *,
    payment_currency: str | None,
    payment_minor: int | None,
    invoice_currency: str,
    invoice_minor: int,
    on: date,
    cfg: PolicyConfig,
) -> CrossCurrencyView | None:
    """None unless the payment and invoice are in different currencies of the official pair."""
    if not payment_currency:
        return None
    pair = {PAIR[0], PAIR[1]}
    if payment_currency == invoice_currency or not {payment_currency, invoice_currency} <= pair:
        return None
    return assess(
        get_rate(session, on, cfg.fx_max_rate_age_days),
        payment_currency,
        payment_minor,
        invoice_currency,
        invoice_minor,
        cfg.fx_tolerance_bps,
        add_reasons=cfg.fx_cross_currency_enabled,
    )


def gap_text(gap_bps: float | Decimal) -> str:
    return f"{float(gap_bps) / 100:.1f}%"
