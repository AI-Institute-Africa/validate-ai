"""Reviewer: sort the queue, use the keyboard, and cancel a reject with Undo (nothing is sent).

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/queue_undo.py http://127.0.0.1:8000
"""

import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
exe = os.environ.get("CHROMIUM_PATH")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    sent: list[str] = []
    page.on("request", lambda r: sent.append(r.url) if "/reject" in r.url and r.method == "POST" else None)

    page.goto(f"{base}/queue?persona=reviewer")
    expect(page.get_by_role("heading", name="Review queue")).to_be_visible()
    rows = page.locator("tbody tr[data-row]")
    expect(rows.first).to_be_visible(timeout=20000)

    # sorting: clicking a column title sets aria-sort on it and keeps the order stable
    page.get_by_role("button", name="Declared").click()
    expect(page.locator("th[aria-sort='descending']")).to_have_count(1)
    page.get_by_role("button", name="Declared").click()
    expect(page.locator("th[aria-sort='ascending']")).to_have_count(1)

    # keyboard: j moves, ? opens the legend
    page.locator("body").press("j")
    expect(page.locator("tr.cursor")).to_have_count(1)
    page.locator("body").press("?")
    expect(page.get_by_role("dialog", name="Queue shortcuts")).to_be_visible()
    page.keyboard.press("Escape")

    # open a claim and reject, then undo within the countdown: nothing is sent
    rows.first.click()
    expect(page).to_have_url(re.compile(r"/claims/"))
    page.get_by_role("button", name="Reject").first.click()
    page.get_by_role("button", name="Reject claim").click()
    undo = page.get_by_role("button", name="Undo")
    expect(undo).to_be_visible()
    undo.click()
    page.wait_for_timeout(10000)  # longer than the countdown
    assert not sent, f"a reject was sent after Undo: {sent}"

    # and without Undo the reject is sent exactly once, after the countdown
    page.get_by_role("button", name="Reject").first.click()
    page.get_by_role("button", name="Reject claim").click()
    expect(page.get_by_role("button", name="Undo")).to_be_visible()
    page.wait_for_timeout(11000)
    assert len(sent) == 1, sent
    expect(page.get_by_text("Rejected. This cannot be undone now.")).to_be_visible(timeout=5000)

    assert not errors, errors
    browser.close()
print("queue and undo: ok")
