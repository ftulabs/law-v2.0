"""Singapore Statutes Online — the sort-window union, moved into the pipeline.

SG is mandatory in every round of this hackathon. Until this adapter its only discovery lane
was `adapter: websearch`, and by 2026-09-07 every search engine answered that lane with HTTP
403; with the Phase-1 search-cache TTL now correctly refusing an eight-day-old cache, live SG
runs were producing ZERO documents.

THE TECHNIQUE IS INHERITED, NOT INVENTED. `backend/corpus/catalogue.enumerate_sg` has walked
SSO's browse index by sort-window union since August, because SSO **ignores `CurrentPage`**
(verified 2026-08-01: pages 1, 2 and 3 of `/Browse/Act/Current/All` return byte-identical HTML
at every `PageSize`, with or without the AJAX header). What SSO DOES honour is the sort: asking
for the same list ASC then DESC returns the first and last `PageSize` rows, and their union is
the whole index whenever `total <= 2 x PageSize`. Two sort keys (Title, Number) x two directions
= four windows.

RE-MEASURED LIVE 2026-09-07 (the brief requires this be re-measured, not inherited):

    Title/ASC:  200  len=1,844,269  rows=500  new=500  total_reported=524
    Title/DESC: 200  len=1,844,062  rows=500  new=24   total_reported=524
    Number/ASC: 200  len=1,843,307  rows=500  new=0    total_reported=524
    Number/DESC:200  len=1,844,043  rows=500  new=0    total_reported=524
    union: 524  ->  524/524, COMPLETE against SSO's own reported total.

SSO'S THROTTLE IS SEVERE ENOUGH TO BLOCK A FULL RUN, NOT JUST SLOW ONE DOWN — found the same
day, later in the same session that produced the clean recon above. SSO answers a burst with
`202` and an EMPTY body, never `429` (this is why `portal.portal_get` treats that specific
shape as a throttle rather than a result). After the recon above plus this module's own
development/testing traffic against the same host, EVERY subsequent request — `enumerate_sso`,
a direct `search_sg_sso` call, and the corpus CLI — received `202` with an empty body on every
one of the four windows, confirmed live 2026-09-08 02:04-02:16 (repeated probes, a dedicated
4-minute cooldown wait, and `portal_get`'s own exponential backoff all failed to recover a
single `200` in that window). A JUDGED LIVE RUN MUST BUDGET FOR THIS: unlike the four-window
union above (a genuine, freshly re-measured fact), the number of documents `search_sg_sso`
actually returns end-to-end is UNVERIFIED in this session — it returned 0 while throttled, which
is the correct behaviour for a blocked run (nothing is silently fabricated), not evidence the
adapter is broken. Whether the throttle is IP-based, request-volume-based, or time-based was
not established; re-attempt after a longer cooldown or from a different network before treating
a repeat 0-document run as a regression.

THE DEPENDENCY IS REVERSED, NOT RELAXED. `tests/test_pipeline_isolation.py` forbids the live
pipeline importing `backend.corpus` — correctly, because that rule stops a pre-built corpus
being served as though it were discovered live. But an enumerator is live HTTP, not a stored
corpus, so the enumeration lives HERE and `backend/corpus/catalogue.py` imports it from this
module (`enumerate_sg` there is now a thin wrapper around `enumerate_sso` below, adding the
corpus-only `law_id` key). The isolation test passes unchanged because the pipeline still
imports nothing from `backend.corpus`.

TWO ID SCHEMES STAY DIFFERENT ON PURPOSE. The corpus row's `law_id` comes from
`backend.corpus.store.law_id` (`sha1("{economy}|{url}")[:14]`, prefixed `sg-`) — that call
stays in `catalogue.enumerate_sg`, not here. `search_sg_sso` below builds `DiscoveredDoc`s with
`portal.doc_id` (`sha1(url)[:10]`, prefixed `SG-`) via `portal.make_doc`. A corpus row and a
discovered document are different things; `enumerate_sso` returns the corpus-shaped dict
WITHOUT a `law_id` key so `catalogue.py` is free to add its own.

HONESTY REQUIREMENT: the four windows cover SSO's ~524 current Acts but NOT its ~5,843
subsidiary instruments (Subsidiary Legislation / Acts-Supp) — a `PageSize=500` window can only
union-cover an index whose total is <= 1,000; SSO's `SL`/`Acts-Supp` kinds are not. That
shortfall is reported in the log every run (see `enumerate_sso`'s "INCOMPLETE" line), recorded
in `data/sources.yaml`, and this adapter — like `catalogue.enumerate_sg` before it — makes no
attempt to enumerate those kinds by default. Widening it is future work, not silently assumed
coverage.

ENCODING, CHECKED (per the Timor-Leste lesson: TL declared windows-1252 while httpx defaulted
to UTF-8 and silently mangled every Portuguese title). SSO declares UTF-8 in BOTH places —
the HTTP response header (`Content-Type: text/html; charset=utf-8`) and the page's own
`<meta charset="utf-8" />` — and httpx's own default is UTF-8, so there is no decoding trap
here (checked live against the saved fixture 2026-09-07, not assumed). What SSO DOES do is
write HTML entities into some titles (`&amp;`, `&#39;` — e.g. nav text reads "What&#39;s New";
Act titles such as "Companies (Amendment & Consequential Provisions) Act" have shipped with
`&amp;` in the past). `_browse_rows` always runs `html.unescape` on the parsed title, whether
or not the saved fixture window happens to contain an escaped one, because a Law Name column
reading "...Amendment &amp; Consequential..." is a wrong citation, not a cosmetic bug.

RELEVANCE SCORING: `discovery._cap` trims to `settings.discovery_max_docs` (22 by default) by
sorting on `relevance_score`. A flat score (the portal-native `portal.make_doc` default of 1.0
for every hit) would make the surviving 22-of-524 Acts arbitrary — for a MANDATORY economy,
that is the worst place to be arbitrary. At discovery time this adapter has only the Act's
TITLE (the body has not been fetched yet), so `_relevance` combines a small "this is a current
Act, not merely a subsidiary instrument" base weight with `discovery._score` run against the
title and the caller's `indicators` — the same signal `adapter_timor.py`/`adapter_laos.py` use
for their topic component, imported locally to avoid the circular import `discovery.py` already
routes around by importing its sibling adapters inside its own dispatch function rather than at
module top.
"""
from __future__ import annotations

import html as _html
import re
import time
from typing import Callable

from ..config import settings
from ..console import safe_log
from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

SG_BASE = "https://sso.agc.gov.sg"

#: Result rows in the /Browse listing: <a class="non-ajax" href="/Act/PDPA2012">Title</a>.
#: `non-ajax` is what separates a real result link from the nav pills and action menus that
#: also litter this page (confirmed against the saved fixture: none of the nav anchors carry
#: this class).
_ROW_RE = re.compile(
    r'<a\s+class="non-ajax"\s+href="(/(?:Act|SL|Acts-Supp)/[^"]+)"[^>]*>\s*([^<]{3,300}?)\s*</a>',
    re.I,
)
_COUNT_RE = re.compile(r'(\d[\d,]*)\s+results in\s+(\d+)\s+pages', re.I)

#: SSO IGNORES `CurrentPage` (verified 2026-08-01, re-measured 2026-09-07 — see module
#: docstring) but honours the sort, so the same list ASC then DESC gives the first and last
#: `PageSize` rows. Two sort keys x two directions = four windows; their union covers the
#: index completely whenever total <= 2 x PageSize (524 current Acts, comfortably under
#: 2 x 500 = 1,000). It does NOT cover the 5,843 subsidiary instruments — see module docstring.
_SG_SORTS: tuple[tuple[str, str], ...] = (
    ("Title", "ASC"), ("Title", "DESC"), ("Number", "ASC"), ("Number", "DESC"),
)

#: Base relevance by SSO "kind" — the first of `_relevance`'s two signals. Only "Act" is
#: enumerated by default (see module docstring's honesty note), so in practice every document
#: this adapter emits today carries the "act" weight; "subsidiary" is kept for the day a
#: caller passes `kinds=("Act", "SL")` explicitly.
_KIND_WEIGHT: dict[str, float] = {"act": 0.60, "subsidiary": 0.45}


def _clean_title(title: str) -> str:
    """HTML-entity-unescape and whitespace-normalise one row title.

    Always applied, not conditionally — see module docstring's encoding note. A Law Name
    column reading "Companies (Amendment &amp; Consequential) Act" is a wrong citation, not a
    cosmetic bug, whether or not the CURRENT fixture window happens to contain an escaped one.
    """
    return re.sub(r"\s+", " ", _html.unescape(title)).strip()


def _browse_rows(html: str) -> list[tuple[str, str]]:
    """Every (path, title) pair one SSO `/Browse` listing page lists, deduplicated by path.

    Pure and side-effect free, so the test suite can drive it against a saved fixture with no
    network. Returns the bare path (`/Act/PDPA2012`), not an absolute URL, because both the
    corpus-shaped row and the `DiscoveredDoc` need to derive two DIFFERENT URLs from it (the
    landing page and the PDF body) — resolving here would bake in one of them.
    """
    seen: set[str] = set()
    rows: list[tuple[str, str]] = []
    for href, title in _ROW_RE.findall(html):
        path = href.split("?")[0]
        if path in seen:
            continue
        seen.add(path)
        rows.append((path, _clean_title(title)))
    return rows


def _body_url(path: str) -> str:
    """SSO serves the whole instrument as PDF at `?ViewType=Pdf` (verified). The landing page
    (bare path) is the citable URL; this is what gets fetched for the body."""
    return f"{SG_BASE}{path}?ViewType=Pdf"


def _relevance(kind: str, title: str, indicators: list) -> float:
    """How much of the discovery budget this Act deserves, from its TITLE alone (the body is
    not fetched at discovery time). See module docstring's "RELEVANCE SCORING" section.
    """
    base = _KIND_WEIGHT.get(kind, 0.40)
    topic = 0.0
    if indicators:
        from .discovery import _score as _topic_score
        topic = _topic_score(title, indicators)
    return round(min(0.99, max(0.05, base + 0.35 * topic)), 4)


def enumerate_sso(client, log: Log = safe_log, kinds=("Act",), page_size: int = 500) -> list[dict]:
    """Enumerate SSO's browse index via sort-window union. Returns CORPUS-SHAPED dicts — the
    same shape `backend/corpus/catalogue.py` has always consumed — WITHOUT a `law_id` key;
    `catalogue.enumerate_sg` adds that itself (see module docstring's "two id schemes" note).

    `log` defaults to `backend.console.safe_log`, NOT `print` — a bare `print` of non-ASCII text
    (a Mongolian portal name, in the incident `backend/console.py`'s own docstring records)
    raised `UnicodeEncodeError` under the Windows console code page from inside an `except`
    block that existed so one dead query would not be fatal, and killed the run instead. SG's
    own titles are ASCII, but this function is called from `backend/corpus/catalogue.py`, which
    is not ASCII-only territory, and a `print` default here would be the same trap waiting for
    whichever caller does not think to override it.

    SSO throttles hard: it answers a burst with `202` and an EMPTY body rather than `429`, which
    is exactly what `portal.portal_get` already treats as a throttle-and-retry rather than a
    result (Task 1). Deliberately slow — four windows per kind, each with a politeness pause —
    so this is minutes, not seconds, same as `catalogue.enumerate_sg` before it.

    `client is None` is a real caller shape only in tests (a stubbed `portal.portal_get` that
    ignores its `client` argument); the sleep is skipped in that case so the unit test does not
    pay four real multi-second pauses for a portal it never actually touches.
    """
    rows: list[dict] = []
    for kind in kinds:
        seen: set[str] = set()
        total: int | None = None
        for sort_by, order in _SG_SORTS:
            url = (f"{SG_BASE}/Browse/{kind}/Current/All?PageSize={page_size}"
                   f"&SortBy={sort_by}&SortOrder={order}&CurrentPage=1")
            resp = portal.portal_get(client, url, log)
            if resp is None:
                log(f"[sg_sso] {kind}: window {sort_by}/{order} unavailable")
                continue
            text = resp.text
            if total is None:
                m = _COUNT_RE.search(re.sub(r"<[^>]+>", " ", text))
                total = int(m.group(1).replace(",", "")) if m else None
            for path, title in _browse_rows(text):
                if path in seen:
                    continue
                seen.add(path)
                landing = SG_BASE + path
                rows.append({
                    "economy": "SG", "portal": "sso.agc.gov.sg", "title": title[:400],
                    "law_number": path.rsplit("/", 1)[-1], "source_url": landing,
                    "body_url": _body_url(path),
                    "collection": "act" if kind == "Act" else "subsidiary",
                    "status": "active",
                    "catalogue_json": _json({"browse_kind": kind, "window": f"{sort_by}/{order}"}),
                })
            log(f"[sg_sso] {kind}: {sort_by}/{order} -> {len(seen)} unique so far")
            if client is not None:
                time.sleep(settings.crawl_delay_seconds)
        if total and len(seen) < total:
            log(f"[sg_sso] {kind}: INCOMPLETE — {len(seen)}/{total} enumerated "
                f"(SSO ignores CurrentPage; raise PageSize or add sort windows)")
        elif total:
            log(f"[sg_sso] {kind}: complete — {len(seen)}/{total}")
        else:
            log(f"[sg_sso] {kind}: {len(seen)} enumerated (no total reported by the portal)")
    return rows


def search_sg_sso(client, src: dict, query: str, economy: Economy, indicators: list,
                   log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    `query` is deliberately unused: like `mn_legalinfo` and `tl_gazette`, this portal is
    enumerated wholesale by sort-window union, not searched by keyword — SSO's own on-portal
    search is token-AJAX, not a plain query string. Relevance is decided per document by
    `_relevance` instead, from the title, so `discovery._cap`'s trim to `discovery_max_docs`
    has something better than arrival order to work with.
    """
    portal_name = src.get("name", "Singapore Statutes Online")
    out: list[DiscoveredDoc] = []
    seen_ids: set[str] = set()
    for row in enumerate_sso(client, log):
        title = row["title"]
        score = _relevance(row["collection"], title, indicators)
        # `law_name` is left unset — SSO's row title already IS the Act's own name (unlike
        # India Code, which publishes one record per section), so extraction derives the name
        # from `title` as it does for every other portal-native adapter (TL, Laos, Mongolia).
        doc = portal.make_doc(
            economy, row["source_url"], title, portal_name,
            law_number=row.get("law_number"), score=score,
        )
        if doc.doc_id in seen_ids:
            continue
        seen_ids.add(doc.doc_id)
        out.append(doc)
    log(f"[sg_sso] {len(out)} unique documents")
    return out


def _json(obj) -> str:
    import json
    try:
        return json.dumps(obj, default=str)[:20_000]
    except Exception:  # noqa: BLE001 — catalogue metadata only, never worth failing the run over
        return "{}"


portal.register("sg_sso", search_sg_sso, enumerates_portal=True)
