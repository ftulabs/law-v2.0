"""ZONE 1a — web-search discovery.

The human workflow (ESCAP slide A) searches "official databases, government websites,
AND THE WEB". The portals' own search boxes are JS/token-gated, but a general web
search reaches the same primary sources and GENERALISES to any economy (we only need
the official-portal domain, not a hard-coded law list — the engine still finds the law).

Strategy: query DuckDuckGo's HTML endpoint (no API key) with the topic + a
`site:<official-portal>` filter, then keep result URLs on that portal. Portal-agnostic;
add a domain per economy in OFFICIAL_PORTAL and it works for Thailand/India/etc. too.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from ..config import settings
from ..schemas import Economy

# Official primary-source portals per economy (domain only — NOT specific laws).
OFFICIAL_PORTAL: dict[str, str] = {
    "SG": "sso.agc.gov.sg",
    "AU": "legislation.gov.au",
    "MY": "lom.agc.gov.my",
    # Final-round economies — add the domain, discovery generalises automatically:
    "TH": "law.go.th",
    "IN": "indiacode.nic.in",
    "ID": "peraturan.go.id",
}

def _clean_ddg(href: str) -> str:
    """DuckDuckGo wraps results as /l/?uddg=<encoded>. Unwrap to the real URL."""
    if "duckduckgo.com/l/" in href or href.startswith("/l/") or href.startswith("//duckduckgo.com/l/"):
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            return q["uddg"][0]
    return href


def _parse(html: str, selector: str, max_results: int) -> list[tuple[str, str, str]]:
    """Return (url, title, snippet) results. Keyless HTML engines expose no reliable
    per-result snippet, so snippet is "" — content-relevance ranking degrades gracefully
    to title-only for them (the keyed Serper path below carries real snippets)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.select(selector):
        href = _clean_ddg(a.get("href", ""))
        if href.startswith("//"):
            href = "https:" + href
        title = a.get_text(" ", strip=True)
        if href.startswith("http") and href not in seen:
            seen.add(href)
            out.append((href, title, ""))
        if len(out) >= max_results:
            break
    return out


# Serper.dev — Google results as JSON (reliable deep links); used first if a key is set.
def _serper(client, q, n):
    if not settings.serper_api_key:
        return []
    r = client.post("https://google.serper.dev/search",
                    headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                    json={"q": q, "num": max(n, 10)})
    if r.status_code != 200:
        return []
    out = []
    for it in r.json().get("organic", []):
        link = it.get("link", "")
        if link.startswith("http"):
            # snippet = Google's query-biased content preview; the signal that lets discovery
            # rank by what a law is ABOUT (generic indicator terms) rather than by its name.
            out.append((link, it.get("title", ""), it.get("snippet", "")))
    return out[:n]


# Independent engines — try in order until one returns results (engines rate-limit).
def _ddg_html(client, q, n):
    r = client.post("https://html.duckduckgo.com/html/", data={"q": q})
    return _parse(r.text, "a.result__a", n) if r.status_code == 200 else []


def _ddg_lite(client, q, n):
    r = client.post("https://lite.duckduckgo.com/lite/", data={"q": q})
    return _parse(r.text, "a.result-link", n) if r.status_code == 200 else []


def _mojeek(client, q, n):
    r = client.get("https://www.mojeek.com/search", params={"q": q})
    return _parse(r.text, "a.title, ul.results-standard li a", n) if r.status_code == 200 else []


def _scrapling_ddg(client, q, n):
    """Last-resort engine: fetch DuckDuckGo's HTML via Scrapling's impersonating Fetcher.
    When the httpx engines above are rate-limited/blocked (their TLS fingerprint is flagged),
    Scrapling's real-browser fingerprint often still gets through. Ignores the httpx client."""
    try:
        from . import scrapling_fetch
    except Exception:
        return []
    if not scrapling_fetch.available():
        return []
    from urllib.parse import quote_plus
    res = scrapling_fetch.fetch(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}", log=lambda *_: None)
    if not res:
        return []
    return _parse(res.body.decode("utf-8", "ignore"), "a.result__a", n)


# Scrapling is the PRIMARY scraper (its real-browser fingerprint is the reliable path the
# user trusts); Serper stays first only when an API key makes it a clean JSON call. The
# plain-httpx engines drop to fallback. Order is reversed to httpx-first when
# settings.crawl_fetcher == "httpx".
_ENGINES_SCRAPLING_FIRST = [_serper, _scrapling_ddg, _ddg_html, _ddg_lite, _mojeek]
_ENGINES_HTTPX_FIRST = [_serper, _ddg_html, _ddg_lite, _mojeek, _scrapling_ddg]


# Circuit breaker for the keyless engines. DuckDuckGo resets the TLS connection after ~a dozen
# queries; each further query then wastes ~60s on Scrapling's 3 retries, so a 48-query
# round-robin run would hang ~50 min. We count CONSECUTIVE empty results: after _SOFT we drop
# the slow Scrapling-retry engine (further probes fail in seconds), after _HARD we stop hitting
# the network entirely and discovery proceeds with the laws already found. A keyed Serper run
# never trips it (Serper is reliable). State is per-process; reset_circuit() clears it per run.
_circuit = {"empties": 0}
_SOFT, _HARD = 2, 6


def reset_circuit() -> None:
    _circuit["empties"] = 0


def _engines() -> list:
    base = (_ENGINES_HTTPX_FIRST if (settings.crawl_fetcher or "scrapling").lower() == "httpx"
            else _ENGINES_SCRAPLING_FIRST)
    if _circuit["empties"] >= _SOFT:
        base = [e for e in base if e is not _scrapling_ddg]   # drop the ~60s retry path
    return base


def _cache_file():
    return settings.cache_path / "_search.json"


def _load_cache() -> dict:
    f = _cache_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def search(query: str, site: str | None = None, max_results: int = 10, log=print) -> list[tuple[str, str, str]]:
    """Return (url, title, snippet) results. Tries Serper (if keyed) then scrapes
    DuckDuckGo/Mojeek so a single rate-limit/captcha doesn't break discovery. Results are
    cached on disk; older 2-tuple cache entries are padded with an empty snippet."""
    try:
        import httpx
    except Exception:
        return []
    q = query + (f" site:{site}" if site else "")
    cache = _load_cache()
    if q in cache:                                  # cache hit — no network, no rate-limit
        return [(r[0], r[1], r[2] if len(r) > 2 else "") for r in cache[q]]
    if _circuit["empties"] >= _HARD and not settings.serper_api_key:
        return []                                   # circuit open — engines blocked, skip network

    headers = {"User-Agent": settings.crawl_user_agent,
               "Accept-Language": settings.crawl_accept_language,
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    results: list[tuple[str, str]] = []
    with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=headers, follow_redirects=True) as client:
        for engine in _engines():
            try:
                results = engine(client, q, max_results)
            except Exception as e:  # noqa: BLE001
                log(f"[websearch] {engine.__name__} error ({type(e).__name__})")
                results = []
            if results:
                break
    if results:
        _circuit["empties"] = 0
        cache[q] = results
        _cache_file().write_text(json.dumps(cache, indent=1), encoding="utf-8")
    else:
        _circuit["empties"] += 1
        msg = f"[websearch] all engines empty for '{q}'"
        if _circuit["empties"] == _HARD and not settings.serper_api_key:
            msg += " — engines blocked; circuit OPEN. Set SERPER_API_KEY for reliable discovery."
        log(msg)
    return results


# portal landing/navigation pages that are not a specific law — never a useful result
_NAV_PATHS = {"", "/", "/index", "/home", "/search", "/browse", "/login", "/about", "/help"}


def _is_law_url(url: str) -> bool:
    """Reject portal roots and nav pages (e.g. 'https://sso.agc.gov.sg/') so the homepage
    can't outrank an actual statute; a real law URL always has a content path segment."""
    path = urlparse(url).path.rstrip("/").lower()
    return path not in _NAV_PATHS and len(path) > 1


def find_law_urls(economy: Economy, topic: str, max_results: int = 10, log=print) -> list[tuple[str, str, str]]:
    """Discover candidate (url, title, snippet) primary-law results on the economy's official portal."""
    site = OFFICIAL_PORTAL.get(economy.value)
    results = search(topic, site=site, max_results=max_results, log=log)
    if site:   # keep only the official portal (drop news/blog noise the engine mixes in)
        results = [r for r in results if site in urlparse(r[0]).netloc.lower()]
    results = [r for r in results if _is_law_url(r[0])]   # drop homepage/nav noise
    return results
