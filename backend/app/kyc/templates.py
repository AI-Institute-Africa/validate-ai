"""Deterministic reading of identity-document text, and per-country number formats.

Counterpart of `extraction/templates.py` for IDs: the second reader (Tesseract) uses `parse_text`
to turn OCR text into fields, and `number_format_ok` tells the rules whether a national ID number
looks like that country's format. Formats are data: extend the tables, not the logic.
"""

import re

from app.kyc import idnumbers

COUNTRY_NAMES = {
    "ZIMBABWE": "ZWE",
    "KENYA": "KEN",
    "SOUTH AFRICA": "ZAF",
    "NIGERIA": "NGA",
    "GHANA": "GHA",
    "ZAMBIA": "ZMB",
    "TANZANIA": "TZA",
    "UGANDA": "UGA",
    "MALAWI": "MWI",
    "BOTSWANA": "BWA",
    "MOZAMBIQUE": "MOZ",
    "NAMIBIA": "NAM",
    "RWANDA": "RWA",
    "ETHIOPIA": "ETH",
    "EGYPT": "EGY",
    "UNITED KINGDOM": "GBR",
    "UNITED STATES": "USA",
}
_ISO3 = set(COUNTRY_NAMES.values())

_LABELS = {
    "surname": r"(?:SURNAME|FAMILY NAME|LAST NAME)",
    "given_names": r"(?:GIVEN NAMES?|FIRST NAMES?|FORENAMES?)",
    "date_of_birth": r"(?:DATE OF BIRTH|BIRTH DATE|D\.?O\.?B\.?)",
    "expiry_date": (
        r"(?:DATE OF EXPIRY|EXPIRY DATE|EXPIRY|EXPIRES|VALID UNTIL|VALID TO|DATE OF EXP)"
    ),
    "document_number": (
        r"(?:ID NUMBER|ID NO|NATIONAL ID(?: NO| NUMBER)?|DOCUMENT (?:NO|NUMBER)"
        r"|PASSPORT (?:NO|NUMBER)|LICEN[CS]E (?:NO|NUMBER)|CARD (?:NO|NUMBER)|NIN)"
    ),
}
_SEP = r"\.?\s*[:\-]?\s*"


def _value(text: str, label: str, shape: str = r".+") -> str | None:
    m = re.search(rf"(?im)(?<![A-Z]){label}{_SEP}({shape})$", text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def parse_text(text: str) -> dict[str, str]:
    """Fields from the labelled lines of an ID's OCR text (English layouts)."""
    out: dict[str, str] = {}
    for name, label in _LABELS.items():
        shape = r"[A-Z0-9][A-Z0-9 \-/]{4,24}" if name == "document_number" else r".+"
        if name in ("date_of_birth", "expiry_date"):
            shape = r"[0-9A-Za-z][0-9A-Za-z .\-/]{5,20}"
        v = _value(text, label, shape)
        if v:
            out[name] = v
    if "surname" not in out:  # plain "NAME:" holds the full name
        v = _value(text, r"(?:FULL NAME|NAME)")
        if v:
            out["full_name"] = v
    sex = re.search(r"(?im)(?<![A-Z])(?:SEX|GENDER)\s*[:\-]?\s*([MF])\b", text)
    if sex:
        out["sex"] = sex.group(1).upper()
    upper = text.upper()
    for name, iso in COUNTRY_NAMES.items():
        if name in upper:
            out["issuing_country"] = iso
            break
    for doc_type, words in (
        ("passport", ("PASSPORT",)),
        ("drivers_licence", ("DRIVING LICEN", "DRIVER", "DRIVERS LICEN")),
        ("national_id", ("NATIONAL ID", "IDENTITY CARD", "IDENTITY", "ID CARD")),
    ):
        if any(w in upper for w in words):
            out["doc_type"] = doc_type
            break
    return out


def normalise_country(raw: str | None) -> str | None:
    """ISO alpha-3 from a code or a country name; None when unknown."""
    if not raw:
        return None
    v = re.sub(r"[^A-Za-z ]", "", raw).strip().upper()
    if v in _ISO3 or (len(v) == 3 and v.isalpha()):
        return v
    return COUNTRY_NAMES.get(v)


def number_format_ok(country: str | None, doc_type: str | None, number: str | None) -> bool | None:
    """Can this national ID number be real for its country? None = no opinion (unknown country,
    not a national ID, or no number). Details and advisory checks live in `kyc.idnumbers`."""
    if doc_type != "national_id":
        return None
    return idnumbers.check(country, number).ok
