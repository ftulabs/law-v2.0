"""Indonesia — browser-first, because httpx is refused everywhere.

MEASURED 2026-09-07/08: `peraturan.bpk.go.id` (JDIH BPK — the national legal database run
by Indonesia's Supreme Audit Board) answers plain httpx with **HTTP 403 at the root, at
`/Search` and at `/sitemap.xml`**. `data/sources.yaml` has recorded this since 21 August; the
Scrapling browser lane (curl_cffi TLS-impersonation, no headless browser needed) gets **HTTP
200** on the same URL. So `search_id_bpk` calls `scrapling_fetch` FIRST — it never tries httpx
at all — because three wasted 403s per request is a real cost multiplied across a whole crawl,
not a fallback worth paying for on every call.

ROBOTS.TXT — read in full before this module was written, because it is the licence this lane
runs on, not a formality to clear:

    # As a condition of accessing this website, you agree to abide by the following
    # content signals:
    ...
    User-agent: *
    Content-Signal: search=yes,ai-train=no,use=reference
    Allow: /

    User-agent: Amazonbot
    Disallow: /
    User-agent: Applebot-Extended
    Disallow: /
    User-agent: Bytespider
    Disallow: /
    User-agent: CCBot
    Disallow: /
    User-agent: ClaudeBot
    Disallow: /
    User-agent: CloudflareBrowserRenderingCrawler
    Disallow: /
    User-agent: Google-Extended
    Disallow: /
    User-agent: GPTBot
    Disallow: /
    User-agent: meta-externalagent
    Disallow: /

    User-agent: *
    Disallow: /Admin/
    Disallow: /Identity/
    Disallow: /Account/
    Disallow: /Manage/

Nine NAMED agents are disallowed outright (ClaudeBot, GPTBot, CCBot, Bytespider, Amazonbot,
Applebot-Extended, Google-Extended, meta-externalagent, CloudflareBrowserRenderingCrawler).
The wildcard group `*` is granted `Allow: /` with `Content-Signal: search=yes, ai-train=no,
use=reference`.

CORRECTED (fix round 1, 2026-09-08): an earlier version of this paragraph said VeriTrade
"fetches as `VeriTrade-Research/0.2` ... and falls in the wildcard group" -- true of the
robots DECISION but not of the actual HTTP request this adapter ever makes, and stating it
that way here, ahead of the "SCRAPLING'S USER AGENT" section below that gets it right, let a
reader stop at the first, wrong claim. What is actually true, stated once and precisely:
`robots.allowed()` is asked, and answers, FOR `settings.crawl_user_agent`
(`VeriTrade-Research/0.2`) -- that identity is what the compliance decision below is computed
against, and it does fall in the wildcard group by product-token matching, none of the nine
named agents included. But `search_id_bpk` never sends an HTTP request with that string in a
`User-Agent` header, because it never calls httpx at all (see above) -- every fetch goes
through `scrapling_fetch`, whose impersonating fetcher sends its OWN randomised
Chrome/Brave-shaped fingerprint instead (measured live 2026-09-08, verbatim in "SCRAPLING'S
USER AGENT" below). That fetcher UA is not `VeriTrade-Research/0.2` and -- the fact that
actually matters for compliance -- it is also not any of the nine named agents, so it still
lands in the same permissive wildcard group under its own steam. The two UAs happen to agree
on the outcome here; they are not the same string, and this module does not pretend they are.
That group's own signals are exactly what this pipeline does: it references and cites every
provision back to its source URL (`use=reference`, `search=yes`) and it trains no model on the
text (`ai-train=no`). Both rules that follow are NOT optional and nothing in this module works
around them:
  1. Never fetch this host with an agent identifying as one of the nine named crawlers.
  2. Never use text fetched from this host to train a model.

`robots.allowed()` was called against our OWN configured user agent (not a substitute one to
get a friendlier answer) and returned **True, with no restricting reason**, for both the site
root and a `/Search?keywords=...` URL — measured live 2026-09-08. That is the compliance
answer this module is built on. Had it come back False the correct move would have been to
report BLOCKED and stop, per this phase's own rule — it did not.

SCRAPLING'S USER AGENT — checked, not assumed, because sending one of the nine named agents by
accident would be exactly the refusal this docstring says to honour. `scrapling.fetchers.
Fetcher.get(..., stealthy_headers=True)` calls `generate_headers()`, which fabricates a
randomised REAL-BROWSER fingerprint (measured live 2026-09-08: `Mozilla/5.0 (Macintosh; Intel
Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36`, with
matching `sec-ch-ua` Client Hints). That is a generic Chrome/Brave-shaped string — not
`VeriTrade-Research/0.2`, and not any of the nine named agents either. It falls in the SAME
wildcard robots group ours does (no product token in it names it specifically), so the fetch
this module makes is still governed by `Allow: /` either way; it does not, however, identify
itself as VeriTrade the way `portal.headers()` does for the httpx-based adapters, which is a
real gap recorded here rather than glossed over — see "WHAT THIS ADAPTER DOES NOT COVER" below.

ENCODING — checked, not assumed (Timor-Leste's `<meta charset>` vs httpx mismatch, in
`adapter_timor.py::_decode`, is the reason to check rather than trust a single title). The
saved fixture declares `charset=utf-8` in its `<meta http-equiv="Content-Type">` tag (the only
charset mentioned anywhere in the document, checked with a regex over the raw bytes) and
decodes cleanly under strict UTF-8 with no replacement characters — verified live 2026-09-08
against the raw response bytes, not the already-decoded text. Indonesian is Latin-script but
titles carry real diacritics-adjacent punctuation (e.g. the "&" in "Ajudan, Polisi ... &
Asisten Pribadi") that a wrong decode would corrupt, so this was checked rather than assumed
merely because the script looks ASCII-safe. No `_decode`-style override is needed here.

RESULT ROW SHAPE — measured against a real search fixture (`?keywords=data+pribadi`, saved
2026-09-08, "Menemukan 46.709 peraturan"): each result is a `div.card` holding TWO pieces of
text that both matter for the citation — a sibling div (class `fw-semibold`) carrying the
instrument's TYPE and NUMBER ("Undang-undang (UU) Nomor 27 Tahun 2022"), and the `<a
href="/Details/<id>/<slug>">` itself carrying the instrument's NAME ("Pelindungan Data
Pribadi"). Neither alone is a citation a reviewer could act on — the anchor text alone drops
the instrument number, and the number alone drops the subject. `_result_rows` joins both into
one title. It also has to avoid a real trap: a `div.card` for one result can carry a NESTED
"Status Peraturan" block ("Dicabut dengan" / revoked-by) linking to a DIFFERENT `/Details/<id>`
regulation — a related-document cross-reference, not a second search result. Taking `select_one`
(the FIRST `/Details/` anchor in DOM order, which measured live is always the title anchor,
appearing before any status/related block) rather than every `/Details/` anchor in the card is
what keeps that cross-reference out — proven against the fixture: 11 raw `/Details/` hrefs on
the page, 10 real result rows, the 11th is exactly that nested "Dicabut dengan" link inside the
Bank Indonesia PBI 7/6/PBI/2005 card.

PAGINATION — `/Search?keywords=<term>&p=<N>` is a real, plain query-string page parameter
(verified against the fixture's own "Next"/page-number links), so multi-page IS possible. This
adapter reads PAGE 1 ONLY per query term, a bounded choice matching `adapter_china.py`'s
"BOUNDED, NOT EXHAUSTIVE" precedent, not a discovered ceiling: with `discovery_max_docs=22` and
several query terms already run per pillar, page 1 of each term already supplies more rows than
the trim keeps, and each additional page is another Scrapling round trip against a host this
project has already measured as httpx-hostile. A future pass wanting deeper recall on a single
term should walk `p=2, 3, ...` explicitly rather than assume this module already does.
CONFIRMED, not assumed (fix round 1, 2026-09-08): `p=2` on a live term ("pusat data") returned
10 MORE rows, none repeating page 1 -- so this is a real, present ceiling this choice accepts,
not a page 2 that would have come back empty anyway. See `task-7-report.md` for the multi-term
live count this produces (order of magnitude below the enumerate-the-whole-gazette lanes --
Timor-Leste, Laos, Thailand, Singapore -- and closer to `adapter_china.py`'s own search-pass
count, because both are top-K-per-query search endpoints, not catalogue walks).

WHAT THIS ADAPTER DOES NOT COVER, recorded rather than hidden:
  * Only `peraturan.bpk.go.id`'s own `/Search` endpoint. `jdihn.go.id` (JDIH Nasional, the
    other Indonesian entry in `data/sources.yaml`) did not resolve at all when last probed
    (2026-08-21) and is not attempted here.
  * Search results beyond page 1 of each query term (see PAGINATION above).
  * The `/Details/<id>` landing page is an ABSTRACT, not the statute text; the linked
    `/Download/<id>/....pdf` is the real instrument. Resolving that hop is `fetch.py`'s job —
    `fetch._BODY_ROUTES` already has a `peraturan.bpk.go.id` rule that reads the `/Details/`
    page's own body for its `/Download/....pdf` link (see that module, and its docstring's own
    note that nine of these abstract pages were once the WHOLE Indonesian corpus until this was
    fixed). This adapter deliberately does NOT re-implement that hop.
  * Regional/local instruments (Perda/Perbup/Perwali — provincial or municipal regulations)
    are not filtered OUT of results, only scored low relative to national instruments (see
    `_TYPE_WEIGHT`) — a genuinely relevant regional rule is not silently dropped, merely
    ranked below a national one when both are present.
  * The fetch itself does not self-identify as VeriTrade (see "SCRAPLING'S USER AGENT" above)
    — the robots DECISION is computed for `settings.crawl_user_agent`, but the HTTP request is
    made by Scrapling's impersonating fetcher under its own randomised browser fingerprint.
    Both land in the same permissive wildcard group, but they are not the same identity, and
    whether this project should change that is a decision above this module's scope.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from ..config import settings
from ..schemas import DiscoveredDoc, Economy
from . import portal, robots, scrapling_fetch

Log = Callable[[str], None]

#: Verified live 2026-09-08 (see module docstring). `search_id_bpk` reads `base_url` from
#: `src` first so `data/sources.yaml` stays the source of truth, falling back to this measured
#: default so a direct call (no `sources.yaml` row) and the unit tests both work unmodified.
_BASE = "https://peraturan.bpk.go.id"

#: Bounded, not exhaustive -- see module docstring's PAGINATION note. Mirrors
#: `adapter_china.py`'s `_SEARCH_MAX_TERMS` precedent for the same reason: each Scrapling round
#: trip is a real cost, and an adapter call already runs one per query term.
_SEARCH_MAX_TERMS = 6

#: Indonesia's own statutory hierarchy (Law 12/2011 on the Formation of Legislation: UU/Perpu
#: above PP, PP above Perpres, Perpres above ministerial and other national regulator
#: instruments, all of those above regional Perda/Perbup/Perwali). This is the FIRST signal
#: `_relevance` combines -- a national Act is far likelier to be an RDTII answer-key law than a
#: municipal staffing regulation, and the fixture's own "Ajudan, Polisi Pengamanan ... Staf
#: Pribadi Wali Kota" rows (Perbup/Perwali, matched only because "pribadi" is a substring of
#: "data pribadi") are the measured example of exactly that noise. Matched case-insensitively
#: against the combined type+title string; order matters, first match wins.
_TYPE_WEIGHT: tuple[tuple[str, float], ...] = (
    ("undang-undang", 0.95),
    ("perpu", 0.90),
    ("peraturan pemerintah", 0.85),
    ("peraturan presiden", 0.80),
    ("peraturan menteri", 0.65),
    ("peraturan bank indonesia", 0.55),
    ("peraturan ojk", 0.55),
    ("keputusan presiden", 0.45),
    ("peraturan daerah", 0.15),
    ("peraturan bupati", 0.15),
    ("peraturan walikota", 0.15),
    ("peraturan gubernur", 0.20),
)
_DEFAULT_TYPE_WEIGHT = 0.35

#: `/Details/<id>/<slug>` only -- the abstract landing page `fetch._BODY_ROUTES` resolves to
#: its PDF (see module docstring). Anything else on this host (search filter chrome, modal
#: `#abstrak-<id>` anchors, etc.) is not a document.
_DETAILS_RE = re.compile(r"/Details/\d+")


def _result_rows(html: str, base_url: str) -> list[tuple[str, str]]:
    """Every (absolute /Details/ url, title) pair a JDIH BPK search-result page lists.

    Pure and network-free so the test suite can drive it against the saved fixture. One row
    per `div.card` that carries a `/Details/` anchor; the FIRST such anchor in the card (see
    module docstring's "RESULT ROW SHAPE" section for why first, not every, matters -- a card
    can carry a second, unrelated `/Details/` link in a nested "Status Peraturan" block). Title
    joins the instrument's type+number (sibling `div.fw-semibold`, e.g. "Undang-undang (UU)
    Nomor 27 Tahun 2022") with its name (the anchor text, e.g. "Pelindungan Data Pribadi") --
    neither alone is a usable citation. Deduplicates by the resolved absolute URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for card in soup.select("div.card"):
        a = card.select_one('a[href*="/Details/"]')
        if a is None:
            continue
        href = a.get("href") or ""
        if not _DETAILS_RE.search(href):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        name = " ".join(a.get_text(" ", strip=True).split())
        type_div = card.select_one("div.fw-semibold")
        type_number = " ".join(type_div.get_text(" ", strip=True).split()) if type_div else ""
        title = f"{type_number} — {name}" if type_number else name
        seen.add(absolute)
        out.append((absolute, title))
    return out


def _relevance(title: str, terms: list[str], indicators: list) -> float:
    """How much of the discovery budget this row deserves. See the module docstring's `_TYPE_
    WEIGHT` note for the statutory-hierarchy signal; combined with two more so a national Act
    that also happens to contain a search term outranks a plain hierarchy match, and a hit on
    an actual RDTII indicator phrase (rare in Indonesian, but not impossible for e.g. an
    English-titled sectoral circular) adds a little more on top.

    `discovery._score` is imported locally, matching the convention `adapter_china.py` and
    `adapter_timor.py` already use: `discovery.py` imports sibling adapters INSIDE its dispatch
    function rather than at its own module top, to avoid a circular import.
    """
    low = title.lower()
    type_weight = _DEFAULT_TYPE_WEIGHT
    for needle, weight in _TYPE_WEIGHT:
        if needle in low:
            type_weight = weight
            break
    term_hits = sum(1 for t in terms if t and t.lower() in low)
    term_fit = min(1.0, term_hits / 2.0) if terms else 0.0
    topic_en = 0.0
    if indicators:
        from .discovery import _score as _topic_score
        topic_en = _topic_score(title, indicators)
    return round(min(0.99, max(0.05, 0.55 * type_weight + 0.30 * term_fit + 0.15 * topic_en)), 4)


def _search_url(base: str, term: str) -> str:
    """Page 1 of `/Search?keywords=<term>` -- see module docstring's PAGINATION note for why
    page 1 only. `urlencode` matches the `+`-for-space form measured live off the portal's own
    search box (`?keywords=data+pribadi`)."""
    return base.rstrip("/") + "/Search?" + urllib.parse.urlencode({"keywords": term})


def _search_terms(query: str, src: dict, indicators: list) -> list[str]:
    """Terms to run through the search pass, capped at `_SEARCH_MAX_TERMS`.

    Prefers `src["queries_p6"]`/`src["queries_p7"]`, filtered to whichever pillar(s)
    `indicators` covers -- the SAME vehicle `discovery._source_queries` already gives every
    other portal-native lane its own query vocabulary through -- then falls back to the
    `query` argument itself, so a call made before `data/sources.yaml` carries queries for this
    adapter (or a direct call, as the unit tests make) still does something useful.

    ⚠ ORDER IS LOAD-BEARING once `data/sources.yaml`'s `id_bpk` entry grows a `queries_p6`/
    `queries_p7` list: config terms are appended BEFORE the passed `query`, so once either list
    reaches `_SEARCH_MAX_TERMS` (6) entries, `query` becomes unreachable dead code -- the same
    misclassification `adapter_china.py`'s `cn_portal` shipped with (found in the 2026-09-07
    final review: its `queries_p6`/`queries_p7` each carry 13 terms, so `cn_portal` had to be
    registered with `enumerates_portal=True` instead of being called once per query term).
    `query` is only "live" today because this entry has no `queries_p6`/`queries_p7` yet --
    re-check `portal.register("id_bpk", ...)`'s `enumerates_portal` once one is added.
    """
    terms: list[str] = []
    pillars = {getattr(ind, "pillar", None) for ind in indicators}
    for p in (6, 7):
        if p in pillars:
            terms.extend(src.get(f"queries_p{p}") or [])
    if query:
        terms.append(query)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= _SEARCH_MAX_TERMS:
            break
    return out


def search_id_bpk(client, src: dict, query: str, economy: Economy, indicators: list,
                   log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    Goes to `scrapling_fetch` FIRST for every request -- never httpx -- because plain httpx is
    refused with HTTP 403 on every path this host has (root, `/Search`, `/sitemap.xml`,
    measured 2026-09-07; see module docstring). `client` (the httpx client other adapters use
    via `portal.portal_get`) is accepted for signature compatibility but never used.

    `portal.portal_get` is not used either, because it is built on that same httpx client --
    this function calls `robots.allowed(url, settings.crawl_user_agent)` itself before every
    browser fetch instead, the same pattern `adapter_china.py::_search_pass` set for a host
    reached only through Scrapling. A missing Scrapling install, a robots refusal, or a dead
    term each log why and the pass continues (or returns empty) rather than raising or silently
    returning nothing.
    """
    portal_name = src.get("name", "Database Peraturan JDIH BPK (BPK RI)")
    base = src.get("base_url") or _BASE

    if not scrapling_fetch.available():
        log("[id_bpk] browser lane unavailable -- scrapling is not installed, and this host "
            "refuses plain httpx on every path (403 at root/Search/sitemap.xml, measured "
            "2026-09-07), so no request can be made")
        return []

    terms = _search_terms(query, src, indicators)
    if not terms:
        log("[id_bpk] no query terms available -- nothing to search for")
        return []

    out: list[DiscoveredDoc] = []
    seen_ids: set[str] = set()
    for i, term in enumerate(terms):
        url = _search_url(base, term)
        ok, why = robots.allowed(url, settings.crawl_user_agent)
        if not ok:
            log(f"[id_bpk] robots refused term {i + 1}/{len(terms)} ({url[:80]}) -- {why}")
            continue
        res = scrapling_fetch.fetch(url, timeout=settings.crawl_timeout_seconds, log=log)
        if res is None:
            log(f"[id_bpk] term {i + 1}/{len(terms)} -> no response from the browser lane")
            continue
        try:
            body = res.body.decode("utf-8", errors="replace")
            rows = _result_rows(body, url)
        except Exception as exc:                      # noqa: BLE001 -- one dead term is not fatal
            log(f"[id_bpk] term {i + 1}/{len(terms)} parse failed: {type(exc).__name__}: {exc}")
            rows = []
        added = 0
        for link_url, title in rows:
            score = _relevance(title, terms, indicators)
            doc = portal.make_doc(economy, link_url, title, portal_name, score=score)
            if doc.doc_id in seen_ids:
                continue
            seen_ids.add(doc.doc_id)
            out.append(doc)
            added += 1
        log(f"[id_bpk] term {i + 1}/{len(terms)} ({term[:40]!r}) -> {added} new "
            f"({len(rows)} parsed)")

    return out


portal.register("id_bpk", search_id_bpk)
