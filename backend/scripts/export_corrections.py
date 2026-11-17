"""Export reviewer corrections as training labels (JSON lines), with consent on record.

    python scripts/export_corrections.py --org <uuid> --out corrections.jsonl [--since 2026-11-01]

Refuses to run unless the organisation's policy has training_export_consent and a
training_consent_ref. Writes an audit event. Rows carry the evidence SHA-256, never images.
See docs/training-data.md.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime

from app.analytics import training
from app.core.audit import audit
from app.core.db import session_scope
from app.policy.engine import load_policy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True, type=uuid.UUID)
    ap.add_argument("--out", required=True)
    ap.add_argument("--since")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since) if a.since else None
    with session_scope() as s:
        try:
            ref = training.require_consent(load_policy(s, a.org).config)
        except training.ConsentMissing as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        n = 0
        with open(a.out, "w", encoding="utf-8") as fh:
            for row in training.corrections(s, a.org, since):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
        audit(
            s,
            actor="script:export_corrections",
            action="training.exported",
            entity_type="organisation",
            entity_id=a.org,
            org_id=a.org,
            after={"rows": n, "consent_ref": ref},
        )
    print(f"wrote {n} rows to {a.out} (consent: {ref})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
