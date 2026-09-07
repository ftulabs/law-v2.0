r"""Thailand — law.go.th's own REST API, recovered from its published JS bundle.

`data/sources.yaml` used to carry Thailand as *"PDF, frequently scanned … this is the
OCR-heavy lane"* (see the superseded `krisdika.go.th` entry, kept for the record). That was
false, and it is why Thailand sat among the hardest economies for a fortnight: the country's
central legal database, `law.go.th`, is a React single-page app whose data comes from a plain
JSON REST API, not from scanned gazette PDFs. `content_all` on every row IS the statute's full
operative text — no PDF, no OCR, no scan, making Thailand one of the two cleanest sources of
the eleven alongside India (`adapter_india.py`).

ROUTE, verified live 2026-09-07 (recovered from the app's own published static bundle —
`https://www.law.go.th/static/js/main.7a41c7a0.js` — not from defeating any protection; this
is the same JS every visitor's browser downloads to render the page):

    base    https://apig.law.go.th/
    header  x-api-key: <public bundle constant, see data/sources.yaml>
    POST    dga-user-service-phase2/law     -> 200, rows[] with content_all (this adapter)
    GET     dga-user-service-phase2/law/master   -> 200, agencies + law types + categories
    GET     dga-user-service-phase2/law/detail/{id}
    POST    dga-user-service-phase2/law/searchResult  -> 400, payload shape not recovered

`apig.law.go.th` is an AWS API Gateway; an unauthenticated request to a route that does not
exist answers `{"message":"Missing Authentication Token"}` — that is route-not-found, not a
refusal, and the `x-api-key` is a constant compiled into the JS bundle, not a credential issued
to anyone. `robots.allowed()` was checked LIVE against both hosts with the project's own
`crawl_user_agent` (2026-09-07): `www.law.go.th` answers its own `/robots.txt` with HTTP 403
(a WAF page, not a robots file) and `apig.law.go.th` answers `{"message":"Missing
Authentication Token"}` (also non-2xx) — `backend.pipeline.robots._fetch` treats any 4xx as "no
rules published" per RFC 9309 ("an empty file grants"), so `robots.allowed()` returns
`(True, "")` for both, confirmed by calling it directly rather than assumed from the raw HTTP
codes. This is the OPPOSITE of the MY/India "server error -> proceed" carve-out — no override
table entry was needed because the ordinary 4xx-grants rule already covers it.

STEP 1 RECON — the two questions this task's brief requires answered before writing a line of
adapter code, both measured live 2026-09-07 against `POST …/law` with `{"page": N, "limit": 20}`:

  1. Does `content_all` carry มาตรา (article) markers?  YES AS A SUBSTRING, but NOT usable by
     `extraction.ARTICLE_PATTERNS`'s Thai splitter without more work than "split for free" —
     found only at Step 6's LIVE verification, not the static-fixture Step 1 probe, so it is
     recorded here rather than left for the report alone. The sampled Cybersecurity Act 2019
     (54,521 chars fetched live) carries 58 `มาตรา` occurrences, and every sampled row in the
     saved fixture is the same: `content_all` has ZERO `\n` characters — none, in any row,
     including the 69,154-char Administrative Reorganisation Act B.E. 2534 (law_id 1700, 76
     `มาตรา` occurrences). `ARTICLE_PATTERNS[Economy.TH]` requires a `มาตรา` marker at the START
     OF A LINE (`(?m)^[ \t]*มาตรา…`) specifically so it does NOT also match a mid-sentence
     cross-reference like "ตามมาตรา ๗" (see extraction.py's own docstring on this exact hazard).
     With no line breaks at all, that anchor can only ever match position 0 of the string, which
     is never a `มาตรา` marker in a real Act (Thai statutes open with the enacting/citation
     clause, not the first substantive section) — so every document from this lane currently
     extracts as ONE `(document)` block (confirmed live in Step 6: 1 provision, `article_section
     == "(document)"`), not per-provision, even though real per-provision text is sitting right
     there in the string. Reconstructing genuine article boundaries from a newline-free blob
     without misfiring on "ตามมาตรา"/"ในมาตรา"/"แห่งมาตรา" cross-references is a real parsing
     problem (not a one-line regex change) and is OUT OF SCOPE for this adapter file — recorded
     here as a disclosed follow-up rather than attempted with a heuristic nobody has verified.
  2. Does paging work?  YES. `{"page": 1}` and `{"page": 2}` returned ZERO overlapping
     `law_id`s (15 rows each, both pages, `limit` requested was 20 but the API always answers
     15 rows/page regardless of the requested `limit` — measured, not assumed). Separately
     (Step 6, live full-adapter run): the feed's OWN ordering is not stable between separate
     calls minutes apart — a law seen on page 10 or 57 in one call was not on the same page in
     a later call (see "WHAT THIS ADAPTER DOES NOT COVER"). Paging itself still works within a
     single run (no duplicate ids were ever seen across this adapter's own 60 pages); it is the
     feed's page ASSIGNMENT that drifts between separate calls, the same "content moving between
     requests" property `adapter_timor.py`'s docstring records for its own portal.

Because paging works, this adapter uses the `law` endpoint directly and never touches
`searchResult` (whose payload shape 400s on every guess tried: `keyword`, `search`,
`search_text`, `law_name`, `text`, `category_id`, `hirachy_of_law_id` — none change the
response even on the *working* `law` endpoint either; see "WHAT THIS ADAPTER DOES NOT COVER").

WHAT THIS ADAPTER DOES NOT COVER — recorded rather than hidden (the lesson the Timor-Leste
adapter cost this phase: a lane that reads part of a portal and reports success anyway).
`POST …/law` is a BROWSE-ALL feed sorted newest-updated-first, not a search: passing `keyword`,
`search`, `category_id`, `hirachy_of_law_id`, `search_text` or `law_name` in the POST body was
tried against it directly (2026-09-07) and every one of them returned the identical 15 rows and
identical `total: 11406` as no filter at all — none of these fields subset the corpus. With
11,406 laws at 15 rows/page (761 pages) and no working filter, this adapter WALKS the feed
page-by-page and RANKS what it finds (`_relevance`) rather than searching for a target; it does
not and cannot see the whole 11,406-law corpus in one run. `_MAX_PAGES` (below) bounds how far
it walks. A law that this adapter's `_relevance` ranks low AND that never gets updated recently
enough to surface within `_MAX_PAGES` pages of the newest-first feed will not be seen by a
single run — this is the same "narrow page budget under-reaches an older foundational statute"
trade-off `adapter_laos.py`'s docstring names for its own `_MAX_PAGES`, not solved here either.

`_MAX_PAGES` measurement (2026-09-07, same recon run, `limit=20`/15-rows-per-page): scanning
this feed page-by-page for the three RDTII-relevant Acts by name found

    พระราชบัญญัติว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์ พ.ศ. 2550  (Computer-Related Crime
        Act 2007)                                    -> page 10   (law_id 19250)
    พระราชบัญญัติการรักษาความมั่นคงปลอดภัยไซเบอร์ พ.ศ. 2562  (Cybersecurity Act 2019)
                                                       -> page 48   (law_id 3018)
    พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562  (Personal Data Protection Act 2019)
                                                       -> page 57   (law_id 11029)

all three of the RDTII P6/P7 answer key's core Thai instruments surfaced within the first 57
pages of an otherwise-unfiltered chronological feed. `_MAX_PAGES` is set to 60 for headroom —
5 pages of margin past the furthest of the three measured hits, not a round number picked
without evidence. At `settings.crawl_delay_seconds` between successful page fetches (2.0s
measured default) plus ~0.35s/request measured round-trip, a full 60-page walk costs roughly
60 * 2.35 ~= 141s of deliberate wall-clock — in the same range as `adapter_timor.py`'s 183s and
well above `adapter_laos.py`'s 47s, recorded here for Task 10's budget rather than left for
someone else to time. Measured live 2026-09-07/08: a full `search_th_law` call (60 pages, 20
requests/min of throttling via `crawl_delay_seconds`) took 140.9s wall-clock and returned 165
documents, top-scored by `_relevance` as the Cybersecurity Act 2019 (0.99). The SAME three
target Acts named above are NOT reliably in that 165 on every call: the feed's page assignment
drifted between the Step 1 recon (minutes earlier, same day) and this run — Computer-Related
Crime Act 2007 and the Personal Data Protection Act 2019 were not among the 165 documents this
particular call returned, while the Cybersecurity Act 2019 was (top-ranked). This is the
portal's OWN ordering moving, not a bug in this adapter's pagination (no `law_id` repeated
across this run's own 60 pages, confirmed by the `seen_law_ids` check in `search_th_law`) —
recorded here rather than only in the task report because a reader of this file, not just the
report, needs to know a single `_MAX_PAGES`-bounded run is not guaranteed to reach every core
Act every time.

ARTICLE SPLITTING, measured live (Step 6): the Cybersecurity Act 2019 fetched above (54,521
chars, 58 `มาตรา` occurrences) currently extracts as ONE `(document)` block, not 58 provisions
— see the "STEP 1 RECON" section's Q1 answer above for why (`content_all` has zero `\n`
characters, and the Thai splitter is deliberately line-anchored so it does not also fire on
"ตามมาตรา" cross-references). This is disclosed, not silently shipped: the documents this lane
finds ARE the right ones (title, citation, relevance all measured live and correct), but until
a future task teaches extraction a newline-free Thai boundary rule, they reach the grader with
one whole-Act citation instead of article-level ones.

DESIGN DECISION — raw_text vs. seed_cache vs. "just emit the URL" (the brief's own named
question): `DiscoveredDoc.raw_text` is declared "filled by extraction" and IS read as a
fallback inside `ocr._extract_document_text`, but ONLY when `doc.local_path` is falsy AND the
document reaches extraction at all. `orchestrator.py`'s fetch stage (`if d.local_path: ...
continue`) never inspects `raw_text` — for every live-discovered document with no `local_path`
it unconditionally calls `fetch_to_cache(fetch_url)`, and if that fetch fails the document is
DROPPED before extraction ever runs (`if not fr: continue` — never falls back to `raw_text`).
So setting `raw_text` alone, with `source_url` left as the plain detail page, would NOT bypass
the network fetch — confirmed by reading both functions, not assumed from the brief's framing.

That would already be reason enough to "emit the URL and let fetch do its job" per the brief's
literal fallback — except doing so here hits a SECOND, worse problem this recon also found:
`https://www.law.go.th/` is a pure Create-React-App shell (`<div id="root"></div>`, verified
live 2026-09-07, 1,256 bytes, no server-rendered content at all) and `ocr.is_js_app_shell`'s
`_SPA_MARKERS` list (`ng-version=`, `<app-root`, `data-reactroot`, `__next_data__`,
`window.__nuxt`, `id="__nuxt"`, `src="/assets/index-`, `<div id="app"></div>`) does NOT include
Create React App's own `<div id="root">` convention. A plain fetch of the detail page would
therefore NOT be caught by the existing shell detector — it would be read as ordinary HTML,
de-chromed to a handful of characters of site chrome, and emitted as one real-looking,
citation-bearing, EMPTY "(document)" provision block per law. That is a SILENT coverage gap of
exactly the kind this phase exists to remove, worse than the detected-shell case (which at
least logs `js_app_shell` and returns nothing).

The resolution used here is `fetch.seed_cache` — written for exactly this shape of problem
(`adapter_india.py`'s own `_seed`, whose docstring says "the text arrived with the search
result and the citable HTML page 502s today"; Thailand's citable HTML page does not 502, it
just never carries the text at all, but the fix is the same). `search_th_law` seeds the fetch
cache, keyed by the document's own `source_url`, with `content_all` as `text/plain` BEFORE
returning. `orchestrator.py`'s fetch stage then calls `fetch_to_cache(d.source_url)` exactly as
it would for any other document, gets a cache HIT (no network request, no SPA shell ever
touched), and extraction reads real Thai statute text — no code outside this adapter had to
change. `DiscoveredDoc.raw_text` itself is left unset: it would be dead weight once the cache
is seeded (the fetch stage does not consult it), and setting it anyway risks implying to a
future reader that it is load-bearing when it is not.

`source_url` is still the human-openable `www.law.go.th` page (never `apig.law.go.th`, which
answers only with the `x-api-key` header) — recovered from the SAME published JS bundle:
`main.7a41c7a0.js` react-router's the detail view at `/DetailLawPage?table_of_law_id=<id>` and
its own "share this law" links build the identical URL
(``${window.location.origin}/DetailLawPage?table_of_law_id=${k}``). A reviewer who opens it
sees the real page load (client-side) the same content this adapter already read from the API.

CHARACTER ENCODING: `httpx`'s `response.json()` decodes the body as UTF-8 by the `Content-Type:
application/json; charset=utf-8` header the API actually sends (verified live 2026-09-07), and
every Thai string sampled round-trips correctly — printed via a UTF-8-wrapped stdout, titles
read as real Thai (e.g. "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562"), not mojibake. Unlike
`adapter_timor.py`'s HTML pages (which declare `windows-1252`/`iso-8859-1` in a `<meta>` tag
httpx never reads), a JSON API has no separate declared-vs-actual encoding to get wrong.

RELEVANCE SCORING — `content_all` is this adapter's real advantage over `adapter_timor.py` and
`adapter_laos.py`, which can only score a row's TITLE (no body text available at discovery
time). `_relevance` combines three signals, all computed from the row alone (no extra fetch):
  1. `hirachy_of_law_id` (the portal's own instrument-type code, from `GET …/law/master`,
     verified live 2026-09-07) — a `พระราชบัญญัติ` (Act, id 1) or `พระราชกำหนด` (Emergency
     Decree, id 883) outranks a `ประกาศ` (Notification, id 2) or `คำสั่ง` (Order, id 885), which
     make up most of the browse feed (routine tax/customs circulars).
  2. presence of `มาตรา` markers in `content_all` — a small bonus for "this is structured
     legislation", not a one-paragraph administrative notice.
  3. `_TH_SEED_TERMS` hits against the FULL `content_all` body (not just the title) — a small,
     adapter-local Thai vocabulary. `query_terms_i18n.py` has no `"th"` entry yet (`TH` maps to
     `"th"` in `ECONOMY_QUERY_LANG` but `NATIVE_QUERY_TERMS` carries no `"th"` key — a staged,
     unvalidated gap recorded in that module's own docstring), so this is intentionally NOT
     wired into the shared multilingual retrieval vocabulary; it is scoped to this adapter only,
     sourced directly from the three Acts' own operative titles found in the Step 1 recon above
     plus generic P6/P7 phrasing (cross-border transfer, storage/retention, DPO). UNVALIDATED
     against a full crawl, the same caveat Mongolia's seed list carries — a term that never
     fires here should be found and dropped by whoever builds a Thai equivalent of
     `tools/audit_native_terms.py`.
  4. `indicators`' own ENGLISH `query_terms`, via `discovery._score`, when `indicators` is
     passed in — included for consistency with `adapter_timor.py`/`adapter_laos.py` and the
     rare English loanword/acronym, but expected to read near-zero for Thai-only text, the same
     known bias those two modules record for non-English titles.
A flat `relevance_score=1.0` (the `portal.make_doc` default) would make `discovery._cap`'s trim
to `discovery_max_docs` (22) arbitrary among however many documents a `_MAX_PAGES` walk turns
up; these four signals give it something real to sort on instead.

A ROW WITH NO USABLE TEXT is dropped, not emitted empty: `content_all` is blank for roughly a
third of rows sampled in Step 1 (a landing record whose text has not been re-published, or a
notification that references another instrument rather than stating one) — `_rows_to_docs`
drops these before scoring rather than emitting a document that fetches to nothing and reaches
the grader as one blank "(document)" block (the same shell problem `is_js_app_shell` and
`corpus.build._looks_like_a_shell` both exist to catch downstream; here it is caught upstream,
at the source).
"""
from __future__ import annotations

import time
from typing import Callable

from ..config import settings
from ..schemas import DiscoveredDoc, DocFormat, Economy
from . import portal, robots

Log = Callable[[str], None]

#: See the module docstring's "`_MAX_PAGES` measurement" section: all three RDTII-relevant Acts
#: found within the first 57 of the browse feed's 761 total pages (11,406 laws / 15 rows-page,
#: measured live 2026-09-07). 60 = 5 pages of margin past the furthest measured hit, not a
#: round number chosen without evidence. Raising it is a one-line change, traded here for a
#: bounded single-run wall-clock/request count exactly as `adapter_laos.py`'s own `_MAX_PAGES`
#: docstring explains for the same trade-off.
_MAX_PAGES = 60

#: The portal's own `hirachy_of_law_id` codes, from `GET dga-user-service-phase2/law/master`
#: (verified live 2026-09-07 — the full list, not a guess). `พระราชบัญญัติ` (Act) is id 1;
#: `ประกาศ` (Notification, id 2) is the single most common code in the browse feed and is a
#: routine administrative notice far more often than a data-protection/cybersecurity measure.
_HIRACHY_WEIGHT: dict[int, float] = {
    1: 0.85,      # พระราชบัญญัติ — Act (both target Acts found in Step 1 carry this code)
    926: 0.85,    # พ.ร.บ.ประกอบรัฐธรรมนูญ — Organic Act
    883: 0.80,    # พระราชกำหนด — Emergency Decree (force of an Act)
    893: 0.78,    # ประมวลกฎหมาย — Code (e.g. Criminal/Civil and Commercial Code)
    889: 0.75,    # ประมวลรัษฎากร — Revenue Code
    887: 0.65,    # รัฐธรรมนูญ — Constitution
    884: 0.55,    # พระราชกฤษฎีกา — Royal Decree
    888: 0.50,    # กฎกระทรวง — Ministerial Regulation
    885: 0.30,    # คำสั่ง — Order
    2: 0.25,      # ประกาศ — Notification (bulk of the feed; routine administrative notices)
}
_DEFAULT_HIRACHY_WEIGHT = 0.20

#: Adapter-local Thai vocabulary — NOT wired into `query_terms_i18n.py` (see the module
#: docstring's "RELEVANCE SCORING" section for why and its provenance). Matched against the
#: FULL `content_all` body, which is this adapter's real advantage over a title-only lane.
_TH_SEED_TERMS: tuple[str, ...] = (
    "ข้อมูลส่วนบุคคล",          # personal data — พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล's own title
    "คุ้มครองข้อมูล",            # data protection
    "ไซเบอร์",                   # cyber — พ.ร.บ.การรักษาความมั่นคงปลอดภัยไซเบอร์'s own title
    "ความมั่นคงปลอดภัย",         # security
    "คอมพิวเตอร์",                # computer — พ.ร.บ.ว่าด้วยการกระทำความผิดเกี่ยวกับคอมพิวเตอร์
    "ส่งข้อมูลไปยังต่างประเทศ",   # transferring data abroad (cross-border transfer, generic P6)
    "โอนข้อมูลไปต่างประเทศ",      # transfer of data abroad (alternative phrasing)
    "จัดเก็บข้อมูล",              # store/hold data (P6 localisation phrasing)
    "เก็บรักษาข้อมูล",            # retain data (P7 retention phrasing)
    "เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล",  # Data Protection Officer (P7-I4 phrasing)
)


def _detail_url(row: dict) -> str:
    """The human-openable `www.law.go.th` page for this row — NEVER `apig.law.go.th`, which
    answers only with the `x-api-key` header and is not something a reviewer can open (one of
    this task's own tests pins that). Recovered from the app's own published bundle: its
    react-router pushes `/DetailLawPage?table_of_law_id=<id>` for a law-detail navigation and
    builds the IDENTICAL url for its own "share this law" links — not a guessed pattern.

    Prefers `table_of_law_id` (what the JS actually keys the route on — verified against
    several `Link to=` call sites in `main.7a41c7a0.js`) over `law_id`, which is a DIFFERENT
    id on the same row (e.g. one sampled row carried `law_id=19639` but
    `table_of_law_id=12306`) and would point at the wrong law's page if used here.
    """
    tid = row.get("table_of_law_id") or row.get("law_id") or ""
    return f"https://www.law.go.th/DetailLawPage?table_of_law_id={tid}"


def _th_topic(content: str) -> float:
    """Fraction (capped at 1.0) of `_TH_SEED_TERMS` present anywhere in `content_all`."""
    if not content:
        return 0.0
    hits = sum(1 for term in _TH_SEED_TERMS if term in content)
    return min(1.0, hits / 4)


def _relevance(row: dict, indicators: list | None) -> float:
    """A real, differentiated score for one row — see the module docstring's "RELEVANCE
    SCORING" section for what each signal is and why. `indicators` is optional (default None)
    so `_rows_to_docs` stays callable with exactly the 3 positional arguments this task's own
    tests use; `search_th_law` passes the run's real indicator list through.
    """
    content = row.get("content_all") or ""
    raw_hirachy = row.get("hirachy_of_law_id")
    try:
        hirachy = int(raw_hirachy) if raw_hirachy not in (None, "") else None
    except (TypeError, ValueError):
        hirachy = None
    base = _HIRACHY_WEIGHT.get(hirachy, _DEFAULT_HIRACHY_WEIGHT)
    structure_bonus = 0.05 if "มาตรา" in content else 0.0
    topic = _th_topic(content)
    en_topic = 0.0
    if indicators:
        from .discovery import _score as _topic_score
        title = row.get("law_name_og") or row.get("law_name_th") or ""
        en_topic = _topic_score(f"{title} {content[:4000]}", indicators)
    score = base + structure_bonus + 0.35 * topic + 0.10 * en_topic
    return round(min(0.99, max(0.05, score)), 4)


def _iso_date(row: dict) -> str | None:
    """The row's own `effective_startdate`/`annouce_date`, trimmed to its date portion, when
    that field is a recognisable ISO-ish timestamp. `None` otherwise — never a guess."""
    for key in ("effective_startdate", "annouce_date"):
        raw = row.get(key) or ""
        if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
            return raw[:10]
    return None


def _rows_to_docs(payload: dict, economy: Economy, portal_name: str,
                   indicators: list | None = None) -> list[DiscoveredDoc]:
    """One page of `POST …/law`'s `rows[]` -> `DiscoveredDoc`s. Pure: no network, no
    filesystem — the test suite drives this directly against the saved fixture.

    A row with no usable `content_all` (or no title) is DROPPED, not emitted empty — see the
    module docstring's "A ROW WITH NO USABLE TEXT" section. `indicators` is optional so this
    keeps the exact 3-positional-argument shape this task's tests call it with; `search_th_law`
    passes the real run's indicators through for the extra English-term signal in `_relevance`.
    """
    out: list[DiscoveredDoc] = []
    seen: set[str] = set()
    for row in payload.get("rows") or []:
        content = (row.get("content_all") or "").strip()
        if not content:
            continue
        title = (row.get("law_name_og") or row.get("law_name_th") or "").strip()
        if not title:
            continue
        url = _detail_url(row)
        doc = portal.make_doc(
            economy, url, title, portal_name, fmt=DocFormat.TEXT,
            score=_relevance(row, indicators), amendment_date=_iso_date(row))
        if doc.doc_id in seen:
            continue
        seen.add(doc.doc_id)
        out.append(doc)
    return out


def search_th_law(client, src: dict, query: str, economy: Economy, indicators: list,
                   log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches
    on (once Task 8 wires `"th_law_api"` into the dispatch table — see the module docstring;
    until then this is called directly, as this task's own live verification does).

    `query` is unused: like `adapter_timor.py`/`adapter_laos.py`, the portal's `law` endpoint
    has no working keyword filter (see "WHAT THIS ADAPTER DOES NOT COVER" above) — every field
    name tried changed nothing, so this walks the browse feed and ranks what it finds instead
    of searching for a target.

    `api_base` and `x-api-key` come from `src` (the `sources.yaml` entry), never hard-coded, so
    a key rotation is a config change — if either is missing this logs an `[error]`-shaped line
    and returns an empty list rather than raising or guessing.
    """
    api_base = (src.get("api_base") or "").rstrip("/")
    api_key = src.get("api_key")
    if not api_base or not api_key:
        log("[error] th_law_api: sources.yaml entry has no api_base/api_key — "
            "cannot query apig.law.go.th (see data/sources.yaml's TH law.go.th entry)")
        return []
    url = f"{api_base}/dga-user-service-phase2/law"

    ok, why = robots.allowed(url, settings.crawl_user_agent)
    if not ok:
        log(f"[th_law_api] robots refuses {url} — {why}")
        return []
    if why:
        log(f"[th_law_api] robots: {why}")

    headers = {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Origin": "https://www.law.go.th",
        "Referer": "https://www.law.go.th/",
    }
    portal_name = src.get("name", "law.go.th")

    out: list[DiscoveredDoc] = []
    seen_law_ids: set = set()
    seen_doc_ids: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        try:
            resp = client.post(url, headers=headers, json={"page": page, "limit": 20},
                               timeout=60)
        except Exception as exc:                      # noqa: BLE001 — one bad page is not fatal
            log(f"[th_law_api] page {page}: {type(exc).__name__}: {exc}")
            break
        if resp.status_code != 200:
            log(f"[th_law_api] page {page} -> HTTP {resp.status_code}, stopping")
            break
        try:
            payload = resp.json()
        except Exception as exc:
            log(f"[th_law_api] page {page}: unparsable JSON ({type(exc).__name__})")
            break

        rows = payload.get("rows") or []
        row_ids = {r.get("law_id") for r in rows if r.get("law_id") is not None}
        new_ids = row_ids - seen_law_ids
        if rows and not new_ids:
            # Step 1's own stop condition: a page returning no new ids means pagination has
            # looped or exhausted the feed. Measured live 2026-09-07 this never actually
            # fires inside _MAX_PAGES (every page carried 15 distinct new ids) — kept as the
            # safety net the brief specifies, not dead code.
            log(f"[th_law_api] page {page}: no new law_ids — pagination exhausted")
            break
        seen_law_ids |= row_ids

        docs = _rows_to_docs(payload, economy, portal_name, indicators)
        content_by_url = {_detail_url(r): (r.get("content_all") or "").strip() for r in rows}
        added = 0
        for doc in docs:
            if doc.doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc.doc_id)
            added += 1
            body = content_by_url.get(doc.source_url)
            if body:
                # Seed the fetch cache with the text law.go.th's own API already handed us —
                # see the module docstring's "DESIGN DECISION" section for why this, and not
                # `raw_text` or a bare detail-page URL, is what actually gets real Thai text
                # to extraction instead of an unrendered React shell.
                try:
                    from .fetch import seed_cache
                    seed_cache(doc.source_url, body.encode("utf-8"), "text/plain",
                               log=lambda _m: None)
                except Exception as exc:              # noqa: BLE001 — discovery still stands
                    log(f"[th_law_api] could not seed cache for {doc.doc_id}: "
                        f"{type(exc).__name__}")
            out.append(doc)
        log(f"[th_law_api] page {page}: {len(rows)} rows -> {added} new documents "
            f"({len(out)} total)")
        if not rows:
            log(f"[th_law_api] page {page}: empty page — stopping")
            break
        if client is not None and page < _MAX_PAGES:
            # settings.crawl_delay_seconds, the project's shared politeness floor — this host
            # publishes no robots.txt Crawl-delay of its own to defer to (see the module
            # docstring's robots finding: both hosts answer non-2xx, so there is no Crawl-delay
            # line to read), the same situation adapter_laos.py's own crawl-delay comment names.
            time.sleep(settings.crawl_delay_seconds)
    return out


portal.register("th_law_api", search_th_law)
