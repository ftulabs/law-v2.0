"""ZONE 1 — bot-resistant fetching via Scrapling (https://github.com/D4Vinci/Scrapling).

The default httpx fetcher works on portals that only check the User-Agent (SG SSO), but
fails on harder targets the hackathon points at: WAFs that fingerprint the TLS/JA3
handshake (httpx's signature is flagged), and JS-rendered portal search (MY DataTables,
deep-paginated AU). Scrapling solves both:

  • Fetcher       — curl_cffi browser-IMPERSONATION (real Chrome TLS + headers), no
                    browser binary. Beats TLS/WAF fingerprint blocks that 403 httpx.
  • StealthyFetcher — a real (Camoufox) stealth browser that executes JS and clears
                    Cloudflare-style challenges. Needs `scrapling install` (browser
                    download); used only when explicitly enabled.

This module exposes ONE function, `fetch()`, returning raw bytes + content-type so the
existing content-addressed cache in fetch.py is reused unchanged. Everything is wrapped
so a missing dependency or a single failure degrades gracefully to None — the caller
then keeps whatever httpx produced. No import of Scrapling happens unless it is used.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from ..config import settings


@dataclass
class ScrapeResult:
    body: bytes
    content_type: str
    status: int
    engine: str


#: Tries of the impersonating fetcher per request; see the BPK note in `fetch`. At the measured
#: 50% refusal rate, four tries miss one term in sixteen instead of one in two.
_ATTEMPTS = 4


def available() -> bool:
    import importlib.util
    return importlib.util.find_spec("scrapling") is not None


def _to_result(r, engine: str) -> ScrapeResult | None:
    status = int(getattr(r, "status", 0) or 0)
    body = getattr(r, "body", None)
    if isinstance(body, str):
        body = body.encode("utf-8", "ignore")
    if not body:                                   # browser fetchers expose text/html only
        text = getattr(r, "html_content", None) or getattr(r, "text", None) or ""
        body = text.encode("utf-8", "ignore")
    ct = ""
    headers = getattr(r, "headers", None)
    if headers:
        try:
            ct = headers.get("content-type", "") or ""
        except Exception:
            ct = ""
    if status and status < 400 and body:
        return ScrapeResult(bytes(body), ct, status, engine)
    return None


def fetch(url: str, timeout: float | None = None, browser: bool = False,
          log=print, attempts: int | None = None,
          retries: int | None = None) -> ScrapeResult | None:
    """Fetch `url` with Scrapling's impersonating Fetcher; optionally escalate to the
    stealth browser for JS-gated pages. Returns None if Scrapling is unavailable or both
    attempts fail (caller falls back to httpx).

    `attempts` (our outer loop, default `_ATTEMPTS`) and `retries` (Scrapling's own inner
    loop, default Scrapling's 3) exist for a caller that only wants ONE cheap probe. The web-
    search lane is that caller: measured 2026-09-30, with html.duckduckgo.com refusing TCP,
    one query cost 4 outer x 3 inner x 21 s connect timeouts plus pauses -- about 4.5 minutes
    -- and the engine needs two failures to be retired, so every economy with a web-search
    lane spent ~9 minutes of discovery learning that DuckDuckGo was down."""
    if not available():
        return None
    timeout = int(timeout or settings.crawl_timeout_seconds)
    tries = max(1, int(attempts or _ATTEMPTS))
    extra = {} if retries is None else {"retries": int(retries)}

    # 1) curl_cffi impersonation — fast, no browser, beats TLS/WAF fingerprinting.
    # Several tries, because each call draws a RANDOM browser fingerprint and some WAFs refuse
    # some of them: peraturan.bpk.go.id answered the same search URL 403, 200, 403, 200 on four
    # consecutive calls (measured 2026-09-26). One try per request made each Indonesian search
    # term a coin flip, and one live run lost all six — 0 documents, a whole economy empty.
    import time
    challenged = False
    for attempt in range(tries):
        try:
            from scrapling.fetchers import Fetcher
            r = Fetcher.get(url, timeout=timeout, stealthy_headers=True, **extra)
            res = _to_result(r, "scrapling-fetcher")
            if res:
                return res
            # A Cloudflare MANAGED CHALLENGE is not a fingerprint coin-flip — no retry clears
            # it, and it must be named: by the afternoon of 2026-09-26 BPK challenged every
            # request (root, sitemap, documents), and the run said only "no response from the
            # browser lane", which reads as our browser being broken.
            hdrs = getattr(r, "headers", None) or {}
            if str(hdrs.get("cf-mitigated", "")).lower() == "challenge":
                log(f"[scrapling] Cloudflare challenge (cf-mitigated) on {url[:90]} — the site "
                    f"now requires a JavaScript challenge; escalating to the browser")
                challenged = True
                break
        except Exception as e:  # noqa: BLE001
            log(f"[scrapling] Fetcher error ({type(e).__name__}) for {url}")
        if attempt + 1 < tries:
            time.sleep(1.5 * (attempt + 1))

    # 2) stealth browser — executes JS, clears challenges (needs `scrapling install`).
    # A named challenge escalates on its own when FETCH_BROWSER_ON_BLOCK is on: a real browser
    # runs Cloudflare's JavaScript check the way any visitor's does, and on 2026-09-26 that was
    # the only way left to read BPK (the impersonating fetcher got "challenge" on every path,
    # the stealth browser got HTTP 200 in 3.9 s on the same search URL).
    if browser or settings.crawl_browser or (challenged and settings.fetch_browser_on_block):
        return browser_fetch(url, timeout, log)
    return None


#: Paths a browser DOWNLOADS rather than displays. Navigating to one fails ("Page.goto: Download
#: is starting", measured on BPK's /Download/<id>/<name>.pdf), so the file is fetched from INSIDE
#: a page of the same site instead — same cookies, same browser, same fingerprint.
_DOWNLOAD_RE = re.compile(r"\.(pdf|docx?|rtf|zip|xlsx?)(?:$|[?#])", re.I)

#: A challenge page the browser has not (yet) cleared.
_CHALLENGE_PAGE_RE = re.compile(r"<title>\s*Just a moment|challenges\.cloudflare\.com|cf-chl-", re.I)

_IN_PAGE_FETCH = """async (u) => {
  const r = await fetch(u, {credentials: 'include'});
  const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; const C = 0x8000;
  for (let i = 0; i < b.length; i += C) s += String.fromCharCode.apply(null, b.subarray(i, i + C));
  return {status: r.status, ct: r.headers.get('content-type') || '', b64: btoa(s)};
}"""


def browser_fetch(url: str, timeout: float | None = None, log=print) -> ScrapeResult | None:
    """Read `url` in the stealth browser. Two tries: the first only lets the page's own
    JavaScript challenge run (enough for BPK's managed challenge, measured 2026-09-26); the
    second also ticks Cloudflare's "verify you are human" box if one is shown. No outside
    CAPTCHA service is ever called, and callers have already asked robots.txt about `url`."""
    timeout = int(timeout or settings.crawl_timeout_seconds)
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as e:  # noqa: BLE001
        log(f"[scrapling] StealthyFetcher unavailable ({type(e).__name__}); "
            f"run `scrapling install` for JS portals")
        return None
    download = bool(_DOWNLOAD_RE.search(urllib.parse.urlsplit(url).path))
    for solve in (False, True):
        try:
            if download:
                res = _download_in_page(StealthyFetcher, url, timeout, solve)
            else:
                r = StealthyFetcher.fetch(url, headless=True, network_idle=True,
                                          timeout=timeout * 1000, solve_cloudflare=solve)
                res = _to_result(r, "scrapling-stealth")
                if res and _CHALLENGE_PAGE_RE.search(res.body[:20000].decode("utf-8", "ignore")):
                    res = None                       # the challenge page itself is not the page
            if res:
                log(f"[scrapling] stealth browser cleared {url}"
                    + (" (after the human-check box)" if solve else ""))
                return res
        except Exception as e:  # noqa: BLE001
            log(f"[scrapling] stealth browser failed ({type(e).__name__}) for {url[:90]}")
    log(f"[scrapling] stealth browser could not clear {url[:90]}")
    return None


def _download_in_page(fetcher, url: str, timeout: int, solve: bool) -> ScrapeResult | None:
    """Open the site's root, then fetch `url` from inside that page."""
    import base64
    parts = urllib.parse.urlsplit(url)
    got: dict = {}

    def action(page):
        got["r"] = page.evaluate(_IN_PAGE_FETCH, url)
        return page

    fetcher.fetch(f"{parts.scheme}://{parts.netloc}/", headless=True, network_idle=True,
                  timeout=timeout * 1000, solve_cloudflare=solve, page_action=action)
    r = got.get("r") or {}
    if not r or int(r.get("status") or 0) >= 400:
        return None
    body = base64.b64decode(r.get("b64") or "")
    if not body or _CHALLENGE_PAGE_RE.search(body[:20000].decode("utf-8", "ignore")):
        return None
    return ScrapeResult(body, r.get("ct") or "", int(r["status"]), "scrapling-stealth")
