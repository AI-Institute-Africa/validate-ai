"""Shared layout assertions for the phone (375px) and tablet (768px) browser gates.

    from mobile_asserts import assert_mobile_layout

    assert_mobile_layout(page, "/queue?persona=reviewer")

The checks are deliberately boring: no sideways scroll, no tiny touch targets, and a page
title that is actually on screen. Keep them here so every e2e script uses the same rules.
"""

from playwright.sync_api import expect

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

LAYOUT_SHIFT_OBSERVER = """
window.__cls = 0;
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__cls += entry.value;
}).observe({ type: 'layout-shift', buffered: true });
"""

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


def assert_no_horizontal_scroll(page, where=""):
    """Page-level sideways scroll is never acceptable; inner scrollers are allowed."""
    result = page.evaluate(NO_OVERFLOW)
    assert result["overflow"] <= 1, f"{where}: page scrolls sideways by {result['overflow']}px: {result['offenders']}"


def assert_touch_targets(page, where=""):
    """Visible controls must be at least 44px tall (0.5px tolerance for rounding)."""
    small = page.evaluate(SMALL_TARGETS)
    assert not small, f"{where}: touch targets under 44px: {small}"


def assert_visible_title(page, where=""):
    """The first page heading (h1, or h2 on sections without an h1) is on screen."""
    title = page.locator("main h1, main h2").first
    expect(title).to_be_visible()
    box = title.bounding_box()
    assert box and box["height"] > 0, f"{where}: page title has no visible box"
    height = page.viewport_size["height"] if page.viewport_size else 10_000
    assert -1 <= box["y"] < height, f"{where}: page title starts at y={round(box['y'])} (viewport {height}px)"
    return title


def install_layout_shift_observer(page):
    """Call before the first navigation so images cannot shift content unnoticed."""
    page.add_init_script(LAYOUT_SHIFT_OBSERVER)


def assert_layout_shift(page, where="", limit=0.1):
    """Cumulative layout shift stays below the usual 'no visible jump' threshold."""
    page.wait_for_timeout(150)  # let late images and skeletons settle
    cls = page.evaluate("window.__cls || 0")
    assert cls < limit, f"{where}: cumulative layout shift {cls:.3f} >= {limit}"


def assert_mobile_layout(page, where=""):
    """All checks, in the order that gives the clearest failure message."""
    assert_no_horizontal_scroll(page, where)
    assert_touch_targets(page, where)
    assert_visible_title(page, where)
    assert_layout_shift(page, where)
