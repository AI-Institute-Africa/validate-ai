"""Screenshots of the main pages at phone, tablet and desktop width, light and dark, for before/after
comparison of a styling change.

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/visual_snapshots.py http://127.0.0.1:8000 before
    ...change the CSS...
    python e2e/visual_snapshots.py http://127.0.0.1:8000 after
    python e2e/visual_diff.py before after

Do not reset the demo between the two runs: the same data keeps the pages comparable.
"""

import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
out = sys.argv[2] if len(sys.argv) > 2 else "shots-visual"
os.makedirs(out, exist_ok=True)
exe = os.environ.get("CHROMIUM_PATH")

SIZES = {"phone": (375, 812), "tablet": (768, 1024), "desktop": (1360, 900)}
HIDE_MOVING = """
* { animation: none !important; transition: none !important; caret-color: transparent !important; scroll-behavior: auto !important; }
.rv-age, .toast, time { visibility: hidden !important; }
"""


def call(path, token):
    req = urllib.request.Request(f"{base}/api{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - local demo server
        return json.loads(r.read())


def token(email, role):
    req = urllib.request.Request(
        f"{base}/api/auth/dev-login",
        data=json.dumps({"email": email, "role": role}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read())["access_token"]


rev = token("rudo.reviewer@demo.validate", "reviewer")
claims = call("/review/queue", rev)
claim_id = next((c["claim_id"] for c in claims if c["state"] != "REJECTED"), None)

PAGES = [
    ("home", "/?persona=admin"),
    ("verify", "/verify?persona=submitter"),
    ("queue", "/queue?persona=reviewer"),
    ("claim", f"/claims/{claim_id}?persona=reviewer" if claim_id else None),
    ("kyc", "/kyc?persona=submitter"),
    ("kyc-review", "/kyc/review?persona=reviewer"),
    ("fraud", "/fraud?persona=admin"),
    ("guardrails", "/guardrails?persona=admin"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    for scheme in ("light", "dark"):
        for size, (w, h) in SIZES.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, device_scale_factor=1)
            page = ctx.new_page()
            for name, path in PAGES:
                if not path:
                    continue
                page.goto(f"{base}{path}")
                page.wait_for_load_state("networkidle")
                page.add_style_tag(content=HIDE_MOVING)
                page.wait_for_timeout(500)
                page.screenshot(path=f"{out}/{name}-{size}-{scheme}.png", full_page=True)
            ctx.close()
    browser.close()
print(f"saved to {out}")
