"""National ID number checks for the markets we serve.

Idea from adieyal/id_validation (MIT): per-country structure and check digits. Written fresh here.
Each check says what it can prove and how sure we are:

* `ok` False  -> the number cannot be real (shown to a person; never an auto-reject).
* `checksum` "valid" / "invalid" / "unchecked". The Zimbabwe check letter is a community-reverse-
  engineered scheme, not an official one, so it is ADVISORY only and never changes the outcome.
"""

import re
from dataclasses import dataclass
from datetime import date

# Zimbabwe: 2-digit registration district, 6-7 digit serial, check letter, 2-digit origin
_ZW = re.compile(r"(\d{2})(\d{6,7})([A-Z])(\d{2})")
# letters for remainders 1..22; remainder 0 is taken as Z (unverified); I, O, U never used
_ZW_LETTERS = "ABCDEFGHJKLMNPQRSTVWXY"
_ZA = re.compile(r"(\d{2})(\d{2})(\d{2})(\d{4})(\d)(\d)(\d)")


@dataclass
class IdNumberResult:
    ok: bool | None  # None = no opinion
    checksum: str = "unchecked"
    dob: date | None = None
    sex: str | None = None  # "M" | "F" when the number encodes it
    notes: tuple[str, ...] = ()


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0


def _zw(value: str) -> IdNumberResult:
    m = _ZW.fullmatch(re.sub(r"[\s-]", "", value))
    if not m:
        return IdNumberResult(False, notes=("FORMAT",))
    region, serial, letter, _origin = m.groups()
    rem = int(region + serial) % 23
    expected = "Z" if rem == 0 else _ZW_LETTERS[rem - 1] if rem <= 22 else "Z"
    return IdNumberResult(True, "valid" if letter == expected else "invalid")


def _za(value: str, today: date) -> IdNumberResult:
    m = _ZA.fullmatch(value)
    if not m or not _luhn(value):
        return IdNumberResult(False, notes=("FORMAT_OR_CHECK_DIGIT",))
    yy, mm, dd = int(m[1]), int(m[2]), int(m[3])
    # the century is not in the number: take the latest one that is not in the future
    dob = None
    for century in (2000, 1900):
        try:
            cand = date(century + yy, mm, dd)
        except ValueError:
            continue
        if cand <= today:
            dob = cand
            break
    if dob is None:
        return IdNumberResult(False, notes=("BAD_DATE_OF_BIRTH",))
    sex = "M" if int(value[6:10]) >= 5000 else "F"
    return IdNumberResult(True, "valid", dob=dob, sex=sex)


def looks_like_placeholder(value: str) -> bool:
    """All one digit, or a plain run up or down (11111111, 12345678): what people type when they
    invent a number. A real holder is possible but very unlikely, so it goes to a person."""
    d = re.sub(r"\D", "", value)
    if len(d) < 6:
        return False
    if len(set(d)) == 1:
        return True
    steps = {(int(b) - int(a)) % 10 for a, b in zip(d, d[1:], strict=False)}
    return steps in ({1}, {9})


# Kenya (7-8 digits) and the Ghana Card (GHA-#########-#) have NO published check digit: nothing
# offline can prove a number was issued. We check shape and obvious inventions only; whether the
# holder exists needs the registry (NIA, IPRS) or a licensed provider such as Smile ID or uqudo.
_SIMPLE = {
    "KEN": r"\d{7,8}",
    "NGA": r"\d{11}",
    "GHA": r"GHA-?\d{9}-?\d",
    "ZMB": r"\d{6}/\d{2}/\d",
    "TZA": r"\d{8}-?\d{5}-?\d{5}-?\d{2}",
    "UGA": r"C[MF][A-Z0-9]{12}",
}


def check(country: str | None, number: str | None, today: date | None = None) -> IdNumberResult:
    if not country or not number:
        return IdNumberResult(None)
    value = number.strip().upper()
    today = today or date.today()
    if country == "ZWE":
        return _zw(value)
    if country == "ZAF":
        return _za(value, today)
    pattern = _SIMPLE.get(country)
    if pattern is None:
        return IdNumberResult(None)
    if not re.fullmatch(pattern, value):
        return IdNumberResult(False, notes=("FORMAT",))
    if looks_like_placeholder(value):
        return IdNumberResult(False, notes=("PLACEHOLDER",))
    return IdNumberResult(True)
