"""ZONE 1b — fetch + cache document bodies.

Discovery (Zone 1a) yields URLs; this module downloads the actual law text/PDF so
extraction has something to read. It is the piece that closes the live-crawl loop.

Design goals — be a good citizen AND be cheap to re-run:
  • polite        — robots.txt is CHECKED (pipeline/robots.py), one User-Agent, and a
                    per-host delay that yields to a larger Crawl-delay the host asks for
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
from . import robots
from .. import metering

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


def _polite_wait(host: str, url: str | None = None) -> None:
    """Space requests to one host. A `Crawl-delay` the host itself asks for WINS over our
    default whenever it is larger — our setting is a floor on politeness, not a ceiling."""
    delay = settings.crawl_delay_seconds
    if url and settings.crawl_respect_robots:
        asked = robots.for_url(url).delay_for()
        if asked and asked > delay:
            delay = asked
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
    # China's National Laws database serves a large share of its statutes as WORD, not PDF,
    # and returns them as application/octet-stream — so the content type says nothing and only
    # the URL does. Without this they fell through to TEXT and were read as raw bytes: a .docx
    # is a ZIP, so the "text" began "PK docProps/app.xml" and split into one junk provision.
    # Kept on DocFormat.TEXT (routed by extension in ocr._extract_document_text) rather than
    # adding an enum member, because DocFormat values are written into exports.
    if low.endswith((".docx", ".doc")) or "wordprocessingml" in ct or "msword" in ct:
        return DocFormat.TEXT, ("docx" if low.endswith(".docx") or "wordprocessingml" in ct
                                else "doc")
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
    or when every engine fails. Bodies younger than fetch_ttl_hours are reused without a
    network round-trip; past the TTL the body is re-fetched (Scrapling primary, httpx
    fallback) and deduped by SHA-256."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None

    # robots.txt, BEFORE the cache check as well as before the network. A rule that appears
    # after we already cached a body still governs whether we may use it, and on 15 October
    # five tools read the same government sites within the same hour — the politeness claim
    # in the README has to be true of the code, not of our intentions.
    ok, why = robots.allowed(url)
    if not ok:
        log(f"[fetch] SKIPPED by robots.txt: {url} ({why})")
        return None
    if why:
        log(f"[fetch] robots: {why}")

    idx = _load_index()
    # TTL: a recently-fetched body is reused without any network round-trip
    prior = idx.get(url)
    if prior and settings.fetch_ttl_hours > 0:
        cached = settings.cache_path / prior["file"]
        if cached.exists() and (time.time() - cached.stat().st_mtime) < settings.fetch_ttl_hours * 3600:
            log(f"[fetch] cache hit (<{settings.fetch_ttl_hours:g}h TTL): {url}")
            res = FetchResult(str(cached), DocFormat(prior["fmt"]), prior["sha256"],
                              prior.get("content_type", ""), True)
            res = _maybe_resolve_embedded_pdf(url, res, idx, log)
            return _maybe_render_spa(url, res, idx, log)
    engines = _engine_order()
    if _tls_relaxed(parsed.netloc):
        # Scrapling verifies TLS through curl and cannot be told not to, so on a host with a
        # known-expired certificate it burns three retries (~10s per document) before failing
        # every time. Go straight to the engine that can actually complete the request.
        engines = [e for e in engines if e != "scrapling"] or ["httpx"]
    said: list[str] = []

    def tee(m):                       # keep what the engines say, and still say it
        said.append(m)
        log(m)

    for engine in engines:
        res = (_scrapling_fetch(url, idx, tee) if engine == "scrapling"
               else _httpx_fetch(url, idx, tee))
        if res:
            res = _maybe_resolve_embedded_pdf(url, res, idx, log)
            res = _maybe_resolve_portal_body(url, res, idx, log)
            return _maybe_render_spa(url, res, idx, log)
    return _maybe_browser_after_block(url, said, idx, log)


def _maybe_browser_after_block(url: str, said: list[str], idx: dict, log) -> "FetchResult | None":
    """A refusal is the one failure a real browser can overturn. Escalate to it, once.

    `_maybe_render_spa` already renders — but only AFTER a successful fetch, and only when
    CRAWL_BROWSER is on, which it is not by default. So a portal that answers 403 to every
    engine was simply lost, even where the browser lane demonstrably clears it: measured on
    2026-08-30, peraturan.bpk.go.id refused httpx and Scrapling with 403 and served the
    stealth browser 43,946 bytes of the same page. Six of Indonesia's nine instruments were
    failing on exactly that, and `data/sources.yaml` had recorded "the browser lane clears
    it" since 21 August — the note was right and nothing acted on it.

    Narrow on purpose. Only a refusal (403/429) escalates: a 404 is a dead link and a DNS
    failure is a wrong host, and driving a browser at either wastes seconds to fail again.
    """
    if not settings.fetch_browser_on_block:
        return None
    tail = " ".join(said[-3:])
    if "HTTP 403" not in tail and "HTTP 429" not in tail:
        return None
    try:
        from . import scrapling_fetch
        if not scrapling_fetch.available():
            return None
        log(f"[fetch] refused by the portal, retrying in the stealth browser: {url}")
        r = scrapling_fetch.fetch(url, browser=True, log=log)
        if r and r.body and len(r.body) <= settings.fetch_max_bytes:
            res = _store(url, r.body, r.content_type, idx, None, None, log, engine=r.engine)
            if res:
                res = _maybe_resolve_embedded_pdf(url, res, idx, log)
                return _maybe_resolve_portal_body(url, res, idx, log)
    except Exception as e:  # noqa: BLE001 — an escalation must never crash the run
        log(f"[fetch] browser escalation failed ({type(e).__name__}): {url}")
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
        pdf = fetch_to_cache(pdf_url, log=log)   # recursive → TTL applies to the PDF too
        if pdf and pdf.fmt in (DocFormat.PDF_TEXT, DocFormat.PDF_SCANNED):
            return pdf
    except Exception as e:  # noqa: BLE001 — resolution is best-effort; keep the HTML body
        log(f"[fetch] embedded-PDF resolve skipped ({type(e).__name__}): {url}")
    return res


#: Portals that answer a document URL with a PAGE ABOUT the document. The page is not broken
#: and not a JS shell — it renders, it is the right instrument, and it contains no law — so
#: neither the SPA check nor the embedded-PDF check sees anything wrong with it. Only knowing
#: the portal helps. Each rule below is a measured route from the landing URL to the body.
_BODY_ROUTES = [
    # peraturan.bpk.go.id: /Details/<id>/<slug> is an ABSTRACT ("MATERI POKOK PERATURAN
    # Abstrak…", a summary with no articles). The statute is a separate PDF linked from it.
    # Nine of these were the whole Indonesian corpus; the linked PDF for UU 27/2022 carries
    # its 24 Pasal. Verified 2026-08-30.
    ("peraturan.bpk.go.id", re.compile(r'href="(/Download/\d+/[^"]+\.pdf)"', re.I)),
]

#: pravo.gov.ru's IPS answers `?docbody=&nd=<id>` with a FRAMESET — 586 characters of chrome
#: around an iframe, measured 2026-08-28. The body is in the frame, and its URL is derivable,
#: so this one is a rewrite rather than a scrape.
_IPS_WRAPPER_RE = re.compile(r"[?&]docbody=&nd=(\d+)", re.I)


def _maybe_resolve_portal_body(url: str, res: "FetchResult", idx: dict, log) -> "FetchResult":
    """Follow a known landing page to the instrument itself. Unchanged when there is no rule."""
    if res.fmt != DocFormat.HTML:
        return res
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        m = _IPS_WRAPPER_RE.search(url)
        if m and "pravo.gov.ru" in host:
            body = f"http://pravo.gov.ru/proxy/ips/?doc_itself=&nd={m.group(1)}&page=1&rdk=0"
            log(f"[fetch] IPS wrapper -> document frame: {body}")
            return _httpx_fetch(body, idx, log) or res
        for portal, rx in _BODY_ROUTES:
            if portal not in host:
                continue
            html = Path(res.local_path).read_text(encoding="utf-8", errors="ignore")
            hit = rx.search(html)
            if not hit:
                return res
            from urllib.parse import urljoin
            body = urljoin(url, hit.group(1))
            log(f"[fetch] landing page -> instrument: {body}")
            return fetch_to_cache(body, log=log) or res
    except Exception as e:  # noqa: BLE001 — best effort; keep the page we already have
        log(f"[fetch] body resolution skipped ({type(e).__name__}): {url}")
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


# Official portals whose TLS certificate is expired or misconfigured on their side.
#
# `wb.flk.npc.gov.cn` is the static document host of China's National Laws and Regulations
# Database — every statute PDF and DOCX the search index points at lives there — and its
# certificate has expired. Verifying it costs the entire economy: the fetch fails, discovery
# still reports the documents, and the run produces "No provision found" for all of China.
#
# Relaxing verification is a deliberate, NARROW trade. It is defensible only because all four
# of these hold, and it must not be widened without them:
#   1. the documents are public statutes — nothing confidential is requested;
#   2. no credential, cookie or token is ever sent to these hosts;
#   3. the fetched bytes are content-hashed (SHA-256) and stored, so a substituted body is
#      detectable after the fact rather than trusted blindly;
#   4. the alternative is not "more secure", it is "this country cannot be processed".
# It is an explicit host allowlist, never a global `verify=False`, and every use is logged.
#
# krisdika.go.th is the second entry, added 2026-08-21 for the same reason and under the same
# four conditions. It is the Office of the Council of State — Thailand's own law library, and
# the primary source for a live-test economy — and it serves a SELF-SIGNED certificate. Both
# the plain client and the browser lane refuse it (curl error 60), so with verification on,
# Thailand has no primary portal at all rather than a degraded one.
_TLS_RELAXED_HOSTS = {"wb.flk.npc.gov.cn", "krisdika.go.th"}


def _tls_relaxed(host: str) -> bool:
    host = (host or "").lower().split(":")[0]
    return any(host == h or host.endswith("." + h) for h in _TLS_RELAXED_HOSTS)


def _why(e: Exception) -> str:
    """A failure description an operator can act on: the HTTP status when there is one, the
    transport problem when there is not."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None)
    if code:
        meaning = {401: "auth", 403: "blocked (WAF/bot rule)", 404: "not found — dead link",
                   410: "gone", 429: "rate-limited", 451: "legally blocked",
                   500: "server error", 502: "bad gateway", 503: "unavailable",
                   504: "gateway timeout"}.get(code, "")
        return f"HTTP {code}{' — ' + meaning if meaning else ''}"
    name = type(e).__name__
    if "ConnectTimeout" in name or "ReadTimeout" in name or "Timeout" in name:
        return "timeout"
    if "ConnectError" in name and "getaddrinfo" in str(e):
        return "DNS: host does not resolve"
    if "ConnectError" in name:
        return f"connect failed: {str(e)[:60]}"
    if "SSL" in name or "Certificate" in name:
        return f"TLS: {str(e)[:60]}"
    return f"{name}: {str(e)[:60]}"


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

    _polite_wait(host, url)
    verify = not _tls_relaxed(host)
    if not verify:
        log(f"[fetch] TLS verification relaxed for {host} (see fetch._TLS_RELAXED_HOSTS)")
    try:
        with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=_headers(cond),
                          follow_redirects=True, verify=verify) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code == 304 and prior:        # unchanged → reuse cache
                    cached_path = settings.cache_path / prior["file"]
                    import os
                    os.utime(cached_path)                    # renew the TTL window
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
        # The KIND of failure decides what to do about it, and "HTTPStatusError" says none of
        # it. Diagnosing twenty Indian fetch failures meant re-probing every URL by hand,
        # because the only thing recorded was the exception's class name. They turned out to
        # be four different problems needing four different answers: 403 (a WAF, which the
        # browser lane clears), 404 (the panel's own link has rotted — nothing to fix here and
        # a fact worth knowing), DNS failure, and connect timeout.
        log(f"[fetch] httpx failed ({_why(e)}): {url}")
        return None
    return _store(url, bytes(buf), content_type, idx, etag, last_mod, log)


def _store(url, data: bytes, content_type: str, idx: dict, etag, last_mod, log,
           engine: str = "httpx") -> "FetchResult | None":
    """Content-address `data` into the cache and update the resumable index. Shared by the
    httpx and Scrapling fetch paths so both dedupe identically. Returns None when a `.pdf` URL
    actually served non-PDF bytes (a dead/moved link redirected to a portal homepage — e.g.
    pdp.gov.my's old /jpdpv2/ paths): the document is unavailable, so skip it rather than feed
    HTML to the PDF parser (garbage) or emit the homepage's nav text as a bogus provision."""
    fmt, ext = _fmt_for(content_type, url)
    if fmt in (DocFormat.PDF_TEXT, DocFormat.PDF_SCANNED) and b"%PDF-" not in data[:1024]:
        log(f"[fetch] .pdf URL served non-PDF bytes (dead/moved link) -> skipping: {url}")
        return None
    metering.record_fetch(len(data))     # bytes actually pulled over the wire
    sha = hashlib.sha256(data).hexdigest()
    fname = f"{sha[:16]}.{ext}"
    path = settings.cache_path / fname
    if not path.exists():                       # content-addressed → identical bodies dedupe
        path.write_bytes(data)
        log(f"[fetch] cached {len(data)//1000} KB -> {fname} via {engine}  ({url})")
    else:
        import os
        os.utime(path)                          # renew the TTL window on revalidation
        log(f"[fetch] dedup (same content) -> {fname}  ({url})")
    idx[url] = {"file": fname, "sha256": sha, "fmt": fmt.value, "content_type": content_type,
                "etag": etag, "last_modified": last_mod, "bytes": len(data), "engine": engine}
    _save_index(idx)
    return FetchResult(str(path), fmt, sha, content_type, False)


def seed_cache(url: str, data: bytes, content_type: str = "text/html",
               log: Callable[[str], None] = print) -> FetchResult | None:
    """Put a body we already hold into the cache, as if it had been fetched.

    Some portals hand the document text back with the SEARCH RESULT rather than at a URL —
    India Code's DSpace API returns each section's operative text inline, and its HTML front
    end currently answers 502, so re-requesting the citable URL would fail while the text sits
    in memory. Seeding keeps every downstream stage identical: extraction, hashing, the audit
    trail and the second-pass "fetched nothing" proof all work on a cache entry and do not care
    how it got there.

    It is deliberately NOT a way to inject arbitrary content. The caller must already have the
    bytes from the portal, and they are content-hashed like any other body, so an audit can
    still tell what was stored and when.
    """
    idx = _load_index()
    return _store(url, data, content_type, idx, None, None, log, engine="api")


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
    _polite_wait(urlparse(url).netloc, url)
    res = scrapling_fetch.fetch(url, log=log)
    if not res:
        return None
    if len(res.body) > settings.fetch_max_bytes:
        log(f"[fetch] scrapling body over cap: {url}")
        return None
    log(f"[fetch] fetched via {res.engine} (status {res.status}): {url}")
    return _store(url, res.body, res.content_type, idx, None, None, log, engine=res.engine)
