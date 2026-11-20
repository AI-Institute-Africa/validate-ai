"""Phone-width gate: every page must fit a 375 px touch viewport, and the mobile drawer must be
usable by touch and keyboard. Run against the standalone demo after a reset.

    python -m app.demo --no-browser --port 8000 &        # from backend/
    python e2e/mobile.py http://127.0.0.1:8000
"""

import atexit
import json
import os
import re
import sys
import urllib.request
import uuid

from playwright.sync_api import expect, sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
exe = os.environ.get("CHROMIUM_PATH")


def api(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(f"{base}/api{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - local demo server
        return json.loads(response.read())


def dev_token(email="rudo.reviewer@demo.validate", role="reviewer"):
    request = urllib.request.Request(
        f"{base}/api/auth/dev-login",
        data=json.dumps({"email": email, "role": role}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read())["access_token"]


def call_api(method, path, token=None, body=None):
    request = urllib.request.Request(
        f"{base}/api{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read() or "null")


reviewer = dev_token()
claims = api("/review/queue", reviewer)
claim_id = next((c["claim_id"] for c in claims if c["state"] != "REJECTED"), None)

PAGES = [
    "/?persona=admin",
    "/verify?persona=submitter",
    "/image-to-text?persona=submitter",
    "/kyc?persona=submitter",
    "/queue?persona=reviewer",
    "/credits?persona=reviewer",
    "/credits/bulk?persona=reviewer",
    "/obligations?persona=reviewer",
    "/alerts?persona=reviewer",
    "/fraud?persona=admin",
    "/guardrails?persona=admin",
    "/insights?persona=admin",
    "/insights/exposure?persona=admin",
    "/insights/scorecard?persona=admin",
    "/insights/replay?persona=admin",
    "/insights/fx?persona=admin",
    "/insights/compliance?persona=admin",
    "/kyc/review?persona=reviewer",
]
if claim_id:
    PAGES += [f"/claims/{claim_id}?persona=reviewer", f"/track/{claim_id}?persona=submitter"]

NO_OVERFLOW = """() => {
  const d = document.documentElement;
  const overflow = d.scrollWidth - d.clientWidth;
  const inScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX)) return true;
    }
    return false;
  };
  const offenders = [];
  if (overflow > 1) {
    document.querySelectorAll('body *').forEach(el => {
      const s = getComputedStyle(el);
      if (s.position === 'fixed' || s.display === 'none' || inScroller(el)) return;
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > d.clientWidth + 1) {
        offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ').slice(0, 2).join('.')} [${Math.round(r.left)}-${Math.round(r.right)}]`);
      }
    });
  }
  return { overflow, offenders: offenders.slice(0, 8) };
}"""

SMALL_TARGETS = """() => {
  const out = [];
  document.querySelectorAll('button, a.btn, select, .rv-pill, .rv-tab, .menu-btn').forEach(el => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || el.closest('[inert]')) return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    if (r.height < 43.5) out.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)}: ${Math.round(r.height)}px`);
  });
  return out.slice(0, 10);
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    ctx = browser.new_context(
        viewport={"width": 375, "height": 812},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{base}/?persona=admin")
    assert page.evaluate("matchMedia('(pointer: coarse)').matches"), "context must emulate a touch device"

    # Drawer: labelled trigger, focus moves in, Escape closes and returns focus, closed drawer is inert.
    menu = page.locator(".menu-btn")
    drawer = page.locator("#shell-nav")
    expect(menu).to_be_visible()
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(drawer).to_have_attribute("aria-hidden", "true")
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")
    expect(drawer).to_be_visible()
    expect(drawer).to_have_attribute("role", "dialog")
    expect(drawer).to_have_attribute("aria-modal", "true")
    expect(page.locator("#shell-nav a").first).to_be_focused()
    expect(page.locator("body")).to_have_css("overflow", "hidden")
    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_focused()
    expect(drawer).to_have_attribute("aria-hidden", "true")
    page.keyboard.press("Tab")
    assert not page.evaluate("!!document.activeElement.closest('#shell-nav')"), "closed drawer must not take focus"

    for path in PAGES:
        page.goto(f"{base}{path}")
        page.wait_for_load_state("networkidle")
        result = page.evaluate(NO_OVERFLOW)
        assert result["overflow"] <= 1, f"{path}: page scrolls sideways by {result['overflow']}px: {result['offenders']}"
        small = page.evaluate(SMALL_TARGETS)
        assert not small, f"{path}: touch targets under 44px: {small}"

    # Phase 1 journey: home -> sample payment -> result -> track, on a touch phone.
    page.goto(f"{base}/?persona=submitter")
    page.get_by_role("link", name="Try it on your own payment").click()
    expect(page).to_have_url(re.compile(r"/verify"))
    page.get_by_role("button", name="Paid, bank has it").click()
    submit = page.get_by_role("button", name="Validate this payment")
    expect(submit).to_be_enabled(timeout=30000)
    submit.click()
    track_link = page.get_by_role("link", name="Track this payment")
    expect(track_link).to_be_visible(timeout=40000)
    track_link.click()
    expect(page).to_have_url(re.compile(r"/track/"))
    expect(page.get_by_role("heading", name="Your payment", exact=True)).to_be_visible()

    # ID page: real label/button structure and the right camera on each capture.
    page.goto(f"{base}/kyc?persona=submitter")
    expect(page.locator("label.dz")).to_have_count(3)
    assert page.locator("label.dz button").count() == 0, "no nested controls in a file label"
    assert page.locator('input[type="file"][capture="environment"]').count() == 2
    assert page.locator('input[type="file"][capture="user"]').count() == 1

    # Offline submit -> online retry, with exactly one claim reaching the server.
    page.goto(f"{base}/verify?persona=submitter")
    page.get_by_role("button", name="Paid, bank has it").click()
    submit = page.get_by_role("button", name="Validate this payment")
    expect(submit).to_be_enabled(timeout=30000)
    posted: list[str] = []
    page.on(
        "response",
        lambda r: posted.append(r.url)
        if r.url.endswith("/api/claims") and r.request.method == "POST" and r.ok
        else None,
    )
    ctx.set_offline(True)
    submit.click()
    expect(page.get_by_text("Waiting to send (1)")).to_be_visible(timeout=15000)
    assert not posted, "nothing should have reached the server while offline"
    ctx.set_offline(False)
    expect(page.locator("body")).to_contain_text("Approved", timeout=40000)
    expect(page.get_by_text("Waiting to send")).to_have_count(0)
    assert len(posted) == 1, posted

    # Phase 2: a reviewer can triage and confirm a matched claim on this 375px phone.
    admin = dev_token("tariro.admin@demo.validate", "admin")
    policy = call_api("GET", "/admin/policy", admin)
    call_api("POST", "/admin/policy", admin, {
        "version": f"mob-{uuid.uuid4().hex[:8]}",
        "config": {**policy["config"], "auto_approve_enabled": False},
    })

    def restore_policy():
        try:
            call_api("POST", "/admin/policy", admin, {
                "version": f"res-{uuid.uuid4().hex[:8]}",
                "config": policy["config"],
            })
        except Exception as exc:  # never hide the real test result
            print(f"could not restore the demo policy: {exc}", file=sys.stderr)

    atexit.register(restore_policy)

    page.goto(f"{base}/verify?persona=submitter")
    page.get_by_role("button", name="Paid, bank has it").click()
    submit = page.get_by_role("button", name="Validate this payment")
    expect(submit).to_be_enabled(timeout=30000)
    submit.click()
    mine = []
    for _ in range(40):  # the claim is read in the background
        mine = [c for c in api("/review/queue", reviewer) if c["approval_tier"] == "GREEN" and c["candidate_credit_id"]]
        if mine:
            break
        page.wait_for_timeout(1000)
    assert mine, "no green matched claim reached the review queue"
    claim = mine[0]
    detail = api(f"/review/claims/{claim['claim_id']}", reviewer)
    txn = next(c for c in detail["candidates"] if c["credit"]["credit_id"] == claim["candidate_credit_id"])["credit"]["provider_txn_id"]

    page.goto(f"{base}/claims/{claim['claim_id']}?persona=reviewer")
    expect(page.get_by_role("region", name="Decision bar")).to_be_visible()
    legend = page.locator(".viewer-legend")
    if legend.count():
        legend.locator("summary").click()
        boxed = legend.locator(".legend-list button").first
        boxed_name = boxed.locator("strong").inner_text()
        boxed.click()
        expect(page.locator(".box.hot")).to_have_count(1)
        boxed.click()  # clear it, so the next assertion is about the field button
        expect(page.locator(".box.hot")).to_have_count(0)
        # Pick the matching field row: not every extracted field has a proof region.
        field = page.locator(".rv-field").filter(has=page.locator(".k", has_text=boxed_name)).first
        field.locator(".show-on-image").click()
        expect(page.locator(".box.hot")).to_have_count(1)
    else:
        # The demo's fake reader records no proof coordinates, so there is no box to
        # highlight. The touch control must still be present and toggle its state.
        toggle = page.locator(".rv-field .show-on-image").first
        expect(toggle).to_have_text("Show on image")
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "true")
        expect(toggle).to_have_text("Hide on image")
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "false")
    # The same evidence must be readable on a 768px tablet, with no page-level sideways scroll.
    # Check it before confirming, while the decision bar is still present.
    tablet = browser.new_context(
        viewport={"width": 768, "height": 1024},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    tpage = tablet.new_page()
    tablet_errors: list[str] = []
    tpage.on("pageerror", lambda e: tablet_errors.append(str(e)))
    for path in (f"/claims/{claim['claim_id']}?persona=reviewer", "/insights?persona=admin"):
        tpage.goto(f"{base}{path}")
        tpage.wait_for_load_state("networkidle")
        result = tpage.evaluate(NO_OVERFLOW)
        assert result["overflow"] <= 1, f"{path}: tablet scrolls sideways by {result['overflow']}px: {result['offenders']}"
    tpage.goto(f"{base}/claims/{claim['claim_id']}?persona=reviewer")
    expect(tpage.locator(".viewer-scroll img")).to_be_visible()
    tlegend = tpage.locator(".viewer-legend")
    if tlegend.count():
        tlegend.locator("summary").click()
        expect(tlegend.locator(".legend-list button").first).to_be_visible()
    expect(tpage.get_by_role("region", name="Decision bar")).to_be_visible()

    page.get_by_role("button", name="Confirm…").click()
    last4 = page.get_by_role("textbox", name="Last four characters of transaction ID")
    expect(last4).to_be_focused()
    last4.fill(txn[-4:])
    page.get_by_role("button", name=re.compile(r"Confirm credit \d+")).click()
    expect(page.get_by_text(re.compile("Confirmed:"))).to_be_visible(timeout=30000)

    assert not errors, errors
    assert not tablet_errors, tablet_errors
    browser.close()
print(f"mobile: ok ({len(PAGES)} pages at 375px; payment, track, ID, offline retry and staff triage; 768px evidence)")
