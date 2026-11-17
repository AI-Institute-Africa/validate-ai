"""Bulk approve end to end: with auto-approve off, a clear payment waits for a person. The reviewer
selects it, opens the approve sheet, types the last 4 characters of the bank record's transaction ID
and approves. A wrong last 4 is refused by the server.

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/bulk_approve.py http://127.0.0.1:8000
"""

import json
import os
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
exe = os.environ.get("CHROMIUM_PATH")


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{base}/api{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - local demo server
        return json.loads(r.read() or "null")


PERSONA_EMAIL = {
    "admin": "tariro.admin@demo.validate",
    "reviewer": "rudo.reviewer@demo.validate",
}


def login(role):
    return call("POST", "/auth/dev-login", body={"email": PERSONA_EMAIL[role], "role": role})["access_token"]


admin = login("admin")
cur = call("GET", "/admin/policy", admin)
cfg = {**cur["config"], "auto_approve_enabled": False}
call("POST", "/admin/policy", admin, {"version": f"{cur['version']}-manual-{os.getpid()}", "config": cfg})
# (the demo's scripted stories re-apply their own policy, so the payer below uses the sample button)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # a payer sends a clear receipt that the bank already has; auto-approve is off, so it waits
    page.goto(f"{base}/verify?persona=submitter")
    page.get_by_role("button", name="Paid, bank has it").click()
    submit = page.get_by_role("button", name="Validate this payment")
    expect(submit).to_be_enabled(timeout=30000)
    submit.click()
    reviewer = login("reviewer")
    mine: list = []
    for _ in range(30):  # the claim is read in the background: wait until it lands in the queue
        queue = call("GET", "/review/queue", reviewer)
        mine = [c for c in queue if c["approval_tier"] == "GREEN" and c["candidate_credit_id"]]
        if mine:
            break
        page.wait_for_timeout(1000)
    assert mine, f"no green matched claim in the queue: {[(c['state'], c['approval_tier']) for c in queue]}"
    claim = mine[0]
    detail = call("GET", f"/review/claims/{claim['claim_id']}", reviewer)
    txn = next(c for c in detail["candidates"] if c["credit"]["credit_id"] == claim["candidate_credit_id"])["credit"]["provider_txn_id"]

    page.goto(f"{base}/queue?persona=reviewer")
    row = page.locator("tbody tr[data-row]", has_text=claim["claimant_ref"]).first
    expect(row).to_be_visible(timeout=20000)
    row.locator("input[type=checkbox]").check()
    page.get_by_role("button", name="Approve matched…").click()
    sheet = page.get_by_role("dialog", name="Approve matched claims")
    box = sheet.locator("input.last4").first
    expect(box).to_be_visible(timeout=20000)
    box.fill("ZZZZ")  # wrong: the server must refuse
    sheet.get_by_role("button", name="Approve 1 of 1").click()
    expect(sheet.get_by_text("did not go through")).to_be_visible(timeout=20000)
    expect(sheet.get_by_text("last four").first).to_be_visible()
    sheet.get_by_role("button", name="Close").click()

    row = page.locator("tbody tr[data-row]", has_text=claim["claimant_ref"]).first
    row.locator("input[type=checkbox]").check()
    page.get_by_role("button", name="Approve matched…").click()
    box = page.get_by_role("dialog", name="Approve matched claims").locator("input.last4").first
    expect(box).to_be_visible(timeout=20000)
    box.fill(txn[-4:])
    page.get_by_role("button", name="Approve 1 of 1").click()
    expect(page.get_by_text("Approved 1 claim.")).to_be_visible(timeout=20000)
    assert not errors, errors
    browser.close()

after = call("GET", f"/claims/{claim['claim_id']}", reviewer)
assert after["state"] in ("APPROVED", "PARTIALLY_ALLOCATED"), after["state"]
print("bulk approve: ok")
