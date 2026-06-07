"""ZONE 1b — fetch + cache document bodies.

Discovery (Zone 1a) yields URLs; this module downloads the actual law text/PDF so
extraction has something to read. It is the piece that closes the live-crawl loop.

Design goals — be a good citizen AND be cheap to re-run:
  • polite        — one User-Agent, a per-host delay between requests
  • incremental   — conditional GET (ETag / Last-Modified); a 304 reuses the cache
  • content-addressed — files are named by SHA-256, so identical bodies dedupe for free
  • bounded       — a hard byte cap refuses to pull a 500 MB consolidated PDF
  • resumable     — an on-disk index means a second run skips already-fetched URLs

Nothing here imports heavy libs; httpx is the only dependency and is already required.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from ..config import settings
from ..schemas import DocFormat

_INDEX_NAME = "_index.json"
_last_request: dict[str, float] = {}   # host → monotonic timestamp of last hit (politeness)


@dataclass
class FetchResult:
    local_path: str
    fmt: DocFormat
    sha256: str
    content_type: str
    from_cache: bool


def _index_file() -> Path:
    return settings.cache_path / _INDEX_NAME


def _load_index() -> dict:
    f = _index_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_index(idx: dict) -> None:
    _index_file().write_text(json.dumps(idx, indent=2, sort_keys=True), encoding="utf-8")


def _polite_wait(host: str) -> None:
    delay = settings.crawl_delay_seconds
    last = _last_request.get(host)
    if last is not None:
        elapsed = time.monotonic() - last
        if elapsed < delay:
            time.sleep(delay - elapsed)
    _last_request[host] = time.monotonic()


def _headers(extra: dict | None = None) -> dict:
    h = {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    }
    if extra:
        h.update(extra)
    return h


def _fmt_for(content_type: str, url: str) -> tuple[DocFormat, str]:
    """Map a response to (DocFormat, file-extension)."""
    ct = (content_type or "").lower()
    low = url.lower()
    if "pdf" in ct or low.endswith(".pdf"):
        return DocFormat.PDF_TEXT, "pdf"        # extraction auto-detects scanned → OCR
    if "html" in ct or low.endswith((".html", ".htm")) or (ct == "" and "<" in low):
        return DocFormat.HTML, "html"
    if "html" in ct:
        return DocFormat.HTML, "html"
    return DocFormat.TEXT, "txt"


def _engine_order() -> list[str]:
    """Which fetch engines to try, in order, from settings.crawl_fetcher:
      scrapling (default) → Scrapling primary, httpx fallback
      httpx               → httpx primary, Scrapling escalation
      auto                → Scrapling if installed, else httpx
    Default is Scrapling-first: its real-browser fingerprint is the more reliable crawler
    against bot-protected government portals, so we don't wait for httpx to fail first."""
    mode = (settings.crawl_fetcher or "scrapling").lower()
    try:
        from . import scrapling_fetch
        has_scrapling = scrapling_fetch.available()
    except Exception:
        has_scrapling = False
    if mode == "httpx" or not has_scrapling:
        return ["httpx", "scrapling"] if has_scrapling else ["httpx"]
    return ["scrapling", "httpx"]


def fetch_to_cache(url: str, log: Callable[[str], None] = print) -> FetchResult | None:
    """Download `url` into the content-addressed cache. Returns None for non-HTTP URLs
    (e.g. file://) or when every engine fails — callers fall back to any local_path.

    Scrapling is the PRIMARY fetcher by default (settings.crawl_fetcher); httpx is the
    fallback. Both store through the same content-addressed cache, so switching engines
    never re-downloads an identical body."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    idx = _load_index()
    for engine in _engine_order():
        res = (_scrapling_fetch(url, idx, log) if engine == "scrapling"
               else _httpx_fetch(url, idx, log))
        if res:
            res = _maybe_resolve_embedded_pdf(url, res, idx, log)
            return _maybe_render_spa(url, res, idx, log)
    return None


# A landing page that embeds the actual law in a PDF.js viewer, e.g. MY's
# act-detail.php: <iframe src="pdfjs/web/viewer.html?file=../../../ilims/.../Act 709.pdf">.
# The visible HTML is just chrome (≈1 KB → one bogus provision); the law text is the PDF.
_EMBEDDED_PDF_RE = re.compile(r"""viewer\.html\?file=([^"'&]+\.pdf)""", re.I)


def _maybe_resolve_embedded_pdf(url: str, res: "FetchResult", idx: dict, log) -> "FetchResult":
    """If an HTML page embeds the real document in a PDF viewer, fetch that PDF instead so
    extraction reads the law, not the landing-page chrome. Returns the PDF result, or the
    original HTML unchanged when there is no embedded PDF (or it can't be fetched)."""
    if res.fmt != DocFormat.HTML:
        return res
    try:
        html = Path(res.local_path).read_text(encoding="utf-8", errors="ignore")
        m = _EMBEDDED_PDF_RE.search(html)
        if not m:
            return res
        from urllib.parse import urljoin, unquote
        # the file= path is relative to the viewer's own location (…/pdfjs/web/viewer.html)
        viewer_base = urljoin(url, "pdfjs/web/viewer.html")
        pdf_url = urljoin(viewer_base, unquote(m.group(1)))
        if pdf_url == url:
            return res
        log(f"[fetch] HTML embeds a PDF viewer, fetching the document: {pdf_url}")
        pdf = (_scrapling_fetch(pdf_url, idx, log) if "scrapling" in _engine_order()
               else None) or _httpx_fetch(pdf_url, idx, log)
        if pdf and pdf.fmt in (DocFormat.PDF_TEXT, DocFormat.PDF_SCANNED):
            return pdf
    except Exception as e:  # noqa: BLE001 — resolution is best-effort; keep the HTML body
        log(f"[fetch] embedded-PDF resolve skipped ({type(e).__name__}): {url}")
    return res


def _maybe_render_spa(url: str, res: "FetchResult", idx: dict, log) -> "FetchResult":
    """If a static fetch returned an unrendered single-page-app shell (e.g.
    legislation.gov.au) and CRAWL_BROWSER is enabled, re-fetch through Scrapling's stealth
    browser so the law text actually renders. Returns the original result unchanged when the
    page isn't a shell, the feature is off, or rendering doesn't improve it."""
    if res.fmt != DocFormat.HTML or not settings.crawl_browser:
        return res
    try:
        html = Path(res.local_path).read_text(encoding="utf-8", errors="ignore")
        from .ocr import is_js_app_shell
        if not is_js_app_shell(html):
            return res
        from . import scrapling_fetch
        if not scrapling_fetch.available():
            return res
        log(f"[fetch] SPA shell detected, rendering in stealth browser: {url}")
        rendered = scrapling_fetch.fetch(url, browser=True, log=log)
        if rendered and len(rendered.body) <= settings.fetch_max_bytes \
                and not is_js_app_shell(rendered.body.decode("utf-8", "ignore")):
            return _store(url, rendered.body, rendered.content_type, idx, None, None, log,
                          engine=rendered.engine)
    except Exception as e:  # noqa: BLE001 — rendering is best-effort; keep the static body
        log(f"[fetch] SPA render skipped ({type(e).__name__}): {url}")
    return res


def _httpx_fetch(url: str, idx: dict, log) -> FetchResult | None:
    """Fetch via httpx with conditional GET (ETag/Last-Modified → 304 reuse) and a byte cap."""
    try:
        import httpx
    except Exception:
        return None
    host = urlparse(url).netloc
    prior = idx.get(url)
    cond: dict = {}
    if prior:
        cached_path = settings.cache_path / prior["file"]
        if cached_path.exists():
            if prior.get("etag"):
                cond["If-None-Match"] = prior["etag"]
            if prior.get("last_modified"):
                cond["If-Modified-Since"] = prior["last_modified"]

    _polite_wait(host)
    try:
        with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=_headers(cond),
                          follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code == 304 and prior:        # unchanged → reuse cache
                    cached_path = settings.cache_path / prior["file"]
                    log(f"[fetch] 304 not-modified, cache hit: {url}")
                    return FetchResult(str(cached_path), DocFormat(prior["fmt"]),
                                       prior["sha256"], prior.get("content_type", ""), True)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                clen = resp.headers.get("content-length")
                if clen and int(clen) > settings.fetch_max_bytes:
                    log(f"[fetch] skip — {int(clen)//1_000_000} MB exceeds cap: {url}")
                    return None

                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > settings.fetch_max_bytes:
                        log(f"[fetch] skip — body exceeded {settings.fetch_max_bytes//1_000_000} MB cap: {url}")
                        return None
                etag = resp.headers.get("etag")
                last_mod = resp.headers.get("last-modified")
    except Exception as e:  # noqa: BLE001 — network/HTTP errors must not crash a run
        log(f"[fetch] httpx failed ({type(e).__name__}): {url}")
        return None
    return _store(url, bytes(buf), content_type, idx, etag, last_mod, log)


def _store(url, data: bytes, content_type: str, idx: dict, etag, last_mod, log,
           engine: str = "httpx") -> FetchResult:
    """Content-address `data` into the cache and update the resumable index. Shared by the
    httpx and Scrapling fetch paths so both dedupe identically."""
    sha = hashlib.sha256(data).hexdigest()
    fmt, ext = _fmt_for(content_type, url)
    fname = f"{sha[:16]}.{ext}"
    path = settings.cache_path / fname
    if not path.exists():                       # content-addressed → identical bodies dedupe
        path.write_bytes(data)
        log(f"[fetch] cached {len(data)//1000} KB -> {fname} via {engine}  ({url})")
    else:
        log(f"[fetch] dedup (same content) -> {fname}  ({url})")
    idx[url] = {"file": fname, "sha256": sha, "fmt": fmt.value, "content_type": content_type,
                "etag": etag, "last_modified": last_mod, "bytes": len(data), "engine": engine}
    _save_index(idx)
    return FetchResult(str(path), fmt, sha, content_type, False)


def _scrapling_fetch(url: str, idx: dict, log) -> FetchResult | None:
    """Fetch through Scrapling (real-browser TLS impersonation; stealth browser when
    CRAWL_BROWSER=true) and store the body like any other. Primary fetcher by default;
    also the escalation when httpx is the primary and gets blocked."""
    try:
        from . import scrapling_fetch
    except Exception:
        return None
    if not scrapling_fetch.available():
        return None
    _polite_wait(urlparse(url).netloc)
    res = scrapling_fetch.fetch(url, log=log)
    if not res:
        return None
    if len(res.body) > settings.fetch_max_bytes:
        log(f"[fetch] scrapling body over cap: {url}")
        return None
    log(f"[fetch] fetched via {res.engine} (status {res.status}): {url}")
    return _store(url, res.body, res.content_type, idx, None, None, log, engine=res.engine)
