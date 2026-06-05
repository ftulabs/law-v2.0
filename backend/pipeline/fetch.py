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


def fetch_to_cache(url: str, log: Callable[[str], None] = print) -> FetchResult | None:
    """Download `url` into the content-addressed cache. Returns None for non-HTTP URLs
    (e.g. file://) or on failure — callers fall back to any existing local_path."""
    try:
        import httpx
    except Exception:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc

    idx = _load_index()
    prior = idx.get(url)

    # conditional GET if we've seen this URL before and still have the file
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
        log(f"[fetch] failed ({type(e).__name__}: {e}): {url}")
        return None

    data = bytes(buf)
    sha = hashlib.sha256(data).hexdigest()
    fmt, ext = _fmt_for(content_type, url)
    fname = f"{sha[:16]}.{ext}"
    path = settings.cache_path / fname
    if not path.exists():                       # content-addressed → identical bodies dedupe
        path.write_bytes(data)
        log(f"[fetch] cached {len(data)//1000} KB → {fname}  ({url})")
    else:
        log(f"[fetch] dedup (same content) → {fname}  ({url})")

    idx[url] = {"file": fname, "sha256": sha, "fmt": fmt.value, "content_type": content_type,
                "etag": etag, "last_modified": last_mod, "bytes": len(data)}
    _save_index(idx)
    return FetchResult(str(path), fmt, sha, content_type, False)
