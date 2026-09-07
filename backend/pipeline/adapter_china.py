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
  * Every page here is read ONCE at its front (page 1). There is no search endpoint on either
    host that this adapter uses — `query` is accepted (to match `PortalEnumerator`) but ignored,
    the same choice `adapter_timor.py` and `adapter_mongolia.py` made for portals with no search
    of their own.
  * `flk.npc.gov.cn` is NOT a lane and never will be through this module. Its own API's
    permission block answers with a "download" field set to zero, which is the operator stating
    plainly that the documents are not to be downloaded — this project honours that rather than
    finding a way around it. (Naming the host here, in a docstring, is not the same thing as
    building a fetchable string that points at it — `test_the_npc_database_is_not_a_fetch_target`
    is what pins the difference.)

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
from . import portal

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
#: because they are general news/policy feeds, not a filtered index.
_SECTION_WEIGHT: dict[str, float] = {
    "data_export_security": 0.75,
    "cybersecurity": 0.72,
    "data_governance": 0.65,
    "policy_regulations": 0.60,
    "front": 0.40,
    "gov_aggregator": 0.35,
}

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


def search_cn_portals(client, src: dict, query: str, economy: Economy, indicators: list,
                       log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    `query` is deliberately unused — neither host exposes a search endpoint this adapter can
    call (see the module docstring), so, like `adapter_timor.search_tl_gazette` and
    `adapter_mongolia._search_mn_legalinfo`, this walks every page it knows about regardless of
    the query text it was called with. `indicators` IS used, via `_relevance`.

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

    return out


portal.register("cn_portal", search_cn_portals)
