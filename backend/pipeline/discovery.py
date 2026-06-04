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
            relevance_score=_score(searchable, indicators),
            discovery_tag=DiscoveryTag(entry.get("discovery_tag", "KNOWN")),
            local_path=str(local),
        )
        docs.append(doc)
    # prioritise recently amended + relevant
    docs.sort(key=lambda d: (d.relevance_score, d.amendment_date or ""), reverse=True)
    return docs


# ─────────────────────────── live mode (skeleton) ───────────────────────────
def load_sources() -> list[dict]:
    f = ROOT / "data" / "sources.yaml"
    if not f.exists():
        return []
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("sources", [])


def discover_live(economy: Economy, pillar: int | None = None, max_docs: int = 10) -> list[DiscoveredDoc]:
    """Polite crawler skeleton. Returns [] if httpx/network unavailable — callers
    should fall back to sample mode. Real portal selectors go in sources.yaml."""
    try:
        import httpx
        from bs4 import BeautifulSoup
    except Exception:
        return []

    indicators = get_indicators(pillar)
    query = " ".join(sorted({t for ind in indicators for t in ind.query_terms})[:5])
    headers = {"User-Agent": settings.crawl_user_agent}
    docs: list[DiscoveredDoc] = []

    for src in load_sources():
        if src.get("economy") != economy.value or not src.get("search_url_template"):
            continue
        url = src["search_url_template"].replace("{query}", httpx.QueryParams({"q": query})["q"])
        try:
            with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=headers, follow_redirects=True) as c:
                resp = c.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select(src.get("result_link_selector", "a"))[:max_docs]:
                    href = a.get("href")
                    if not href:
                        continue
                    full = httpx.URL(url).join(href).human_repr()
                    fmt = DocFormat.PDF_TEXT if full.lower().endswith(".pdf") else DocFormat.HTML
                    docs.append(DiscoveredDoc(
                        doc_id=_doc_id(economy.value, full),
                        economy=economy,
                        title=a.get_text(strip=True) or full,
                        source_url=full,
                        portal=src.get("name", "live"),
                        fmt=fmt,
                        relevance_score=_score(a.get_text(" ", strip=True), indicators),
                        discovery_tag=DiscoveryTag.NEW,
                    ))
        except Exception:
            continue
    docs.sort(key=lambda d: d.relevance_score, reverse=True)
    return docs[:max_docs]


def discover(economy: Economy, pillar: int | None = None, use_samples: bool = True) -> list[DiscoveredDoc]:
    if use_samples:
        return discover_from_samples(economy, pillar)
    live = discover_live(economy, pillar)
    return live or discover_from_samples(economy, pillar)
