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
     15 rows/page regardless of the requested `limit` — measured, not assumed; `limit` turned
     out to be the wrong field name entirely, see "DETERMINISM" below). Separately (Step 6,
     live full-adapter run): the feed's OWN ordering is not stable between separate calls
     minutes apart — a law seen on page 10 or 57 in one call was not on the same page in a
     later call. Paging itself still works within a single run (no duplicate ids were ever
     seen across one run's own pages); it is the feed's page ASSIGNMENT that drifts between
     separate calls, the same "content moving between requests" property `adapter_timor.py`'s
     docstring records for its own portal. **This drift is FIXED for the instruments that
     matter — see "DETERMINISM" below, added in a review round after this adapter's first
     version shipped with the drift only disclosed, not fixed.**

Because paging works, this adapter uses the `law` endpoint directly and never touches
`searchResult` (whose payload shape 400s on every guess tried: `keyword`, `search`,
`search_text`, `law_name`, `text`, `category_id`, `hirachy_of_law_id` — none change the
response even on the *working* `law` endpoint either — see "WHAT THIS ADAPTER DOES NOT COVER").
Two OTHER fields, found only in the fix round below by reading the app's request payload
rather than guessing field names, DO work: `size` (the real page-size field) and `hirachy` (a
real, working type filter) — see "DETERMINISM".

WHAT THIS ADAPTER DOES NOT COVER — recorded rather than hidden (the lesson the Timor-Leste
adapter cost this phase: a lane that reads part of a portal and reports success anyway).
`POST …/law` is a BROWSE-ALL feed sorted newest-updated-first, not a search: passing `keyword`,
`search`, `category_id`, `hirachy_of_law_id`, `search_text` or `law_name` in the POST body was
tried against it directly (2026-09-07) and every one of them returned the identical 15 rows and
identical `total: 11406` as no filter at all — none of these fields subset the corpus. The
SUBORDINATE tier (Notifications, Ministerial Regulations, Orders — everything outside
`_LEGISLATIVE_HIRACHY_TIERS`, roughly 10,231 of the 11,406 rows) still has no working filter
and is still walked page-by-page, bounded by `_MAX_PAGES`, RANKED by `_relevance` rather than
searched for, and NOT deterministic — see "DETERMINISM" for what changed and what did not. A
subordinate instrument that `_relevance` ranks low AND that never gets updated recently enough
to surface within `_MAX_PAGES` pages of the newest-first feed will not be seen by a single run
— the same "narrow page budget under-reaches an older foundational statute" trade-off
`adapter_laos.py`'s docstring names for its own `_MAX_PAGES`, not solved here either. The
LEGISLATIVE-GRADE tier (Act and above — where every RDTII citation this adapter has found
actually lives) no longer has this problem; see "DETERMINISM".

DETERMINISM — added in a fix round after review found the gap: a first version of this
adapter disclosed the browse feed's page-order drift (above) but did not fix it, and the
timed live-verification run in that version found only 1 of the 3 RDTII-cited Thai Acts
(Cybersecurity Act 2019) — the Personal Data Protection Act 2019 and the Computer-Related
Crime Act 2007, both present in the Step 1 recon minutes earlier, were simply not in the pages
that particular run happened to walk. Disclosure was the right first step but was not enough:
completeness against the panel's own citations is the deliverable.

The fix has two parts, both found by reading the app's own bundle request payload rather than
guessing field names (`main.7a41c7a0.js`: `nj.getUpdated({...T, size:l>a?a:l, page:d})`):

  * `size`, not `limit`, is the real page-size field — `limit` silently did nothing in every
    round-1 probe. Verified live 2026-09-08: `size=20` -> 20 rows, `size=500` -> 500 rows,
    `size=8000` -> 8000 rows in 14.7s. `size=9000`/`9500` answered a Gateway timeout at least
    once while `size=9998` (near the full 11,406-row corpus) succeeded once — a FLAKY
    boundary, not a documented hard cap, so this adapter caps its own requests at
    `_TIER_FETCH_SIZE_CAP` (3,000), comfortably inside the range measured reliable.
  * `hirachy` is a REAL, working server-side filter (unlike `hirachy_of_law_id`, tried in
    round 1 and silently ignored). Verified live 2026-09-08: `{"hirachy": 1}` dropped `total`
    from 11,406 to 1,113 and the first row was immediately an actual Act. Every RDTII citation
    this adapter's own recon has found — the Computer-Related Crime Act, the Cybersecurity
    Act, the PDPA — carries `hirachy_of_law_id=1` (Act). `_LEGISLATIVE_HIRACHY_TIERS` is the
    FULL "force of an Act or higher" tier from `GET …/law/master`: Act, Organic Act,
    Emergency Decree, Code, Revenue Code, Constitution.

Combined, `size` + `hirachy` mean a WHOLE legislative-grade tier fits in one atomic request
(probe `total` at `size=1`, then fetch at `size=total`) — there is no multi-request window left
for the feed's reordering to act in. `search_th_law` now runs this as PASS 1, deterministic,
before the original bounded browse walk (now PASS 2, secondary, still non-deterministic, kept
only for subordinate instruments the tier list does not reach).

MEASURED, live 2026-09-08, two separate `search_th_law` calls roughly 3 minutes apart (the
first call's own 165s runtime, back to back with the second's): **identical results** — 739
documents both times, the exact same 739 `doc_id`s (0 only-in-run-1, 0 only-in-run-2). PASS 1
alone: `hirachy=1` -> 1,113 rows -> 19 new documents; `hirachy=883` (Emergency Decree) -> 49
rows -> 1 new document; the other four tiers contributed 0 NEW documents (their real content,
where present, was already reached by `hirachy=1`'s superset in these two runs). This is a
measured result for THIS pair of calls, not a guarantee the mechanism can give for all time —
PASS 2 remains architecturally order-dependent even though it happened not to visibly drift in
this particular ~3-minute window; the guarantee this fix actually provides is that PASS 1's
documents do not depend on PASS 2's ordering at all (pinned by
`tests/test_adapter_thailand.py::test_tier_walk_documents_survive_the_browse_walk_reordering`,
which drives a fake feed that DOES reorder between calls and confirms PASS 1's document is
unaffected).

Of the three RDTII-cited Acts specifically, PASS 1 now reliably finds two on every run:

    พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562  (PDPA 2019)                    -> 0.99
    พระราชบัญญัติการรักษาความมั่นคงปลอดภัยไซเบอร์ พ.ศ. 2562  (Cybersecurity Act 2019) -> 0.99

The THIRD, the Computer-Related Crime Act B.E. 2550 (2007), is a SEPARATE, deeper problem that
PASS 1's determinism does not fix and cannot fix: its `content_all` is EMPTY — not merely on
this row, but on every representation of this law found anywhere in the API. Verified live
2026-09-08 three ways: (1) inside the full 1,113-row `hirachy=1` dump, `content_all` is `""`;
(2) `GET …/law/detail/{table_of_law_id}` for the SAME law also returns `content_all: ""`; (3)
a full-corpus scan (two requests, `size=6000` each, covering all 11,406 rows) found exactly
ONE row titled with this Act's name, and it is the same empty one. Its real text is not
missing from the SITE — `GET …/law/detail/9000`'s `content_list_process` field carries 47
structured per-clause objects (`content_type`/`content_number`/`content_desc`) — but reading
THAT field is the same kind of per-clause reconstruction work as the มาตรา-splitting problem
this file's "STEP 1 RECON" Q1 answer already found and left out of scope, and is left out of
scope here for the same reason (a future task, not this adapter file). The PDPA had the SAME
symptom on its `hirachy=1` row (`content_all: ""`) but turned out to have a SECOND, DUPLICATE
row elsewhere in the same tier (a Thai-numeral-year title variant, "๒๕๖๒" vs "2562") whose
`content_all` genuinely is populated (78,093 chars) — `_rows_to_docs`'s existing "drop empty,
keep populated" rule (unchanged, already tested) resolves the duplicate correctly on its own,
which is why the PDPA above shows a real score and the Computer-Related Crime Act does not.

`fetch.seed_cache` tags the cache entry `engine="api"` (see `_store`'s `engine` parameter),
but `FetchResult` itself carries no `engine` field, so nothing downstream can currently tell a
seeded entry from a genuinely fetched one. This is inherited from `adapter_india.py`'s
existing `_seed()`, not introduced here, and is left unfixed (noted for whoever next touches
`fetch.py`, not a Task 4 regression).

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
#: docstring explains for the same trade-off. AS OF 2026-09-08 this walk is SECONDARY — see
#: `_LEGISLATIVE_HIRACHY_TIERS` below for the deterministic primary walk that replaced it for
#: the instruments RDTII actually cites; this bounded, order-dependent walk now exists only to
#: pick up subordinate instruments (Notifications, Ministerial Regulations) outside that tier,
#: and its own non-determinism is disclosed in the module docstring's "DETERMINISM" section.
_MAX_PAGES = 60

#: THE FIX for the page-order-drift finding (see the module docstring's "DETERMINISM" section
#: for the full story and measurements). `hirachy` is a REAL, working server-side filter on
#: `POST …/law` — verified live 2026-09-08: `{"hirachy": 1}` dropped `total` from 11,406 to
#: 1,113 and the first row was immediately an actual Act — unlike every field Task 4's first
#: pass tried (`hirachy_of_law_id`, `category_id`, `keyword`…), which changed nothing. Combined
#: with `size` (see `_TIER_FETCH_SIZE_CAP`), a whole tier fits in ONE atomic request, so there
#: is no multi-request window left for the feed's own reordering to act in. These six ids are
#: the FULL "has the force of an Act or higher" tier from `GET …/law/master` (verified live
#: 2026-09-07): Act, Organic Act, Emergency Decree, Code, Revenue Code, Constitution — every
#: RDTII P6/P7 citation this adapter's own recon has found (PDPA, Cybersecurity Act,
#: Computer-Related Crime Act) carries hirachy=1 (Act). Totals measured live 2026-09-08:
#: 1=1113, 926=4, 883=49, 893=8, 889=0, 887=1 (1,175 total) — never hard-coded here, because a
#: stale count would silently under- or over-fetch; `_fetch_tier` re-probes every call.
_LEGISLATIVE_HIRACHY_TIERS: tuple[int, ...] = (1, 926, 883, 893, 889, 887)

#: The real page-size field is `size`, not `limit` — a genuinely separate finding from the
#: `hirachy` filter, made investigating it. `limit` silently did nothing in every Task 4
#: round-1 probe: the API always answered its own internal default of 15 rows regardless of
#: the `limit` value sent, which is WHY round 1 never noticed `size` existed. `size` was
#: recovered from the app's own bundle (`main.7a41c7a0.js`:
#: `nj.getUpdated({...T, size:l>a?a:l, page:d})`) and verified live 2026-09-08: `size=20` -> 20
#: rows, `size=500` -> 500 rows, `size=8000` -> 8000 rows in 14.7s. `size=9000`/`9500` answered
#: a Gateway "timeout exceeded when trying to connect" at least once while `size=9998` (a
#: near-full-corpus single request) succeeded once — the boundary is FLAKY, not a documented
#: hard cap, so this adapter never asks for more than `_TIER_FETCH_SIZE_CAP`, comfortably
#: inside the range measured reliable and far above the largest legislative tier (1,113).
_TIER_FETCH_SIZE_CAP = 3000

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


def _fetch_tier(client, url: str, headers: dict, hirachy: int, log: Log) -> list[dict]:
    """Every row in one legislative-grade `hirachy` tier — see the module docstring's
    "DETERMINISM" section for why this exists and what it fixes.

    Two requests, not one: a cheap probe (`size=1`) to learn the tier's own `total`, then a
    single atomic fetch at `size=total`. Whenever `total` fits under `_TIER_FETCH_SIZE_CAP`
    (every tier measured live 2026-09-08 does — the largest, Act, is 1,113), there is exactly
    ONE page for the WHOLE tier, so there is no multi-request window left for the feed's own
    reordering (the finding this fix responds to) to act in between them.

    Falls back to a bounded, DEDUPED paged walk within the tier only if a future `total` ever
    exceeds the cap — logged loudly, because that path reintroduces the same reordering risk
    this mechanism exists to avoid, just scoped to one tier instead of the whole corpus.
    """
    try:
        probe = client.post(url, headers=headers,
                             json={"page": 1, "size": 1, "hirachy": hirachy}, timeout=60)
    except Exception as exc:                          # noqa: BLE001 — one tier is not the run
        log(f"[th_law_api] hirachy={hirachy} probe failed: {type(exc).__name__}: {exc}")
        return []
    if probe.status_code != 200:
        log(f"[th_law_api] hirachy={hirachy} probe -> HTTP {probe.status_code}")
        return []
    try:
        # `total` comes back as a STRING ("1113"), not an int — measured live 2026-09-08,
        # easy to miss because Python's own print()/repr() of a dict doesn't show the quotes
        # unless you check .__class__ directly. Cast explicitly rather than let a bare
        # `<=` comparison crash the whole tier walk on a str/int mismatch.
        raw_total = probe.json().get("total")
        total = int(raw_total) if raw_total not in (None, "") else 0
    except Exception as exc:
        log(f"[th_law_api] hirachy={hirachy} probe: unparsable JSON/total ({type(exc).__name__})")
        return []
    if not total:
        return []

    if total <= _TIER_FETCH_SIZE_CAP:
        try:
            resp = client.post(url, headers=headers,
                                json={"page": 1, "size": total, "hirachy": hirachy}, timeout=120)
        except Exception as exc:
            log(f"[th_law_api] hirachy={hirachy} fetch ({total} rows) failed: "
                f"{type(exc).__name__}: {exc}")
            return []
        if resp.status_code != 200:
            log(f"[th_law_api] hirachy={hirachy} fetch -> HTTP {resp.status_code}")
            return []
        try:
            return resp.json().get("rows") or []
        except Exception as exc:
            log(f"[th_law_api] hirachy={hirachy}: unparsable JSON ({type(exc).__name__})")
            return []

    log(f"[th_law_api] hirachy={hirachy}: total={total} exceeds _TIER_FETCH_SIZE_CAP="
        f"{_TIER_FETCH_SIZE_CAP} — falling back to a paged walk (the reordering risk this "
        f"whole mechanism exists to avoid applies to THIS tier only)")
    rows_all: list[dict] = []
    seen_ids: set = set()
    page, max_pages = 1, (total // _TIER_FETCH_SIZE_CAP) + 2
    while len(seen_ids) < total and page <= max_pages:
        try:
            resp = client.post(url, headers=headers,
                                json={"page": page, "size": _TIER_FETCH_SIZE_CAP,
                                      "hirachy": hirachy}, timeout=120)
        except Exception as exc:
            log(f"[th_law_api] hirachy={hirachy} page {page}: {type(exc).__name__}")
            break
        if resp.status_code != 200:
            break
        try:
            rows = resp.json().get("rows") or []
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            lid = r.get("law_id")
            if lid not in seen_ids:
                seen_ids.add(lid)
                rows_all.append(r)
        page += 1
        if client is not None and page <= max_pages:
            time.sleep(settings.crawl_delay_seconds)
    return rows_all


def _emit_docs(rows: list[dict], economy: Economy, portal_name: str, indicators: list | None,
               out: list[DiscoveredDoc], seen_doc_ids: set[str], log: Log) -> int:
    """Turn one batch of raw rows into `DiscoveredDoc`s, seed each new one's fetch cache (see
    the module docstring's "DESIGN DECISION" section), and append it to `out`. Shared by the
    deterministic tier walk and the supplementary browse walk so the seed_cache logic — the
    part that actually gets real Thai text past the SPA shell — is written once. Returns how
    many NEW documents this batch added (for the caller's own log line).
    """
    docs = _rows_to_docs({"rows": rows}, economy, portal_name, indicators)
    content_by_url = {_detail_url(r): (r.get("content_all") or "").strip() for r in rows}
    added = 0
    for doc in docs:
        if doc.doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(doc.doc_id)
        added += 1
        body = content_by_url.get(doc.source_url)
        if body:
            try:
                from .fetch import seed_cache
                seed_cache(doc.source_url, body.encode("utf-8"), "text/plain",
                           log=lambda _m: None)
            except Exception as exc:                  # noqa: BLE001 — discovery still stands
                log(f"[th_law_api] could not seed cache for {doc.doc_id}: "
                    f"{type(exc).__name__}")
        out.append(doc)
    return added


def search_th_law(client, src: dict, query: str, economy: Economy, indicators: list,
                   log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches
    on (once Task 8 wires `"th_law_api"` into the dispatch table — see the module docstring;
    until then this is called directly, as this task's own live verification does).

    `query` is unused: like `adapter_timor.py`/`adapter_laos.py`, the portal's `law` endpoint
    has no working keyword filter (see "WHAT THIS ADAPTER DOES NOT COVER" above) — every field
    name tried changed nothing, so this walks the browse feed and ranks what it finds instead
    of searching for a target.

    Two passes, not one — see the module docstring's "DETERMINISM" section for the full story:
      1. PRIMARY, deterministic: `_fetch_tier` over every id in `_LEGISLATIVE_HIRACHY_TIERS`,
         each in one atomic request. This is where the RDTII-cited instruments live and it is
         reproducible run to run.
      2. SECONDARY, best-effort: the original bounded newest-first browse walk (`_MAX_PAGES`),
         for subordinate instruments (Notifications, Ministerial Regulations) the tier list
         does not cover. This pass is NOT deterministic — the feed's own ordering drifts
         between calls minutes apart (measured; see the module docstring) — and is disclosed
         as such rather than relied on for anything the first pass already covers.

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
    seen_doc_ids: set[str] = set()

    # PASS 1 — deterministic: every legislative-grade instrument, in as few atomic requests
    # as its own total needs. See _fetch_tier's docstring and the module docstring's
    # "DETERMINISM" section.
    for hirachy in _LEGISLATIVE_HIRACHY_TIERS:
        rows = _fetch_tier(client, url, headers, hirachy, log)
        added = _emit_docs(rows, economy, portal_name, indicators, out, seen_doc_ids, log)
        log(f"[th_law_api] hirachy={hirachy}: {len(rows)} rows -> {added} new documents "
            f"({len(out)} total)")
        if client is not None:
            time.sleep(settings.crawl_delay_seconds)

    # PASS 2 — best-effort: the original bounded, newest-first browse walk, for subordinate
    # instruments PASS 1's tier list does not reach. NOT deterministic — see the module
    # docstring's "DETERMINISM" section for the measured overlap between two separate calls.
    seen_law_ids: set = set()
    for page in range(1, _MAX_PAGES + 1):
        try:
            resp = client.post(url, headers=headers, json={"page": page, "size": 30},
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
            # fires inside _MAX_PAGES (every page carried distinct new ids) — kept as the
            # safety net the brief specifies, not dead code.
            log(f"[th_law_api] page {page}: no new law_ids — pagination exhausted")
            break
        seen_law_ids |= row_ids

        added = _emit_docs(rows, economy, portal_name, indicators, out, seen_doc_ids, log)
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
