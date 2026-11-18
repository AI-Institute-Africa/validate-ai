"""Export administrators' fake / not-fake decisions as authenticity labels (JSON lines).

    python -m training.detect.export_confirmed --org <uuid> --out labels.jsonl [--since 2026-11-01]

Needs the organisation's policy to record `training_export_consent` and a `training_consent_ref`
(the same gate as the corrections export); refuses otherwise and writes an audit event when it runs.
Rows carry the evidence SHA-256 and what the trained detectors said at the time, never images or
names. A false positive is as valuable as a confirmed fake: it teaches what not to flag. The rows
with a detector that disagreed with the person are the ones to label and learn from first.
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
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
            for row in training.detector_labels(s, a.org, since):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
        audit(
            s,
            actor="script:export_confirmed",
            action="training.exported",
            entity_type="organisation",
            entity_id=a.org,
            org_id=a.org,
            after={"rows": n, "consent_ref": ref, "kind": "detector_labels"},
        )
    print(f"wrote {n} rows to {a.out} (consent: {ref})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
