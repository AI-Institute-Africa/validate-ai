#!/usr/bin/env sh
# Run every browser test against a running demo.
#
#   (cd backend && python -m app.demo --no-browser --port 8000) &
#   sh frontend/e2e/run_demo_suite.sh [base-url] [screenshots-dir]
#
# The demo is reset before each script, so one script's changes (a rejected claim, a policy switch)
# can never decide the next one's result, and the order does not matter. CI runs exactly this.
# Set PYTHON to pick the interpreter (it needs `playwright`) and CHROMIUM_PATH to use a browser
# that is already installed.
set -u
base="${1:-http://127.0.0.1:8000}"
shots="${2:-shots}"
py="${PYTHON:-python}"
cd "$(dirname "$0")/.." || exit 2

group() { [ -n "${GITHUB_ACTIONS:-}" ] && echo "::group::$1" || echo "== $1"; }
endgroup() { [ -n "${GITHUB_ACTIONS:-}" ] && echo "::endgroup::"; return 0; }

failed=""
for t in demo_tour offline_retry queue_undo bulk bulk_approve mobile; do
  group "$t"
  if curl -fsS --max-time 180 -X POST "$base/api/demo/reset" >/dev/null && "$py" "e2e/$t.py" "$base" "$shots"; then
    echo "PASS $t"
  else
    echo "FAIL $t"
    failed="$failed $t"
  fi
  endgroup
done

if [ -n "$failed" ]; then
  echo "Browser tests failed:$failed"
  exit 1
fi
echo "All browser tests passed."
