"""ZONE 1 — headless-browser fetch (Playwright).

The national portals are JS single-page apps that render results client-side and
apply bot-detection (SG SSO uses a request token; MY LOM is a DataTables AJAX grid).
A plain httpx GET only sees the empty shell. This module drives a real Chromium so
the page's own JavaScript runs — exactly the "bypass standard bot-detection / retrieve
from live portals in real time / PDFs buried 3+ clicks deep" requirement.

Used by:
  • discovery adapters (render a portal's search results, then scrape the live DOM)
  • fetch (render a JS-only law page to clean text, or drive a PDF download)

Lazy + optional: if Playwright (or its Chromium) isn't installed, callers fall back
to the httpx path. Browser launch is reused across calls within a session.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

_AVAILABLE: bool | None = None


def available() -> bool:
    """True if Playwright AND a Chromium build are installed (cached)."""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # launching is the only sure test that the browser binary exists
            b = p.chromium.launch(headless=True)
            b.close()
        _AVAILABLE = True
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


@dataclass
class RenderResult:
    html: str
    final_url: str


_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",   # hide the obvious automation flag
    "--disable-dev-shm-usage",
]


class Browser:
    """A reusable headless Chromium session. Use as a context manager:

        with Browser() as b:
            html = b.render(url, wait_selector="a.non-ajax")
    """

    def __init__(self):
        self._pw = None
        self._browser = None
        self._ctx = None

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        self._ctx = self._browser.new_context(
            user_agent=settings.crawl_user_agent,
            locale="en-US",
            extra_http_headers={"Accept-Language": settings.crawl_accept_language},
            viewport={"width": 1366, "height": 900},
        )
        # strip navigator.webdriver — a common bot tell
        self._ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        return self

    def __exit__(self, *exc):
        for closer in (self._ctx, self._browser):
            try:
                closer and closer.close()
            except Exception:
                pass
        try:
            self._pw and self._pw.stop()
        except Exception:
            pass

    def render(self, url: str, wait_selector: str | None = None,
               wait_ms: int = 2500, log=print) -> RenderResult | None:
        """Load `url`, let its JS run, return the rendered HTML. wait_selector waits
        for results to appear; wait_ms is a settle delay for late XHRs."""
        timeout = int(settings.crawl_timeout_seconds * 1000)
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout)
                except Exception:
                    pass            # selector may legitimately be absent (no results)
            page.wait_for_timeout(wait_ms)
            return RenderResult(html=page.content(), final_url=page.url)
        except Exception as e:  # noqa: BLE001
            log(f"[browser] render failed ({type(e).__name__}): {url}")
            return None
        finally:
            page.close()


def render_html(url: str, wait_selector: str | None = None, log=print) -> RenderResult | None:
    """One-shot convenience: launch, render one URL, tear down. Prefer Browser() for
    multiple URLs (reuses the Chromium process)."""
    if not available():
        return None
    with Browser() as b:
        return b.render(url, wait_selector=wait_selector, log=log)
