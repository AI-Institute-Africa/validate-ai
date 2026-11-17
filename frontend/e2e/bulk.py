"""Reviewer bulk actions: select, ask for more info (after the undo window), and the approve sheet
refusing claims that are not clearly safe.

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/bulk.py http://127.0.0.1:8000
"""

import os
import sys

from playwright.sync_api import expect, sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
exe = os.environ.get("CHROMIUM_PATH")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    infos: list[str] = []
    confirms: list[str] = []
    page.on("request", lambda r: infos.append(r.url) if "/request-info" in r.url and r.method == "POST" else None)
    page.on("request", lambda r: confirms.append(r.url) if "/confirm" in r.url and r.method == "POST" else None)

    page.goto(f"{base}/queue?persona=reviewer")
    expect(page.locator("tbody tr[data-row]").first).to_be_visible(timeout=20000)
    total = page.locator("tbody tr[data-row]").count()
    assert total >= 2, f"need at least two queued claims, found {total}"

    # select with the keyboard (x) and with a checkbox
    page.locator("body").press("j")
    page.locator("body").press("x")
    page.locator("tbody tr[data-row]").nth(0).locator("input[type=checkbox]").check()
    expect(page.get_by_text("2 selected")).to_be_visible()

    # the approve sheet: nothing is approved without the reviewer typing the last 4
    page.get_by_role("button", name="Approve matched…").click()
    sheet = page.get_by_role("dialog", name="Approve matched claims")
    expect(sheet).to_be_visible()
    expect(sheet.get_by_text("Checking 2 claims…")).to_have_count(0, timeout=20000)
    assert sheet.get_by_role("button", name="Approve 0 of").is_disabled() or sheet.locator("input.last4").count() > 0
    page.keyboard.press("Escape")
    assert not confirms, f"nothing should be confirmed without typed last 4: {confirms}"

    # ask for more info: sent only after the undo window
    page.get_by_role("button", name="Ask for more info").click()
    page.get_by_label("Message to all 2 payers").fill("Please send a clearer photo of the whole receipt.")
    page.get_by_role("button", name="Send to 2").click()
    expect(page.get_by_role("button", name="Undo")).to_be_visible()
    assert not infos, "nothing is sent while the countdown runs"
    page.wait_for_timeout(11000)
    assert len(infos) == 2, infos
    expect(page.get_by_text("Asked 2 claims.")).to_be_visible(timeout=5000)

    assert not errors, errors
    browser.close()
print("bulk: ok")
