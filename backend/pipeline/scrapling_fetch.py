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
          log=print) -> ScrapeResult | None:
    """Fetch `url` with Scrapling's impersonating Fetcher; optionally escalate to the
    stealth browser for JS-gated pages. Returns None if Scrapling is unavailable or both
    attempts fail (caller falls back to httpx)."""
    if not available():
        return None
    timeout = int(timeout or settings.crawl_timeout_seconds)

    # 1) curl_cffi impersonation — fast, no browser, beats TLS/WAF fingerprinting.
    # Several tries, because each call draws a RANDOM browser fingerprint and some WAFs refuse
    # some of them: peraturan.bpk.go.id answered the same search URL 403, 200, 403, 200 on four
    # consecutive calls (measured 2026-09-26). One try per request made each Indonesian search
    # term a coin flip, and one live run lost all six — 0 documents, a whole economy empty.
    import time
    for attempt in range(_ATTEMPTS):
        try:
            from scrapling.fetchers import Fetcher
            r = Fetcher.get(url, timeout=timeout, stealthy_headers=True)
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
                    f"now requires a JavaScript challenge; not retried")
                break
        except Exception as e:  # noqa: BLE001
            log(f"[scrapling] Fetcher error ({type(e).__name__}) for {url}")
        if attempt + 1 < _ATTEMPTS:
            time.sleep(1.5 * (attempt + 1))

    # 2) stealth browser — executes JS, clears challenges (needs `scrapling install`)
    if browser or settings.crawl_browser:
        try:
            from scrapling.fetchers import StealthyFetcher
            r = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=timeout * 1000)
            res = _to_result(r, "scrapling-stealth")
            if res:
                log(f"[scrapling] stealth browser cleared {url}")
                return res
        except Exception as e:  # noqa: BLE001
            log(f"[scrapling] StealthyFetcher unavailable ({type(e).__name__}); "
                f"run `scrapling install` for JS portals")
    return None
