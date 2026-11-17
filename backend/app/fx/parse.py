"""Read the Reserve Bank of Zimbabwe's daily exchange-rate PDF.

The file has one page of rates. A date line ("Friday, 13 November 2026") sits above a table with the
columns CURRENCY, INDICES, BID, ASK, MID RATE, then BID RATE, ASK RATE, MID RATE in ZWG. Under the
heading INTERBANK RATE the first data row is USD, for example

    USD  1  1  1.0000  25.9214  27.2508  26.5861

We take the ASK RATE (27.2508 ZiG per 1 USD on 13 November 2026). If the date, the headings or the
row are not what we expect, we raise LayoutChanged instead of guessing: a wrong rate is worse than
none, and the caller alerts an administrator.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_DATE = re.compile(
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?,?\s*"
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    re.I,
)
_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")


class LayoutChanged(Exception):
    """The file does not look like the published rates table."""


@dataclass(frozen=True)
class RbzRate:
    rate_date: date
    bid: Decimal
    ask: Decimal
    mid: Decimal


def _dec(token: str) -> Decimal:
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation as exc:
        raise LayoutChanged(f"not a number: {token!r}") from exc


def parse_date_line(text: str) -> date:
    for m in _DATE.finditer(text):
        month = MONTHS.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                continue
    raise LayoutChanged("no date line found")


Word = tuple[float, float, float, float, str]  # x0, y0, x1, y1, text


def _lines(words: list[Word]) -> list[list[Word]]:
    """Group words into lines by vertical position, left to right."""
    out: list[list[Word]] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        mid = (w[1] + w[3]) / 2
        if out and abs(((out[-1][0][1] + out[-1][0][3]) / 2) - mid) <= 3.0:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w[0]) for line in out]


def _bigram_centre(line: list[Word], first: str) -> float | None:
    """Centre of the LAST heading '<first> RATE' on the line, if present.

    MID RATE appears twice (index columns, then rate columns); the rate columns are on the right.
    """
    centre = None
    for a, b in zip(line, line[1:], strict=False):
        if a[4].upper() == first and b[4].upper() == "RATE":
            centre = (a[0] + b[2]) / 2
    return centre


def parse_words(words: list[Word], page_text: str) -> RbzRate:
    rate_date = parse_date_line(page_text)
    lines = _lines(words)
    centres: dict[str, float] = {}
    header_index = -1
    for i, line in enumerate(lines):
        found = {k: _bigram_centre(line, k) for k in ("BID", "ASK", "MID")}
        if found["BID"] is not None and found["ASK"] is not None:
            centres = {k: v for k, v in found.items() if v is not None}
            header_index = i
            break
    if header_index < 0:
        raise LayoutChanged("headings BID RATE and ASK RATE not found")
    names = " ".join(w[4].upper() for line in lines[: header_index + 1] for w in line)
    for needed in ("CURRENCY", "INDICES"):
        if needed not in names:
            raise LayoutChanged(f"heading {needed} not found")

    row: list[Word] | None = None
    seen_interbank = False
    for line in lines[header_index + 1 :]:
        text = " ".join(w[4].upper() for w in line)
        if "INTERBANK" in text:
            seen_interbank = True
            continue
        if seen_interbank and line[0][4].upper() == "USD":
            row = line
            break
    if row is None:
        raise LayoutChanged("INTERBANK RATE / USD row not found")

    numbers = [w for w in row[1:] if _NUMBER.match(w[4])]
    if len(numbers) < 4:
        raise LayoutChanged("USD row has too few numbers")

    def pick(key: str) -> Decimal:
        centre = centres.get(key)
        if centre is None:
            raise LayoutChanged(f"heading {key} RATE not found")
        best = min(numbers, key=lambda w: abs((w[0] + w[2]) / 2 - centre))
        return _dec(best[4])

    bid, ask = pick("BID"), pick("ASK")
    mid = pick("MID") if "MID" in centres else (bid + ask) / 2
    return RbzRate(rate_date=rate_date, bid=bid, ask=ask, mid=mid)


def parse_pdf(data: bytes) -> RbzRate:
    """Parse the PDF bytes. Imports pymupdf lazily (it is a runtime dependency)."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - any unreadable file is a layout problem
        raise LayoutChanged(f"not a readable PDF: {exc}") from exc
    try:
        if doc.page_count < 1:
            raise LayoutChanged("PDF has no pages")
        page = doc[0]
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
        return parse_words(words, page.get_text())
    finally:
        doc.close()


def validate(
    rate: RbzRate,
    requested: date,
    previous_ask: Decimal | None = None,
    max_move_pct: float = 25.0,
) -> None:
    """Raise LayoutChanged unless the rate is plausible for the day asked for."""
    if rate.rate_date != requested:
        raise LayoutChanged(f"file is dated {rate.rate_date}, expected {requested}")
    if rate.bid <= 0 or rate.ask <= 0 or rate.mid <= 0:
        raise LayoutChanged("rates must be positive")
    if rate.ask < rate.bid:
        raise LayoutChanged("ask rate is below bid rate")
    if previous_ask is not None and previous_ask > 0:
        move = abs(rate.ask - previous_ask) / previous_ask * 100
        if move > Decimal(str(max_move_pct)):
            raise LayoutChanged(
                f"ask rate moved {move:.1f}% from the previous day (limit {max_move_pct}%)"
            )
