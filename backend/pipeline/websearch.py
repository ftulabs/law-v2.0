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


class EngineUnavailable(Exception):
    """An engine could not answer at all — a spent key, a rate limit, a challenge page.

    Deliberately distinct from an engine that answered with zero results. Collapsing the
    two is what made a dead Serper key read as "Singapore has no data-protection law":
    measured 2026-09-07, `_serper` returned [] on HTTP 400 "Not enough credits" and nothing
    anywhere recorded that the engine had failed.
    """

    def __init__(self, engine: str, detail: str):
        self.engine, self.detail = engine, detail
        super().__init__(f"{engine}: {detail}")


#: Per-run discovery provenance. Reset by `reset_diagnostics()` at the top of every run, so a
#: dashboard process that serves many runs cannot attribute one run's failures to the next.
_diag: dict = {"cache_hits": 0, "network_queries": 0, "empty_queries": 0,
               "engine_failures": {}}


def diagnostics() -> dict:
    """A copy of this run's search provenance — what came from cache, what hit the network,
    and which engines were unavailable. Read by `discovery.explain_empty_discovery`."""
    return {**_diag, "engine_failures": dict(_diag["engine_failures"])}


# Official primary-source portals per economy (domain only — NOT specific laws).
OFFICIAL_PORTAL: dict[str, str] = {
    "SG": "sso.agc.gov.sg",
    "AU": "legislation.gov.au",
    "MY": "lom.agc.gov.my",
    # Round-2 economies:
    "CN": "flk.npc.gov.cn",      # National Laws and Regulations Database (NPC) — the official one
    "IN": "indiacode.nic.in",    # India Code — official repository of Central Acts
    "MN": "legalinfo.mn",        # Unified Legal Information System of Mongolia
    # Later finals — add the domain, discovery generalises automatically:
    "TH": "law.go.th",
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
    # One billable credit per query, counted at the moment it is spent. Serper charges the
    # attempt, so this sits before the request rather than after a successful parse — a table
    # that only counts successes understates the bill.
    from .. import metering
    metering.record_search("serper")
    r = client.post("https://google.serper.dev/search",
                    headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                    json={"q": q, "num": max(n, 10)})
    if r.status_code != 200:
        try:
            detail = r.json().get("message") or r.text[:120]
        except Exception:                                    # noqa: BLE001 — not JSON
            detail = r.text[:120]
        raise EngineUnavailable("serper", f"HTTP {r.status_code} — {detail}")
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
    if r.status_code != 200:
        # 202 is DuckDuckGo's anomaly/challenge page, not an empty result set.
        raise EngineUnavailable("ddg_html", f"HTTP {r.status_code}"
                                            f"{' (challenge page)' if r.status_code == 202 else ''}")
    return _parse(r.text, "a.result__a", n)


def _ddg_lite(client, q, n):
    r = client.post("https://lite.duckduckgo.com/lite/", data={"q": q})
    if r.status_code != 200:
        raise EngineUnavailable("ddg_lite", f"HTTP {r.status_code}"
                                            f"{' (challenge page)' if r.status_code == 202 else ''}")
    return _parse(r.text, "a.result-link", n)


def _mojeek(client, q, n):
    r = client.get("https://www.mojeek.com/search", params={"q": q})
    if r.status_code != 200:
        raise EngineUnavailable("mojeek", f"HTTP {r.status_code}")
    return _parse(r.text, "a.title, ul.results-standard li a", n)


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
# the network entirely and discovery proceeds with the laws already found. State is per-process;
# reset_circuit() clears it per run.
#
# The circuit opens on _HARD consecutive failures REGARDLESS of whether serper_api_key is set.
# It used to exempt a configured key on the theory that a keyed Serper run is reliable and
# never trips it. That is false: a key can be configured and SPENT — ours answers
# HTTP 400 "Not enough credits" (measured 2026-09-07) — and `settings.serper_api_key` is a
# non-empty string either way, so the exemption made the circuit permanently un-openable
# whenever a key happened to be set, spent or not. A spent key is WORSE than no key: with no
# key the circuit opens after _HARD failures and the run moves on; with a dead key every one
# of the (up to 48) queries in a round-robin run waited out its full network timeout, which is
# what starved India's `in_dspace` lane of its 600s budget entirely (measured 2026-09-07,
# `discovery.discover(Economy.IN, 6, use_samples=False)`). A healthy key never accumulates
# _HARD consecutive failures, so this guard costs nothing when things work — it only fires
# once search is already useless, keyed or not.
_circuit = {"empties": 0}
_SOFT, _HARD = 2, 6


def reset_diagnostics() -> None:
    """Zero the per-RUN search provenance. Called once per run by the orchestrator.

    Kept separate from reset_circuit() because the circuit breaker is per-LANE:
    discover_websearch resets it for every web-search source of every pillar (the loop
    in discovery.discover_live), so an economy with four lanes across two pillars resets
    it eight times. Conflating the two made explain_empty_discovery report the last lane's
    counters as the whole run's, and let it assert "every engine answered" when an earlier
    lane had failed.
    """
    _diag.update(cache_hits=0, network_queries=0, empty_queries=0)
    _diag["engine_failures"] = {}


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


def _entry_results(entry, now: float | None = None) -> list | None:
    """Usable results from a cache entry, or None meaning "treat as a miss".

    Entries written before 2026-09-07 are a bare list with no timestamp. They cannot be
    shown to be fresh, so they expire by construction rather than being trusted by default —
    that default is what let a week-old cache stand in for live discovery.
    """
    import datetime as _dt

    max_age = settings.search_cache_max_age_days
    if max_age <= 0 or not isinstance(entry, dict):
        return None
    stamp = entry.get("fetched_at")
    rows = entry.get("results")
    if not stamp or not isinstance(rows, list):
        return None
    try:
        fetched = _dt.datetime.fromisoformat(stamp)
        if fetched.tzinfo is None:
            # A stamp with no offset is NAIVE; .timestamp() would then read it in the
            # host's local zone and skew the age by the UTC offset. Our own writer always
            # emits a tz-aware stamp — this only guards a hand-edited or future non-UTC entry.
            fetched = fetched.replace(tzinfo=_dt.timezone.utc)
        age_days = ((now or _dt.datetime.now(_dt.timezone.utc).timestamp())
                    - fetched.timestamp()) / 86400.0
    except (ValueError, TypeError):
        return None
    if age_days > max_age:
        return None
    # This comprehension used to sit outside the try above, so a row that was a string (not
    # a list) or shorter than two elements raised IndexError/TypeError instead of being
    # declined. That mattered more once the expiry-prune below started calling this on every
    # entry in the cache on every successful write, not just on the key being queried — one
    # corrupted neighbour then broke every search, not just its own. A plain string still
    # answers to r[0]/r[1] without raising (it silently indexes into characters), so this
    # checks the shape explicitly rather than trusting an exception to catch it.
    out = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 2:
            return None
        out.append((r[0], r[1], r[2] if len(r) > 2 else ""))
    return out


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
    hit = _entry_results(cache.get(q))
    if hit is not None:                             # fresh hit — no network, no rate-limit
        _diag["cache_hits"] += 1
        return hit
    if _circuit["empties"] >= _HARD:
        return []                                   # circuit open — engines blocked, skip network
    _diag["network_queries"] += 1

    headers = {"User-Agent": settings.crawl_user_agent,
               "Accept-Language": settings.crawl_accept_language,
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    results: list[tuple[str, str]] = []
    with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=headers, follow_redirects=True) as client:
        for engine in _engines():
            try:
                results = engine(client, q, max_results)
            except EngineUnavailable as e:
                _diag["engine_failures"][e.engine] = e.detail
                log(f"[websearch] {e.engine} unavailable — {e.detail}")
                results = []
            except Exception as e:  # noqa: BLE001
                log(f"[websearch] {engine.__name__} error ({type(e).__name__})")
                results = []
            if results:
                break
    if results:
        _circuit["empties"] = 0
        import datetime as _dt
        cache[q] = {"results": [list(r) for r in results],
                    "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    "engine": getattr(engine, "__name__", "?")}
        if settings.search_cache_max_age_days > 0:
            # Nothing else prunes this file: `_entry_results()` only declines to SERVE a
            # stale entry, so without this the dict only grows — 890 entries from 2026-08-31
            # were still being re-serialised on every successful query, at 1.6 MB. Drop
            # already-expired keys on every write instead. Guarded on the TTL being enabled:
            # at max_age_days<=0, `_entry_results` treats EVERY entry (including the one just
            # written above) as expired, which would empty the file on the next write.
            cache = {k: v for k, v in cache.items() if _entry_results(v) is not None}
        _cache_file().write_text(json.dumps(cache, indent=1), encoding="utf-8")
    else:
        _circuit["empties"] += 1
        _diag["empty_queries"] += 1
        msg = f"[websearch] all engines empty for '{q}'"
        if _circuit["empties"] == _HARD:
            if settings.serper_api_key:
                # A configured key failing _HARD times running is the more urgent case — it
                # reads as "reliable" until it silently isn't. Name the specific engines that
                # failed (diagnostics() already records each one) rather than a generic hint.
                failures = ", ".join(f"{e}: {d}" for e, d in _diag["engine_failures"].items()) or "no detail captured"
                msg += (f" — engines blocked; circuit OPEN despite a configured SERPER_API_KEY. "
                        f"The key may be spent or invalid — {failures}.")
            else:
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


def find_law_urls(economy: Economy, topic: str, max_results: int = 10, log=print,
                  site: str | None = None) -> list[tuple[str, str, str]]:
    """Discover candidate (url, title, snippet) primary-law results on a portal. Defaults to the
    economy's OFFICIAL_PORTAL; pass `site` to scope to a secondary official portal (e.g. a sectoral
    regulator like Malaysia's pdp.gov.my for the registered Codes of Practice)."""
    site = site or OFFICIAL_PORTAL.get(economy.value)
    results = search(topic, site=site, max_results=max_results, log=log)
    if site:   # keep only the official portal (drop news/blog noise the engine mixes in)
        results = [r for r in results if site in urlparse(r[0]).netloc.lower()]
    results = [r for r in results if _is_law_url(r[0])]   # drop homepage/nav noise
    return results
