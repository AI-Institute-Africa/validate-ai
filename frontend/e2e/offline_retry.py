"""A payer submits while offline: the upload waits on the phone, is sent when back online, and
exactly one claim exists afterwards.

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/offline_retry.py http://127.0.0.1:8000
"""

import json
import os
import sys

from playwright.sync_api import expect, sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
exe = os.environ.get("CHROMIUM_PATH")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{base}/verify?persona=submitter")  # on a phone the menu is closed: go straight there
    page.get_by_role("button", name="Paid, bank has it").click()
    submit = page.get_by_role("button", name="Validate this payment")
    expect(submit).to_be_enabled(timeout=30000)

    claims_seen: list[str] = []
    page.on(
        "response",
        lambda r: claims_seen.append(r.url)
        if r.url.endswith("/api/claims") and r.request.method == "POST" and r.ok
        else None,
    )

    ctx.set_offline(True)  # the phone loses its signal
    submit.click()
    expect(page.get_by_text("Waiting to send (1)")).to_be_visible(timeout=15000)
    assert not claims_seen, "nothing should have reached the server while offline"

    ctx.set_offline(False)  # signal is back: it sends by itself
    expect(page.locator("body")).to_contain_text("Approved", timeout=40000)
    expect(page.get_by_text("Waiting to send")).to_have_count(0)
    assert len(claims_seen) == 1, claims_seen

    assert not errors, errors
    browser.close()
print("offline retry: ok")
