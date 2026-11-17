"""Is the recipient printed on a receipt one of the payees we trust?

The bank gate only proves money landed in OUR account. A receipt can still show a payment to
somebody else's wallet (a payer who paid a fraudster, or an edited receipt), so we also compare the
printed recipient with the organisation's `trusted_payees` (names, wallet numbers, merchant codes).
Empty list = no opinion. Numbers are compared by their last nine digits so +263 77.. and 077..
agree; names by their letters and digits, so punctuation and case do not matter.
"""

import re

_DIGITS = re.compile(r"\d")


def _digits(s: str) -> str:
    return "".join(_DIGITS.findall(s))


def normalise_payee(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _is_number(s: str) -> bool:
    d = _digits(s)
    return len(d) >= 9 and len(d) >= len(re.sub(r"[^A-Za-z0-9]", "", s)) - 2


def same_payee(a: str, b: str) -> bool:
    """Do two printed recipients name the same payee?"""
    if _is_number(a) and _is_number(b):
        return _digits(a)[-9:] == _digits(b)[-9:]
    na, nb = normalise_payee(a), normalise_payee(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    return len(short) >= 5 and short in long_  # "COGNIFYMAIN" in "COGNIFYMAINACCOUNT"


def is_trusted(value: str, trusted: list[str]) -> bool:
    return any(same_payee(value, t) for t in trusted)
