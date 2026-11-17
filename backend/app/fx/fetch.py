"""Fetch the RBZ daily rates PDF.

Direct link first: the file name follows the date, so one plain HTTP request is enough. If that
fails (file moved, name changed), a browser run renders the exchange-rates page, opens the year and
month, and finds the day's link. The browser is an optional extra, `backend[fxbrowser]`, and is
not in the default image.
"""

import contextlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from html import unescape
from urllib.parse import urljoin

import httpx

log = logging.getLogger(__name__)

INDEX_PAGE = "https://www.rbz.co.zw/index.php/research/markets/exchange-rates"
FILES_BASE = "https://www.rbz.co.zw/documents/Exchange_Rates"
USER_AGENT = "validate-fx/1 (daily official rate check)"


class FetchError(Exception):
    """The file could not be fetched; `.retry` says whether trying again later may help."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


@dataclass(frozen=True)
class Fetched:
    data: bytes
    url: str
    method: str  # direct | browser


def dated_url(d: date, base: str = FILES_BASE) -> str:
    """e.g. .../2026/November/RATES_13_NOVEMBER_2026.pdf"""
    month = d.strftime("%B")
    return f"{base.rstrip('/')}/{d.year}/{month}/RATES_{d.day:02d}_{month.upper()}_{d.year}.pdf"


def find_pdf_link(html: str, d: date, page_url: str = INDEX_PAGE) -> str | None:
    """Find the link to the day's PDF in the rendered exchange-rates page."""
    month = d.strftime("%B").upper()
    want = re.compile(rf"RATES_0?{d.day}_{month}_{d.year}\.pdf", re.I)
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", html, re.I):
        href = unescape(href).strip()
        if want.search(href.replace("%20", "_")):
            return urljoin(page_url, href)
    return None


def fetch_direct(d: date, client: httpx.Client | None = None, base: str = FILES_BASE) -> Fetched:
    url = dated_url(d, base)
    own = client is None
    client = client or httpx.Client(
        timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"direct fetch failed: {type(exc).__name__}") from exc
    finally:
        if own:
            client.close()
    if resp.status_code == 404:
        raise FetchError("file not published at the dated link", retry=True)
    if resp.status_code != 200:
        raise FetchError(f"direct fetch returned HTTP {resp.status_code}")
    if not resp.content.startswith(b"%PDF"):
        raise FetchError("the dated link did not return a PDF")
    return Fetched(resp.content, url, "direct")


def fetch_browser(d: date, render: Callable[[str], str] | None = None) -> Fetched:
    """Open the page in a browser, expand the year and month, and download the day's PDF.

    `render(url)` returns the page HTML after the sections are opened; it defaults to Playwright.
    """
    html = render(INDEX_PAGE) if render else _render_with_playwright(INDEX_PAGE, d)
    link = find_pdf_link(html, d)
    if not link:
        raise FetchError("the page has no link for that day", retry=True)
    try:
        resp = httpx.get(
            link, timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    except httpx.HTTPError as exc:
        raise FetchError(f"download failed: {type(exc).__name__}") from exc
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        raise FetchError("the linked file is not a PDF")
    return Fetched(resp.content, link, "browser")


def _render_with_playwright(url: str, d: date) -> str:  # pragma: no cover - needs a browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError(
            "browser fallback is not installed (extra: fxbrowser)", retry=False
        ) from exc
    year = str(d.year)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # best effort: open the year and month sections if the page hides them
            for label in (year, d.strftime("%B")):
                with contextlib.suppress(Exception):  # the section may already be open
                    page.get_by_text(label, exact=True).first.click(timeout=3000)
            return page.content()
        finally:
            browser.close()


def fetch_day(
    d: date, client: httpx.Client | None = None, render: Callable[[str], str] | None = None
) -> Fetched:
    """Direct link, then the browser. Raises FetchError when both fail."""
    try:
        return fetch_direct(d, client)
    except FetchError as first:
        log.info("direct fetch for %s failed (%s); trying the browser", d, first)
        try:
            return fetch_browser(d, render)
        except FetchError as second:
            raise FetchError(
                f"{first}; browser: {second}", retry=first.retry or second.retry
            ) from second
