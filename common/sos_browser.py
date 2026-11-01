"""Fetch files from the SOS-hosted ENR (liveresults.boe.ohio.gov) through a
real Chrome window that a person has opened.

Why: the SOS ENR's summary XML/CSV, the only source of the vote-method split
for most counties, sits behind a Cloudflare Turnstile check. Plain HTTP,
headless browsers and Playwright-launched browsers are all refused (tested
2026-11-01). A normal Chrome window that a person opens loads the files fine.
So this module does not launch or automate a browser itself. It connects to
a Chrome window the owner started with a local debugging port, and makes
same-origin fetch() calls from that window's page, like the site's own
"details" view does. It never interacts with a challenge. If a fetch comes
back as a Cloudflare page, it stops and asks a person to complete the check
in that window. (The owner waived the project's no-bypass rule for this;
see REPORT.md.)

Start the window (Terminal, not from an agent sandbox):

    tools/sos_chrome.sh

That opens Chrome with a dedicated, empty profile (~/.scrapers2026-chrome)
and a debugging port on 127.0.0.1:9333 only. Keep it open while scraping.
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

CDP_URL = os.environ.get("SOS_CDP_URL", "http://127.0.0.1:9333")
HOST = "liveresults.boe.ohio.gov"
START_PAGE = f"https://{HOST}/ENR/butlerohenr/24/en/Index_24.html"
# The host rate-limits: ~30 requests at 1/s drew HTTP 429 (2026-11-01).
PAUSE = float(os.environ.get("SOS_PAUSE", "3"))   # seconds between requests
BACKOFF = (60, 120, 240)                           # waits after a 429, then give up

_JS = """async u => {
  const r = await fetch(u, {cache: 'no-store'});
  return {status: r.status, type: r.headers.get('content-type') || '', text: await r.text()};
}"""


class ChallengeNotCleared(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


def _is_challenge(status: int, ctype: str, text: str) -> bool:
    if "html" not in ctype.lower():
        return False
    head = text[:5000].lower()
    return any(k in head for k in ("just a moment", "security check", "attention required",
                                   "website maintenance", "challenge-platform/h/"))


class SOSBrowser:
    """Context manager. One connection, many fetches, paced 1 req/s."""

    def __init__(self, cdp_url: str = CDP_URL):
        self.cdp_url = cdp_url
        self._pw = self._browser = self._page = None
        self._last = 0.0

    def __enter__(self):
        from playwright.sync_api import sync_playwright  # optional dependency
        self._pw = sync_playwright().start()
        try:
            self._connect()
        except Exception:
            self._pw.stop()
            raise
        return self

    def _connect(self):
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url, timeout=10_000)
        except Exception as e:
            raise RuntimeError(
                f"No Chrome debugging port at {self.cdp_url}. Start the window with "
                f"tools/sos_chrome.sh (from Terminal) and keep it open. ({e})") from None
        if not self._browser.contexts:
            raise RuntimeError("Connected to Chrome but it has no browser context")
        ctx = self._browser.contexts[0]
        pages = [p for p in ctx.pages if urlparse(p.url).netloc == HOST]
        if pages:
            self._page = pages[0]
        else:
            # Open one tab on the host so fetch() is same-origin. This is a
            # page load a person would make; if Cloudflare asks for a check,
            # the person completes it in the window.
            self._page = ctx.new_page()
            self._page.goto(START_PAGE, timeout=60_000)

    def __exit__(self, *exc):
        # Disconnect only; never close the person's Chrome window.
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def fetch(self, url: str) -> tuple[int, str, str]:
        if urlparse(url).netloc != HOST:
            raise ValueError(f"SOSBrowser only fetches from {HOST}: {url}")
        wait = PAUSE - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self._page.evaluate(_JS, url)
        except Exception as e:
            # The tab can reload, or the CDP connection can drop (seen after
            # ~40 min of polling). Reconnect from scratch once, then retry.
            if "closed" not in str(e).lower():
                raise
            print("Chrome connection lost; reconnecting", file=sys.stderr)
            try:
                self._browser.close()
            except Exception:
                pass
            time.sleep(PAUSE)
            self._connect()
            r = self._page.evaluate(_JS, url)
        self._last = time.monotonic()
        for wait in BACKOFF:
            if r["status"] != 429:
                break
            print(f"HTTP 429 (rate limited) on {url}; waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
            r = self._page.evaluate(_JS, url)
            self._last = time.monotonic()
        if r["status"] == 429:
            raise RateLimited(f"Still rate limited (HTTP 429) after backing off: {url}")
        if _is_challenge(r["status"], r["type"], r["text"]):
            raise ChallengeNotCleared(
                f"Cloudflare check on {url}. Complete it in the Chrome window opened "
                "by tools/sos_chrome.sh (open any liveresults.boe.ohio.gov page there), "
                "then rerun. Not attempting to solve it.")
        return r["status"], r["type"], r["text"]

    def fetch_bytes(self, url: str) -> bytes:
        status, ctype, text = self.fetch(url)
        if status != 200:
            raise RuntimeError(f"{status} for {url}")
        return text.encode("utf-8")


_JS_BYTES = """async u => {
  const r = await fetch(u, {cache: 'no-store'});
  const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode.apply(null, b.subarray(i, i + 8192));
  return {status: r.status, type: r.headers.get('content-type') || '', b64: btoa(s)};
}"""


def fetch_file_via_page(url: str, page_url: str, cdp_url: str = CDP_URL) -> bytes:
    """Fetch a binary file (e.g. a county results PDF on www.boe.ohio.gov)
    through the owner's Chrome window: open a tab on `page_url` (same origin
    as `url`), fetch the file from there, close the tab. Used for SOS-hosted
    county BOE sites, which are behind the same Cloudflare check."""
    import base64
    from playwright.sync_api import sync_playwright
    if urlparse(url).netloc != urlparse(page_url).netloc:
        raise ValueError("url and page_url must be on the same host")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp_url, timeout=10_000)
        except Exception as e:
            raise RuntimeError(f"No Chrome debugging port at {cdp_url}. Start the window with "
                               f"tools/sos_chrome.sh (from Terminal) and keep it open. ({e})") from None
        tab = browser.contexts[0].new_page()
        try:
            tab.goto(page_url, timeout=60_000)
            time.sleep(PAUSE)
            r = tab.evaluate(_JS_BYTES, url)
            if r["status"] == 429:
                raise RateLimited(f"HTTP 429 (rate limited): {url}")
            data = base64.b64decode(r["b64"])
            if _is_challenge(r["status"], r["type"], data[:5000].decode("utf-8", "ignore")):
                raise ChallengeNotCleared(f"Cloudflare check on {url}. Complete it in the Chrome window, then rerun.")
            if r["status"] != 200:
                raise RuntimeError(f"{r['status']} for {url}")
            return data
        finally:
            tab.close()   # our own tab only
            browser.close()


_shared: SOSBrowser | None = None


def fetch_bytes(url: str) -> bytes:
    """Module-level helper with a lazily opened shared connection."""
    global _shared
    if _shared is None:
        _shared = SOSBrowser().__enter__()
    return _shared.fetch_bytes(url)
