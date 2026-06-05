"""ZONE 1 — Legal discovery.

Two modes:
  • sample mode (default for demo): reads bundled docs from data/samples/<economy>/
    and the manifest in data/samples/manifest.yaml. Deterministic, offline.
  • live mode (optional): a polite HTTP crawler skeleton that hits a portal's
    search endpoint, fetches result pages, and classifies format. Wire real
    portals via data/sources.yaml. Playwright/Scrapy can drop in behind the same
    interface for JS-heavy portals.

Both modes return ranked DiscoveredDoc records tagged KNOWN/NEW. "KNOWN" = present
in the reference manifest; "NEW" = surfaced beyond the sample set (live crawl, or a
sample explicitly flagged new).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from ..config import ROOT, settings
from ..rdtii import get_indicators
from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, Indicator

SAMPLES_DIR = ROOT / "data" / "samples"
MANIFEST = SAMPLES_DIR / "manifest.yaml"


def _doc_id(economy: str, source_url: str) -> str:
    return f"{economy}-" + hashlib.sha1(source_url.encode()).hexdigest()[:10]


def _score(text_blob: str, indicators: list[Indicator]) -> float:
    """Relevance = indicator query-term coverage over the doc's searchable text."""
    blob = text_blob.lower()
    all_terms = {t.lower() for ind in indicators for t in ind.query_terms}
    if not all_terms:
        return 0.0
    hits = sum(1 for t in all_terms if t in blob)
    return round(min(1.0, hits / max(4, len(all_terms) * 0.25)), 3)


# ─────────────────────────── sample mode ───────────────────────────
def discover_from_samples(economy: Economy, pillar: int | None = None) -> list[DiscoveredDoc]:
    if not MANIFEST.exists():
        return []
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    indicators = get_indicators(pillar)
    docs: list[DiscoveredDoc] = []
    for entry in manifest.get("documents", []):
        if entry.get("economy") != economy.value:
            continue
        local = SAMPLES_DIR / entry["path"]
        searchable = entry.get("title", "")
        # include first chunk of the file so ranking sees the body, not just title
        if local.exists() and local.suffix in {".html", ".txt"}:
            searchable += " " + local.read_text(encoding="utf-8", errors="ignore")[:4000]
        sidecar = local.with_suffix(".ocr.txt")
        if sidecar.exists():
            searchable += " " + sidecar.read_text(encoding="utf-8", errors="ignore")[:4000]

        doc = DiscoveredDoc(
            doc_id=_doc_id(economy.value, entry["source_url"]),
            economy=economy,
            title=entry["title"],
            source_url=entry["source_url"],
            portal=entry.get("portal", "sample"),
            fmt=DocFormat(entry.get("format", "html")),
            amendment_date=entry.get("amendment_date"),
            law_number=entry.get("law_number"),
            relevance_score=_score(searchable, indicators),
            discovery_tag=DiscoveryTag(entry.get("discovery_tag", "KNOWN")),
            local_path=str(local),
        )
        docs.append(doc)
    # prioritise recently amended + relevant
    docs.sort(key=lambda d: (d.relevance_score, d.amendment_date or ""), reverse=True)
    return docs


# ─────────────────────────── live mode (config-driven adapters) ───────────────────────────
def load_sources() -> list[dict]:
    f = ROOT / "data" / "sources.yaml"
    if not f.exists():
        return []
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("sources", [])


def _headers() -> dict:
    return {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }


def _resolve_download(src: dict, abs_href: str) -> str:
    """Turn a result link into a fetchable body URL via the adapter's template."""
    import re as _re
    tmpl = src.get("download_url_template")
    if not tmpl:
        return abs_href
    doc_id = ""
    rx = src.get("id_regex")
    if rx:
        m = _re.search(rx, abs_href)
        doc_id = m.group(1) if m else ""
    return tmpl.replace("{href}", abs_href).replace("{id}", doc_id)


def _search_one(client, src: dict, query: str, economy: Economy, indicators, log) -> list[DiscoveredDoc]:
    """Fire one query at one portal, parse result links into candidate docs."""
    import httpx
    from bs4 import BeautifulSoup

    url = src["search_url_template"].replace("{query}", httpx.QueryParams({"q": query})["q"])
    out: list[DiscoveredDoc] = []
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 — bot blocks / network; report and move on
        log(f"[discover] {src.get('name','?')} query='{query}' failed ({type(e).__name__})")
        return out

    soup = BeautifulSoup(resp.text, "lxml")
    must = (src.get("link_must_contain") or "").lower()
    for a in soup.select(src.get("result_link_selector", "a")):
        href = a.get("href")
        if not href:
            continue
        abs_href = httpx.URL(url).join(href).human_repr()
        if must and must not in abs_href.lower():
            continue
        body_url = _resolve_download(src, abs_href)
        title = a.get_text(" ", strip=True) or abs_href
        fmt = DocFormat.PDF_TEXT if body_url.lower().endswith(".pdf") else DocFormat.HTML
        out.append(DiscoveredDoc(
            doc_id=_doc_id(economy.value, body_url),
            economy=economy,
            title=title[:200],
            source_url=body_url,
            portal=src.get("name", "live"),
            fmt=fmt,
            relevance_score=_score(title, indicators),
            discovery_tag=DiscoveryTag.NEW,
        ))
    return out


def _search_au_api(client, src: dict, query: str, economy: Economy, indicators, log) -> list[DiscoveredDoc]:
    """Australia: official OData JSON API. AU Acts are named by title not topic, so we
    run TWO queries per term and merge: contains(name,…) nails flagship Acts by name
    ('Privacy Act'→C2004A03712), while $search hits topic words in the full text to
    surface topically-relevant Acts that lack an obvious keyword title."""
    import re as _re
    tmpl = src.get("detail_url_template", "https://www.legislation.gov.au/{id}")
    qtok = {w for w in _re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    out: list[DiscoveredDoc] = []
    seen: set[str] = set()
    # contains(name,…) is precise and fast; $search (full-text) is slow and its
    # content-only hits get filtered out by the title-overlap score anyway.
    variants = [
        {"$filter": f"contains(name,'{query}') and collection eq 'Act'", "$top": "40"},
    ]
    for params in variants:
        try:
            r = client.get(src["api_base"], params=params, headers={"Accept": "application/json"})
            r.raise_for_status()
            items = r.json().get("value", [])
        except Exception as e:  # noqa: BLE001
            log(f"[discover] AU API query='{query}' ({'search' if '$search' in params else 'name'}) "
                f"failed ({type(e).__name__})")
            continue
        for it in items:
            tid, name = it.get("id"), (it.get("name") or "")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            # rank by how much of the search term appears in the TITLE — keeps flagship
            # name-matches (Privacy Act → 1.0) and drops $search content-only noise (1901
            # acts whose titles share no query word → 0.0, filtered out by the caller).
            ntok = {w for w in _re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2}
            score = round(len(qtok & ntok) / len(qtok), 3) if qtok else 0.0
            url = tmpl.replace("{id}", tid)
            out.append(DiscoveredDoc(
                doc_id=_doc_id(economy.value, url), economy=economy, title=name[:200],
                source_url=url, portal=src.get("name", "AU"), fmt=DocFormat.HTML,
                law_number=tid, relevance_score=score, discovery_tag=DiscoveryTag.NEW))
    return out


def _resolve_pdf_url(economy: Economy, url: str) -> tuple[str, DocFormat]:
    """Turn a law's landing URL into a fetchable full-text body URL + its format.
    SG SSO serves the whole Act as a PDF at ?ViewType=Pdf (verified); MY links are
    already direct PDFs; others fall back to the page itself."""
    from urllib.parse import urlsplit, urlunsplit
    low = url.lower()
    if low.endswith(".pdf"):
        return url, DocFormat.PDF_TEXT
    if economy.value == "SG" and ("/act/" in low or "/sl/" in low or "/acts-supp/" in low):
        s = urlsplit(url)
        return urlunsplit((s.scheme, s.netloc, s.path, "ViewType=Pdf", "")), DocFormat.PDF_TEXT
    return url, DocFormat.HTML


def discover_websearch(economy: Economy, pillar: int | None, max_docs: int) -> list[DiscoveredDoc]:
    """Discover laws via web search (slide A: 'search ... and the web') — portal-agnostic,
    generalises to any economy with an entry in websearch.OFFICIAL_PORTAL."""
    from . import websearch
    from ..rdtii.keywords import portal_search_queries
    topics = portal_search_queries(economy.value, pillar)
    by_url: dict[str, DiscoveredDoc] = {}
    for topic in topics:
        for url, title in websearch.find_law_urls(economy, topic, max_results=6):
            body_url, fmt = _resolve_pdf_url(economy, url)
            if body_url in by_url:
                continue
            by_url[body_url] = DiscoveredDoc(
                doc_id=_doc_id(economy.value, body_url), economy=economy,
                title=(title or url)[:200], source_url=body_url, portal=websearch.OFFICIAL_PORTAL.get(economy.value, "web"),
                fmt=fmt, relevance_score=0.0, discovery_tag=DiscoveryTag.NEW)
        if len(by_url) >= max_docs * 2:
            break
    return list(by_url.values())[:max_docs]


def discover_live(economy: Economy, pillar: int | None = None, max_docs: int | None = None) -> list[DiscoveredDoc]:
    """Search the economy's official portal(s) with coarse pillar keywords and return
    ranked candidate documents (NEW). Returns [] if httpx/bs4 or the network are
    unavailable — callers fall back to sample mode. Bodies are fetched later (Zone 1b).
    """
    try:
        import httpx  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
    except Exception:
        return []

    from ..rdtii.keywords import portal_search_queries
    max_docs = max_docs or settings.discovery_max_docs
    indicators = get_indicators(pillar)
    queries = portal_search_queries(economy.value, pillar)
    sources = [s for s in load_sources() if s.get("economy") == economy.value
               and (s.get("search_url_template") or s.get("adapter"))]
    if not sources:
        return []

    by_url: dict[str, DiscoveredDoc] = {}

    # web-search adapters (SG/MY/…): portal-agnostic, finds laws the JS search hides
    if any(s.get("adapter") == "websearch" for s in sources):
        for d in discover_websearch(economy, pillar, max_docs):
            by_url[d.source_url] = d

    # API / scrape adapters (AU JSON API; server-rendered portals)
    api_sources = [s for s in sources if s.get("adapter") not in ("websearch",)]
    if api_sources:
        import httpx
        with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=_headers(), follow_redirects=True) as client:
            for src in api_sources:
                searcher = _search_au_api if src.get("adapter") == "au_api" else _search_one
                for q in queries:
                    for d in searcher(client, src, q, economy, indicators, log=print):
                        prev = by_url.get(d.source_url)
                        if prev is None or d.relevance_score > prev.relevance_score:
                            by_url[d.source_url] = d
                    if len(by_url) >= max_docs * 3:
                        break

    # web-search docs carry score 0 (ranked later by CONTENT); keep them. Only drop
    # the API title-overlap zeros (content-only noise) when no web-search ran.
    docs = list(by_url.values())
    docs.sort(key=lambda d: d.relevance_score, reverse=True)
    return docs[:max_docs]


def doc_from_file(economy: Economy, path: str) -> DiscoveredDoc:
    """Build a DiscoveredDoc from a local file (the `--pdf` bypass-crawler path)."""
    p = Path(path)
    ext = p.suffix.lower()
    fmt = (DocFormat.PDF_TEXT if ext == ".pdf"
           else DocFormat.HTML if ext in (".html", ".htm")
           else DocFormat.TEXT)
    return DiscoveredDoc(
        doc_id=_doc_id(economy.value, str(p.resolve())),
        economy=economy, title=p.stem, source_url=p.resolve().as_uri(),
        portal="local-file", fmt=fmt, relevance_score=1.0,
        discovery_tag=DiscoveryTag.NEW, local_path=str(p),
    )


def discover(economy: Economy, pillar: int | None = None, use_samples: bool = True) -> list[DiscoveredDoc]:
    if use_samples:
        return discover_from_samples(economy, pillar)
    # Live mode is the SCORED path: retrieve from live portals only. Do NOT fall back to
    # the bundled sample corpus — the rubric forbids pre-downloaded files. An empty result
    # surfaces a real discovery failure (e.g. search rate-limited) instead of masking it.
    return discover_live(economy, pillar)
