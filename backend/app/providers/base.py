import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.normalise.fields import normalise_reference


class LookupFailure(StrEnum):
    BAD_FORMAT = "BAD_FORMAT"  # the reference cannot belong to this provider
    NOT_CONFIGURED = "NOT_CONFIGURED"  # no official API / credentials set up
    TIMEOUT = "TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    NOT_FOUND = "NOT_FOUND"  # the provider answered: no such transaction
    MISMATCH = "MISMATCH"  # the provider answered about a different transaction


@dataclass(frozen=True)
class Record:
    txn_id: str
    amount_minor: int
    currency: str
    status: str


@dataclass(frozen=True)
class Outcome:
    reference: str
    provider: str | None
    record: Record | None = None
    failure: LookupFailure | None = None
    detail: str = ""


# transport(reference) -> raw record dict from the provider's official API; may raise TimeoutError
Transport = Callable[[str], dict]


@dataclass
class Adapter:
    name: str
    id_pattern: str | None  # None = we do not know this provider's reference shape: no opinion
    transport: Transport | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def looks_like(self, reference: str) -> bool | None:
        if self.id_pattern is None:
            return None
        return re.fullmatch(self.id_pattern, reference.strip().upper()) is not None

    def lookup(self, reference: str) -> Outcome:
        ref = normalise_reference(reference) or ""
        if self.looks_like(reference) is False:
            return Outcome(reference, self.name, failure=LookupFailure.BAD_FORMAT)
        if self.transport is None:
            return Outcome(reference, self.name, failure=LookupFailure.NOT_CONFIGURED)
        try:
            raw = self.transport(reference)
        except TimeoutError:
            return Outcome(reference, self.name, failure=LookupFailure.TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - any transport failure is "no evidence"
            return Outcome(
                reference,
                self.name,
                failure=LookupFailure.UPSTREAM_ERROR,
                detail=type(exc).__name__,
            )
        if not raw:
            return Outcome(reference, self.name, failure=LookupFailure.NOT_FOUND)
        try:
            rec = Record(
                txn_id=str(raw["txn_id"]),
                amount_minor=int(raw["amount_minor"]),
                currency=str(raw["currency"]).upper(),
                status=str(raw["status"]),
            )
        except (KeyError, TypeError, ValueError):
            return Outcome(
                reference, self.name, failure=LookupFailure.UPSTREAM_ERROR, detail="shape"
            )
        if normalise_reference(rec.txn_id) != ref:
            # the answer must be about the transaction we asked for
            return Outcome(reference, self.name, failure=LookupFailure.MISMATCH)
        return Outcome(reference, self.name, record=rec)
