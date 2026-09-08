"""China — cac.gov.cn's own server-rendered news/policy pages, plus gov.cn's policy aggregator.

Both CN entries in `data/sources.yaml` were `adapter: websearch`, and every search engine now
answers 403 (measured against the pre-existing lane before this adapter existed). This module
gives China its first portal-native lane.

ROUTE, verified live 2026-09-07/08:

    https://www.cac.gov.cn/                                     200, 59,987 bytes (`len(r.text)`),
                                                                  356 links, 82 raw /c_<id>.htm
                                                                  anchors (71 distinct after
                                                                  dedup) — server-rendered, NOT a
                                                                  JS shell.
      article pages   //www.cac.gov.cn/YYYY-MM/DD/c_<id>.htm     protocol-relative (see below)
      section indexes //www.cac.gov.cn/<path>/A<N>index_<N>.htm  do NOT paginate (see below)

    https://www.gov.cn/zhengce/xxgk/                             200, 209,014 bytes, 921 links,
                                                                  921 links, server-rendered. Its
                                                                  /c_<id>.html anchors point OUT to
                                                                  OTHER agencies' own domains
                                                                  (cidca.gov.cn, nea.gov.cn,
                                                                  gjxfj.gov.cn, ...) — it is a
                                                                  policy AGGREGATOR, not a document
                                                                  host itself. Those hrefs are
                                                                  already absolute (0 of 921 were
                                                                  protocol-relative), so no
                                                                  resolution trap here, but every
                                                                  one is a DIFFERENT host from
                                                                  cac.gov.cn and each is fetched
                                                                  and robots-checked independently
                                                                  by `portal.portal_get`, per host,
                                                                  by the downstream fetch stage.

PROTOCOL-RELATIVE HREFS: cac.gov.cn writes `//www.cac.gov.cn/...` — no scheme. Left unresolved
these are not fetchable URLs (`httpx.get("//www.cac.gov.cn/...")` is not a request any client can
make), and the economy would silently discover nothing off the front page. `_article_links`
resolves every href through `urllib.parse.urljoin(base_url, href)`, which turns `//host/path`
into `https://host/path` when `base_url` itself is `https://...` (verified: the two obviously
differ, `urljoin` is exercised directly by `test_protocol_relative_hrefs_are_resolved`, not just
implied by not crashing).

DO PAGE-2 SECTION INDEXES EXIST? NO — measured live 2026-09-08 against four real section
indexes discovered by walking the front page's own nav (not the placeholder `A0901index_N`
from the brief's recon script, which is not one of this portal's real sections and 404s at
n=1 too):

    https://www.cac.gov.cn/wxzw/zcfg/A093703index_1.htm            (政策法规 / policy & regs)
    https://www.cac.gov.cn/wxzw/sjzl/sjcjaqpg/A09370801index_1.htm (数据出境安全评估 / cross-
                                                                      border data-export security
                                                                      assessment — P6 core)
    https://www.cac.gov.cn/wxzw/wlaq/A093705index_1.htm            (网络安全 / cybersecurity —
                                                                      P7-I2 core)
    https://www.cac.gov.cn/wxzw/sjzl/A093708index_1.htm            (数据治理 / data governance)

Every one of the four answered `_1` with a real article list (10-20 rows each) and `_2` with a
bare HTTP 404 (one `sjcjaqpg` attempt returned no response at all rather than a clean 404, which
reads as the same "there is no page 2" rather than a portal that is merely slow — a genuinely
slow portal would have succeeded on `portal_get`'s retry, and a repeat probe of the same URL
came back 404 immediately). **So this lane reads the FRONT PAGE of each section only** — that is
a real coverage limit, not a defect papered over: whatever a section publishes past its first
10-20 rows is invisible to this adapter. `_SECTIONS` below lists exactly these four; nothing
here attempts `_2`, `_3`, ... because there is nothing there to attempt.

WHAT THIS ADAPTER DOES NOT COVER, recorded rather than hidden:
  * cac.gov.cn carries roughly 70 OTHER section indexes reachable from its own front page nav
    (leadership bios, photo galleries, regional bureaus, thematic campaign pages...) — see the
    front-page recon dump used to pick `_SECTIONS`. Only the four on-topic ones above are walked.
    A future pass that wants deeper coverage should widen `_SECTIONS`, not silently assume the
    four here are exhaustive.
  * Each section page is read ONCE at its front (page 1) — see the pagination finding above.
  * `flk.npc.gov.cn` is NOT a lane and never will be through this module. Its own API's
    permission block answers with a "download" field set to zero, which is the operator stating
    plainly that the documents are not to be downloaded — this project honours that rather than
    finding a way around it. (Naming the host here, in a docstring, is not the same thing as
    building a fetchable string that points at it — `test_the_npc_database_is_not_a_fetch_target`
    is what pins the difference.)

CORRECTION (2026-09-08 fix round 1): an earlier version of this docstring said "there is no
search endpoint on either host that this adapter uses" / "neither host exposes a search
endpoint this adapter can call". That was false, and it was false on evidence sitting in the
fixture this module's own tests read: `tests/fixtures/portals/cn_cac_index.html` carries a
keyword-search form (`<form id="zlb" ... action="//search.cac.gov.cn/cms/cmsadmin/infopub/
gjjs.jsp">`) and a 高级检索 ("advanced search") link in its header, and neither had been probed
before that claim was written. See "FULL-TEXT SEARCH" below for what was actually found once it
was. The gap this adapter has is not "no search exists on this portal" — it is "recency-sorted
feeds and a WAF-gated search endpoint, between them, do not surface a promulgation-era statute
without either full-text search or many pages of un-paginated recency"; the search pass below
closes most of that gap where the browser lane is available, and is honest about the rest where
it is not.

GOV.CN/ZHENGCE/XXGK/ PAGINATION (Finding 2, checked 2026-09-08): this page is a client-rendered
listing widget (script `.../trs_zfxx_20190820policyLibrarySearchResultPage.js`, markup carrying
`class="k-pagination-dot"` and inline JS testing `this.currentPage`/`this.totalPage`) backed by
an AJAX call this module does not reverse-engineer. It is NOT the simple `?page=N` shape
`cac.gov.cn`'s search endpoint turned out to have. The `javascript:;` year links visible in the
DOM (2019年..2025年) are client-side filter triggers for that same AJAX call, not fetchable
URLs; the few `year=2021`/`year=2023` query strings that DO appear on the page belong to OTHER
agencies' own sites (`nfra.gov.cn`, `safe.gov.cn`) reached through this page's cross-domain
aggregator links, not to gov.cn's own archive. So: **no**, this page does not paginate in a way
this adapter can walk without running its JS, and it offers no plain year-archive URL either.
`gov_aggregator` stays a front-page-only pass, same as before — recorded here as a checked
"no", not an unchecked one.

WHY `portal_strategies.paginated_index` IS NOT USED (Finding 3) even though it is named in this
task's own Interfaces block, following the precedent `adapter_laos.py` set for saying so rather
than leaving the question open: that helper reads the row's href AND its title off the SAME
anchor (`a.get("href")`, `a.get_text()`) and filters only on the href via `link_filter`. Every
page this adapter reads needs MORE than that from one anchor — the protocol-relative resolution,
the `/c_<id>.htm`-only filter, and the 答记者问 title-level noise drop all have to happen
together, in one pass, for the section walk, the front page AND the search-pass results to
agree on what a "row" is. `_article_links` is that one pass. Reusing `paginated_index` for the
sections would have meant a second, divergent extraction path with no title-noise filtering, for
a payoff that stopped applying once Step 1 measured `_2` as a 404 on every real section — there
is nothing here to paginate INTO.

ENCODING — checked, not assumed (Timor-Leste's `<meta charset>` vs httpx mismatch, in
`adapter_timor.py::_decode`, is the reason to check rather than trust). Both hosts declare UTF-8
in their `<meta http-equiv="Content-Type" ... charset=...>` tag, and httpx's own encoding guess
(`resp.encoding`) independently landed on `utf-8` for both when probed live 2026-09-08. They
AGREE, so there is no silent mis-decode here and no `_decode`-style override is needed — `resp.text`
is trusted as-is. (Verified against the raw response bytes, not the already-decoded `.text`, so a
disagreement would have shown up.)

答记者问 NOISE: cac.gov.cn mixes press-Q&A pages about its own measures into these same article
listings — they fetch and would otherwise split into a single undifferentiated block. A
title-level filter is obvious here (measured live: 2 of 71 front-page rows, 1 of 10 on the
data-export-security section, 1 of 20 on the cybersecurity section, 3 of 19 on the data-
governance section carried "答记者问" literally in the anchor text) so `_article_links` drops any
row whose title contains it, rather than leaving it for the LLM grader to reject at a dollar
cost per call.

ROBOTS.TXT — cac.gov.cn's own robots.txt (`Disallow: /zfz/ /wxb_zfz/ /wxzf/
/vmsfile/newVideo.html?vid=*`) does not touch any path this adapter reads, so every URL here is
robots-ALLOWED whenever the robots.txt fetch itself succeeds. The fetch itself is intermittently
flaky FROM THIS NETWORK — six back-to-back attempts (2026-09-08) split 3 succeeded / 3 raised
`httpcore.ConnectTimeout` on the TLS handshake — which is the same fact already on record in
`CLAUDE.md` ("cac.gov.cn ... TLS-times-out from some networks"). No `robots.UNREACHABLE_OVERRIDE`
entry is added here: unlike the MY/India/RBI entries in that table, this is not a server
returning a 4xx/5xx that PERSISTS — it is connection-level flakiness that a retried request
generally clears (observed: a stalled handshake was followed by a fast, cached-connection
success), and `robots.py`'s per-host cache means only the FIRST check in a given hour is at
risk. Recorded here so the next person who sees a CN run come back emptier than expected checks
this before assuming the adapter itself is broken.

FULL-TEXT SEARCH (added 2026-09-08, fix round 1): `search.cac.gov.cn/cms/cmsadmin/infopub/
gjjs.jsp` is a real keyword search over the whole `cac.gov.cn` corpus, found in the front-page
fixture's own header form (see the CORRECTION note above). It answers `?huopro=<query>&
templetid=1563339473064626&pubtype=S&pubpath=portal&webappcode=A09&searchdir=A09&sort=<0|1>
&page=<N>` with a paginated HTML result list in the SAME `/c_<id>.htm` shape `_article_links`
already parses. The host is `search.` — DNS resolves it to `*.vip.jiasule.org`, i.e. it sits
behind the Jiasule anti-bot CDN, confirmed live 2026-09-08: plain httpx/curl cannot even
complete the TLS handshake most attempts (`ConnectTimeout` on 3 of 3 raw attempts), and on the
one attempt that did connect, the JSP path answered a 403 Jiasule challenge page while the same
client's earlier request to the bare `https://search.cac.gov.cn/` (no query string) 301-redirected
straight to `www.cac.gov.cn` — i.e. only the actual search PATH is gated, not the whole host.

Cleared through `backend/pipeline/scrapling_fetch.py`'s impersonating Fetcher (curl_cffi,
`stealthy_headers=True`) — the same tool this project already documents as the answer to a
TLS/WAF-fingerprint block (see that module's own docstring; ID's portal in this same phase is
refused by httpx on every path and answers Scrapling 200). Measured live 2026-09-08, querying
the exact statute names with `sort=0` (relevance — see below for why not the form's own default
`sort=1`):

    "中华人民共和国个人信息保护法" (PIPL)  -> rank #1: cac.gov.cn/2021-08/20/c_1631050028355286.htm
                                              titled "中华人民共和国个人信息保护法" verbatim
    "中华人民共和国数据安全法" (DSL)       -> rank #1: cac.gov.cn/2021-06/11/c_1624994566919140.htm
                                              titled "中华人民共和国数据安全法" verbatim
    "中华人民共和国网络安全法" (CSL)       -> found (2016 original + a 2025-12-29 amended
                                              republication), on retry — the first attempt hit
                                              the same network-level flakiness `cac.gov.cn`
                                              already carries (both the Fetcher AND the
                                              StealthyFetcher escalation timed out before either
                                              reached the WAF; a bare retry of the same URL
                                              cleared it)

`sort=0` (relevance), not the form's own hidden default `sort=1` (date-descending), is the
choice that makes this work WITHOUT hardcoding a promulgation date: the form also exposes
`startDate`/`endDate`, and an earlier probe confirmed a date-window on PIPL's real 2021-08/09
promulgation month does surface it too — but shipping a per-statute date range in code would be
exactly the "hardcode a law's answer" this project's own rules forbid. `sort=0` with the plain
query text needs no such knowledge and is what `_search_url` uses; a query for "个人信息保护法"
on page 1 with the DEFAULT `sort=1` returns only 2026 news (495 total results, date-sorted, the
statute itself many pages back), which is the failure mode that made the original "no search
endpoint" docstring claim look superficially true if the endpoint were only tried the naive way.

BOUNDED, NOT EXHAUSTIVE: `_search_pass` runs at most `_SEARCH_MAX_TERMS` (6) query terms, page 1
only (~20 results each), per call. This is a deliberate cap, not a discovered limit of the
endpoint (page 25 of an unfiltered "个人信息保护法" query was reached live, 495 results total —
the endpoint itself paginates fine). The cap exists because each Scrapling round trip against
this specific WAF was observed taking anywhere from ~15s to several retried minutes, and an
adapter call already does a 6-page front/section walk before this pass starts. `_search_terms`
prefers `src["queries_p6"]`/`src["queries_p7"]` (filtered to whichever pillar(s) `indicators`
covers) — the SAME vehicle `discovery._source_queries` already gives every other lane its own
query vocabulary through — and falls back to one native Chinese phrase per indicator from
`query_terms_i18n.NATIVE_QUERY_TERMS["zh"]` when `src` carries no queries yet (e.g. before
`data/sources.yaml` is wired to `cn_portal`), so the pass is not dead code waiting on that
wiring. If `scrapling_fetch.available()` is False, or `search.cac.gov.cn`'s own robots.txt is
unreadable/disallowing, the pass logs why and returns nothing — it never raises, and the
front/section pass above still runs regardless.

RELEVANCE SCORING — every document used to default to `relevance_score=1.0` in an adapter this
shape (see `adapter_timor.py`'s own note on what that does to `discovery._cap`'s trim to
`discovery_max_docs`); `_relevance` here combines three signals instead: which of the four
on-topic sections (or the generic front page / gov.cn aggregator) the row came from, how many of
the CN indicator vocabulary's own Chinese phrases (`backend/rdtii/query_terms_i18n.py`,
`NATIVE_QUERY_TERMS["zh"]` — PIPL/CSL articles quoted verbatim, not guessed) appear in the title,
and — for the rare English-titled row — `discovery._score` against the English `query_terms`.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from ..rdtii.query_terms_i18n import NATIVE_QUERY_TERMS
from ..schemas import DiscoveredDoc, Economy
from . import portal, robots, scrapling_fetch

Log = Callable[[str], None]

#: The two hosts, verified live 2026-09-07/08 (see module docstring). `search_cn_portals` reads
#: these from `src` first (so `data/sources.yaml` can hold the two hosts, per the brief), and
#: falls back to these measured defaults so the unit tests and a direct call (no `sources.yaml`
#: row) both work unmodified.
_CAC_BASE = "https://www.cac.gov.cn/"
_GOV_BASE = "https://www.gov.cn/zhengce/xxgk/"

#: The four on-topic section indexes found by walking the cac.gov.cn front page's own nav (see
#: module docstring for why these four and not the ~70 others the site also links). Confirmed
#: NOT to paginate: `_2` on every one of these 404s or gets no response at all. `label` feeds
#: `_SECTION_WEIGHT` in `_relevance`.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("https://www.cac.gov.cn/wxzw/zcfg/A093703index_1.htm", "policy_regulations"),
    ("https://www.cac.gov.cn/wxzw/sjzl/sjcjaqpg/A09370801index_1.htm", "data_export_security"),
    ("https://www.cac.gov.cn/wxzw/wlaq/A093705index_1.htm", "cybersecurity"),
    ("https://www.cac.gov.cn/wxzw/sjzl/A093708index_1.htm", "data_governance"),
)

#: Base relevance by which page a row came from — the first of `_relevance`'s signals. The two
#: on-topic sections that map straight onto a pillar (data-export-security -> P6, cybersecurity
#: -> P7-I2) sit highest; the front page and gov.cn's cross-domain aggregator are the lowest
#: because they are general news/policy feeds, not a filtered index. A "search" hit sits above
#: those two: it is a DIRECTED match on a query term, not incidental recency, even before
#: `_relevance`'s own topic-fit bonus is added on top.
_SECTION_WEIGHT: dict[str, float] = {
    "data_export_security": 0.75,
    "cybersecurity": 0.72,
    "search": 0.68,
    "data_governance": 0.65,
    "policy_regulations": 0.60,
    "front": 0.40,
    "gov_aggregator": 0.35,
}

#: The keyword-search endpoint found in the fixture's own header form (see module docstring's
#: "FULL-TEXT SEARCH" section). `_SEARCH_TEMPLATE_ID` etc. are the form's own hidden field
#: values, read verbatim off `tests/fixtures/portals/cn_cac_index.html`, not guessed.
_SEARCH_ENDPOINT = "https://search.cac.gov.cn/cms/cmsadmin/infopub/gjjs.jsp"
_SEARCH_TEMPLATE_ID = "1563339473064626"
_SEARCH_WEBAPPCODE = "A09"
_SEARCH_DIR = "A09"
#: Bounded, not exhaustive — see module docstring's "BOUNDED, NOT EXHAUSTIVE" paragraph for why
#: this number and not "walk every page the endpoint offers" (which live testing found goes to
#: 25 pages / 495 results for one broad query alone).
_SEARCH_MAX_TERMS = 6

#: cac.gov.cn also carries 答记者问 (press Q&A) pages about its own measures alongside the real
#: instruments in the same listings — see the module docstring's "答记者问 NOISE" section for the
#: measured drop rate. `_article_links` drops any row whose anchor text contains this literally.
_NOISE_TITLE_MARKERS: tuple[str, ...] = ("答记者问",)

#: Article pages only — `/YYYY-MM/DD/c_<id>.htm(l)`, on ANY host (gov.cn's aggregator links out
#: to other agencies' domains under the same `/c_<id>.html` shape). Section index pages
#: (`A<N>index_<N>.htm`) never match this, so nothing extra is needed to keep them out.
_ARTICLE_RE = re.compile(r"/c_\d+\.html?$", re.I)

#: Every Chinese phrase the indicator vocabulary carries for this economy (`query_terms_i18n.py`,
#: PROVENANCE section: quoted from PIPL/CSL articles, not guessed), flattened once at import time
#: rather than per title. Used by `_relevance` as the topic-fit signal — a title carrying
#: "数据出境安全评估" is doing real work an English-only `discovery._score` could never see, the
#: same gap `query_terms_i18n.py` exists to close for BM25.
_ZH_TERMS: tuple[str, ...] = tuple(
    sorted({t for terms in NATIVE_QUERY_TERMS.get("zh", {}).values() for t in terms}))


def _article_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Every (absolute article url, title) pair a cac.gov.cn or gov.cn page lists.

    Pure and network-free so the test suite can drive it against the saved fixture. Resolves
    protocol-relative (`//host/path`) and relative hrefs through `urljoin` against `base_url` —
    see the module docstring's "PROTOCOL-RELATIVE HREFS" section for why that step is not
    optional here. Keeps only `/c_<id>.htm(l)` article pages, drops `答记者问` noise rows (see
    `_NOISE_TITLE_MARKERS`), and deduplicates by the resolved absolute URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not href or not _ARTICLE_RE.search(href):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        # The search-result row shape (not the plain listing pages) prefixes every title with a
        # decorative "» " bullet in its own text node -- measured live 2026-09-08: 0/69 front-page
        # rows carry it, 20/20 search-result rows do. Pure UI noise, stripped rather than kept as
        # a leading character nobody asked to match on.
        title = title.lstrip("»").strip()
        if any(marker in title for marker in _NOISE_TITLE_MARKERS):
            continue
        seen.add(absolute)
        out.append((absolute, title))
    return out


def _relevance(section: str, title: str, indicators: list) -> float:
    """How much of the discovery budget this row deserves. See the module docstring's
    "RELEVANCE SCORING" section for the reasoning; this is the mechanics.

    `discovery._score` is imported locally, matching the convention `adapter_timor.py` already
    uses: `discovery.py` imports sibling adapters INSIDE its dispatch function rather than at its
    own module top, to avoid a circular import.
    """
    base = _SECTION_WEIGHT.get(section, 0.35)
    hits = sum(1 for t in _ZH_TERMS if t in title)
    topic_zh = min(1.0, hits / 2.0) if _ZH_TERMS else 0.0
    topic_en = 0.0
    if indicators:
        from .discovery import _score as _topic_score
        topic_en = _topic_score(title, indicators)
    return round(min(0.99, max(0.05, base + 0.35 * topic_zh + 0.10 * topic_en)), 4)


def _search_url(term: str, page: int = 1) -> str:
    """Build a `sort=0` (relevance) search URL. See the module docstring's "FULL-TEXT SEARCH"
    section for why relevance and not the form's own default `sort=1` (date)."""
    params = {
        "templetid": _SEARCH_TEMPLATE_ID, "pubtype": "S", "pubpath": "portal",
        "page": str(page), "webappcode": _SEARCH_WEBAPPCODE, "huopro": term,
        "mustpro": "", "notpro": "", "inpro": "", "startDate": "", "endDate": "",
        "sort": "0", "searchfield": "", "searchdir": _SEARCH_DIR,
    }
    return _SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def _search_terms(query: str, src: dict, indicators: list) -> list[str]:
    """Terms to run through the search pass, capped at `_SEARCH_MAX_TERMS`.

    Prefers `src["queries_p6"]`/`src["queries_p7"]`, filtered to whichever pillar(s)
    `indicators` belongs to, then the `query` argument itself, then — only if neither gave
    anything — one native Chinese phrase per indicator from `NATIVE_QUERY_TERMS["zh"]`, so the
    pass still does something useful when called before `data/sources.yaml` carries queries for
    this adapter. See the module docstring's "BOUNDED, NOT EXHAUSTIVE" paragraph for the cap.
    """
    terms: list[str] = []
    pillars = {getattr(ind, "pillar", None) for ind in indicators}
    for p in (6, 7):
        if p in pillars:
            terms.extend(src.get(f"queries_p{p}") or [])
    if query:
        terms.append(query)
    if not terms and indicators:
        zh = NATIVE_QUERY_TERMS.get("zh", {})
        for ind in indicators:
            ind_terms = zh.get(getattr(ind, "indicator_id", ""), [])
            if ind_terms:
                terms.append(ind_terms[0])
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= _SEARCH_MAX_TERMS:
            break
    return out


def _search_pass(terms: list[str], portal_name: str, economy: Economy, seen_ids: set[str],
                  indicators: list, log: Log) -> list[DiscoveredDoc]:
    """Full-text search via `search.cac.gov.cn`, cleared through the Scrapling browser lane.

    See the module docstring's "FULL-TEXT SEARCH" section: plain httpx/curl cannot reliably
    reach this host (TLS handshake failures, and a Jiasule anti-bot 403 on the query path when
    it does connect); `scrapling_fetch.fetch` is what got through in live testing. Robots is
    checked explicitly here (via `robots.allowed`, not `portal.portal_get`) because this fetch
    does not go through `portal.portal_get`'s httpx client at all — Scrapling is a different
    transport, so the one place robots gets enforced for this host has to be this function.
    Never raises: a missing Scrapling install, a robots refusal, or a dead term each log why and
    the pass continues (or returns empty) rather than taking the whole call down with it.
    """
    if not terms:
        return []
    if not scrapling_fetch.available():
        log("[cn_portal] search pass skipped -- Scrapling not installed")
        return []
    ok, why = robots.allowed(_SEARCH_ENDPOINT)
    if not ok:
        log(f"[cn_portal] search pass skipped -- robots: {why}")
        return []

    out: list[DiscoveredDoc] = []
    for i, term in enumerate(terms):
        url = _search_url(term)
        res = scrapling_fetch.fetch(url, timeout=45, browser=True, log=log)
        if res is None:
            log(f"[cn_portal] search pass: term {i + 1}/{len(terms)} -> no response")
            continue
        try:
            body = res.body.decode("utf-8", errors="replace")
            rows = _article_links(body, url)
        except Exception as exc:                      # noqa: BLE001 -- one dead term is not fatal
            log(f"[cn_portal] search pass: term {i + 1}/{len(terms)} parse failed: "
                f"{type(exc).__name__}: {exc}")
            rows = []
        added = 0
        for link_url, title in rows:
            score = _relevance("search", title, indicators)
            doc = portal.make_doc(economy, link_url, title, portal_name, score=score)
            if doc.doc_id in seen_ids:
                continue
            seen_ids.add(doc.doc_id)
            out.append(doc)
            added += 1
        log(f"[cn_portal] search pass: term {i + 1}/{len(terms)} -> {added} new "
            f"({len(rows)} parsed)")
    return out


def search_cn_portals(client, src: dict, query: str, economy: Economy, indicators: list,
                       log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    Two passes. First, the front page + `_SECTIONS` + the gov.cn aggregator, all read through
    `portal.portal_get` (plain httpx; these pages are not WAF-gated). Second, a full-text search
    pass over `_search_terms(query, src, indicators)` via `search.cac.gov.cn`, WHICH IS WAF-gated
    — see `_search_pass` and the module docstring's "FULL-TEXT SEARCH" section for why this
    needs the Scrapling browser lane rather than `portal.portal_get`, and why an earlier version
    of this function's docstring claiming no search endpoint existed was wrong. `indicators` is
    used by both passes, via `_relevance`.

    Reads its two base URLs from `src` (`base_url` for cac.gov.cn, `gov_base` for the gov.cn
    aggregator) so `data/sources.yaml` can hold them, falling back to the measured `_CAC_BASE` /
    `_GOV_BASE` when `src` does not carry them (e.g. a direct call, or the unit test's
    `src={"name": ...}`). Pass `gov_base=""` in `src` to skip the aggregator page entirely.
    """
    portal_name = src.get("name", "Cyberspace Administration of China")
    cac_base = src.get("base_url") or _CAC_BASE
    gov_base = src.get("gov_base", _GOV_BASE)

    pages: list[tuple[str, str]] = [(cac_base, "front")]
    pages.extend(_SECTIONS)
    if gov_base:
        pages.append((gov_base, "gov_aggregator"))

    out: list[DiscoveredDoc] = []
    seen_ids: set[str] = set()
    for url, label in pages:
        resp = portal.portal_get(client, url, log)
        if resp is None:
            log(f"[cn_portal] no response for {label} ({url[:70]})")
            continue
        try:
            rows = _article_links(resp.text, url)
        except Exception as exc:                      # noqa: BLE001 -- one dead page is not fatal
            log(f"[cn_portal] could not parse {label} ({url[:70]}): {type(exc).__name__}: {exc}")
            rows = []
        added = 0
        for link_url, title in rows:
            score = _relevance(label, title, indicators)
            doc = portal.make_doc(economy, link_url, title, portal_name, score=score)
            if doc.doc_id in seen_ids:
                continue
            seen_ids.add(doc.doc_id)
            out.append(doc)
            added += 1
        log(f"[cn_portal] {label}: {url[:70]} -> {added} new ({len(rows)} parsed)")

    terms = _search_terms(query, src, indicators)
    if terms:
        out.extend(_search_pass(terms, portal_name, economy, seen_ids, indicators, log))
    else:
        log("[cn_portal] search pass: no query terms available")

    return out


# enumerates_portal=True: the front/section/aggregator walk is query-independent by
# construction, and the shipped `data/sources.yaml` entry's queries_p6/queries_p7 (13 terms
# each) already exhaust `_search_terms`'s `_SEARCH_MAX_TERMS` (6) cap before the per-call
# `query` argument is ever appended -- so under the shipped config `query` cannot reach the
# search pass at all. Registering this without `enumerates_portal=True` made
# `discover_live` call it once per query term (13x for one pillar), repeating the identical
# httpx walk and the identical six WAF-gated Scrapling searches against search.cac.gov.cn each
# time: 78 WAF crossings for a single pillar, against a portal already documented as flaky and
# WAF-gated. Found in the 2026-09-07 final review. See
# `tests/test_portal_enumeration_dispatch.py`.
portal.register("cn_portal", search_cn_portals, enumerates_portal=True)
