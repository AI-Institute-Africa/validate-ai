"""Live check of the RBZ rate source. Run by hand from a network that can reach www.rbz.co.zw.

    python tools/fx_live_check.py 2026-11-13          # expects ask 27.2508 for that day

Fetches the day's PDF the same way the daily job does, parses it, and prints what it found. It
writes nothing to the database. Use it after a layout-change alert, or before turning on
POPS_FX_ENABLED.
"""

import sys
from datetime import date

from app.fx import fetch
from app.fx.parse import parse_pdf


def main(day: str) -> int:
    d = date.fromisoformat(day)
    got = fetch.fetch_day(d)
    rate = parse_pdf(got.data)
    print(f"fetched via {got.method}: {got.url}")
    print(f"file date {rate.rate_date}  bid {rate.bid}  ask {rate.ask}  mid {rate.mid}")
    return 0 if rate.rate_date == d else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()))
