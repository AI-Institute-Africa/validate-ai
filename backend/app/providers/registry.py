"""Known providers and a bounded-concurrency batch verify with one result per input."""

from concurrent.futures import ThreadPoolExecutor

from app.providers.base import Adapter, LookupFailure, Outcome

# Only EcoCash's shape is known to us (it matches our sample receipts: PP251021.1432.A12345).
# The others declare no pattern rather than a guessed one; add a pattern when it is confirmed.
ADAPTERS: dict[str, Adapter] = {
    "ECOCASH": Adapter("ECOCASH", r"PP\d{6}\.\d{4}\.[A-Z]\d{4,6}", aliases=("ecocash", "eco cash")),
    "INNBUCKS": Adapter("INNBUCKS", None, aliases=("innbucks", "inn bucks")),
    "PAYNOW": Adapter("PAYNOW", None, aliases=("paynow",)),
    "ONEMONEY": Adapter("ONEMONEY", None, aliases=("onemoney", "one money")),
}
MAX_BATCH = 200


def adapter_for(
    provider: str | None, reference: str, table: dict[str, Adapter] | None = None
) -> Adapter | None:
    """Named provider first; otherwise the one provider whose known shape fits, if exactly one."""
    table = table if table is not None else ADAPTERS
    if provider:
        p = provider.strip().lower()
        return next((a for a in table.values() if p == a.name.lower() or p in a.aliases), None)
    fits = [a for a in table.values() if a.looks_like(reference)]
    return fits[0] if len(fits) == 1 else None


def verify_batch(
    items: list[tuple[str | None, str]],
    workers: int = 4,
    adapters: dict[str, Adapter] | None = None,
) -> list[Outcome]:
    """One Outcome per item, in order. An unknown provider is reported, never dropped."""
    if len(items) > MAX_BATCH:
        raise ValueError(f"at most {MAX_BATCH} items per batch")

    def one(item: tuple[str | None, str]) -> Outcome:
        provider, ref = item
        a = adapter_for(provider, ref, adapters)
        if a is None:
            return Outcome(
                ref, None, failure=LookupFailure.NOT_CONFIGURED, detail="unknown provider"
            )
        return a.lookup(ref)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        return list(pool.map(one, items))
