"""Laos — laoofficialgazette.gov.la, a Yii app with a real server-rendered document table.

`data/sources.yaml` recorded this host as *"URLError — host does not resolve"* and called
Laos *"the weakest coverage of the nine on every axis"*. Both were wrong. Probed live
2026-09-07 (re-confirmed 2026-09-08, the day this adapter was written) the host answers
**HTTP 200, 110 KB (page text), 136,331 bytes on disk, 12,477 Lao characters**, and it is one
of the most tractable portals in this phase: no JS rendering, no WAF, no encrypted catalogue.

ROUTES, verified live 2026-09-08:

    ?r=site/index&Document_page=N     paginated list — TWO independent tables per page (see
                                       "TWO GRIDS" below), each carrying real titles, agency,
                                       two dates, instrument type, and PDF link(s)
    ?r=site/display&id=N              detail page for one instrument (mostly nav chrome; the
                                       PDF it links is the SAME url the list page already
                                       carries, so this adapter never fetches it)
    ?r=site/list&legaltype=N          filter by instrument type (unused — see "IGNORING
                                       query" below)
    ?r=site/switchpage&lc=en          English edition toggle (session-cookie based — see
                                       "THE ENGLISH TOGGLE" below; NOT used)
    /kcfinder/upload/files/*.pdf      the gazette PDFs themselves — this is the source_url
                                       every DiscoveredDoc here actually points at

A guessed `id=1` on `site/display` returns HTTP 404 (verified 2026-09-07) — ids come from the
list page and nowhere else; nothing here walks a numeric range.

IDS COME FROM `table.items` ROWS ONLY, NOT FROM ANY `<a href>` ON THE PAGE. The naive read —
"every `r=site/display` link on the page is a document" — is wrong. Page 1 carries 26 distinct
`site/display&id=` links, but only 20 are documents (10 per grid, see below); the other 6 are
static site chrome: "About us", "Contact us", "Help", "Other websites" (all four sit in a
`<li>`, never inside a `<tr>`) and one "Legal system of Lao PDR" info blurb that DOES sit
inside a `<tr>` — but in a plain, un-classed `<table>`, not `table.items`. Scoping every parser
here to `table.items` rows excludes all six without a name-based denylist, and as a side
effect also excludes the page's 141 `agencies_id=` and 36 `legaltype=` filter links (verified
live: zero of either land inside `table.items` — they are select-driven, not anchors).

TWO GRIDS SHARE ONE PAGE PARAM. `Document_page=N` is a Yii `CGridView` pager id, and this page
runs TWO independent grids that happen to share it: `homelegal-grid` (1,479 rows total,
"latest documents") and `olddoc-result` (292 rows total, "archived documents") — 10 rows each,
20 `table.items` rows per fetched page. This was not assumed; it was found by walking every
`table.items` on the saved fixture and reading each one's preceding "showing 1-N of TOTAL"
caption, which names the two totals directly. Because both grids paginate together, walking
`Document_page` 1..N does advance BOTH lists in lockstep (confirmed: pages 2 and 3 each added
20 new distinct ids out of the 26 total anchors present, i.e. every genuine document row was
new). Laos does NOT hit the "portal ignores its own page parameter" stop condition this task
named — pagination is real and this adapter relies on it.

WHY THIS ADAPTER DOES NOT CALL `portal_strategies.paginated_index` DIRECTLY, even though the
task plan named it: that helper reads BOTH the href AND the title off the SAME anchor
(`a.get("href")`, `a.get_text()`). On this portal the anchor's own text is the generic literal
"ເບິ່ງ" ("View") for every single row — the real law title lives in a SIBLING `<td>` (the
first cell of the row), exactly the shape `adapter_timor.py`'s `_law_rows` was written to
solve for a different portal. Calling the generic helper as specified would title every one of
the ~20 documents/page "View", which would not just be cosmetically bad — it would break the
"give every document a real relevance score" requirement this task also carries, because
`_relevance` below scores on the TITLE, and 20 identical titles collapse back into exactly the
flat-score failure mode `adapter_mongolia.py` and `adapter_timor.py` both document fixing. The
"stop at the first page that adds nothing new" termination rule IS reused, by hand, in
`search_la_gazette`'s own loop (see `seen_detail`), so the useful part of the shared strategy
survives even though the call does not.

ENCODING, checked per this task's standing instruction (the Timor-Leste adapter immediately
before this one found the portal's declared charset and httpx's guess disagreeing, corrupting
every Portuguese title). Here they AGREE: the page's own
`<meta http-equiv="Content-Type" content="text/html; charset=utf-8">` and httpx's own
`resp.encoding` both say UTF-8 (verified live 2026-09-08, both directions — a fresh `httpx.get`
reports `.encoding == "utf-8"` and the same request's raw bytes carry the same meta tag). No
`_decode()`-style override is needed here; `resp.text` is used as-is. Recorded so the check is
provably a check and not an assumption, matching the lesson without inventing a mismatch that
was not measured.

THE ENGLISH TOGGLE is SESSION-based, not per-URL, so this adapter does not use it — per this
task's own fallback instruction ("if Step 1 showed the toggle is session-based rather than
per-URL, say so and skip it"). Measured live 2026-09-08: appending `&lc=en` directly to a
`site/index` fetch on a client that has never visited `site/switchpage` changes nothing (row
text stays Lao). Visiting `site/switchpage&lc=en` first sets a `lang=en` cookie
(`Set-Cookie: lang=en; HttpOnly`), and only THEN do subsequent `site/index` fetches on that
SAME cookie jar render English row titles. Using it here would mean either (a) mutating the
shared `httpx.Client` the whole `discover_live` run passes around — a side effect that would
silently change what every OTHER lane sees from this host for the rest of the run — or
(b) opening a second, adapter-private client, adding a full extra round trip per page for a
feature that does not even cover every document: several English cells were observed reading
the literal placeholder "Eng – version not available" rather than a translation. Skipped, not
guessed.

`robots.txt` returns the site's OWN HOMEPAGE (HTTP 200, HTML, not a robots file) because the
Yii app has a catch-all route with no dedicated robots handler. `robots.allowed()` already
tolerates a body it cannot parse as robots rules (no `Disallow` line matches, so nothing is
refused) — this is not special-cased here, it is simply why the host reads as fully permitted
to a polite crawler that identifies itself.

HAZARDS THAT ARE STILL TRUE, carried forward rather than solved by this adapter: Lao statutes
served here are commonly SCANNED PDFs, and there is no maintained Lao OCR model in this
pipeline, so extraction quality on a genuine scan is unverified. Separately, legacy Lao fonts
(pre-Unicode) map Lao letters onto upper-ASCII code points, so even a PDF with a real text
layer can decode as mojibake rather than throwing any error. `script_validity()` is the only
defence against either failure mode and it is advisory, not a gate — it can flag a bad
extraction but nothing here stops a bad one from being returned as if it were good.

WHY `search_la_gazette` IGNORES `query` ENTIRELY: like `adapter_timor.py`'s `search_tl_gazette`
and `adapter_mongolia.py`'s `_search_mn_legalinfo`, this portal's list has no free-text search
box of its own to hand a keyword to (only the two dropdown filters above, which need an id, not
a string). So the lane enumerates what the paginated list offers and leaves topical relevance
to `_relevance` / `discovery._cap`, exactly as those two adapters already do.

`_MAX_PAGES` is a deliberate PARTIAL walk, not the whole catalogue. Total rows measured live
2026-09-08: 1,479 (`homelegal-grid`) + 292 (`olddoc-result`) = 1,771, at 20 `table.items` rows
per fetched page — a full walk is ~89 fetches. `_MAX_PAGES` below is far short of that on
purpose: `discovery._cap` only keeps `discovery_max_docs` (22 by default) documents per run
regardless of how many this adapter returns, and both grids sort newest-first (verified: row
dates on page 1 run 2026-08-28, 2026-08-21, … descending), so the documents a small page budget
reaches are the ones most likely to still be in force. This is the same trade-off TL's own
docstring names for its "2011-ish" static tree, stated here rather than left implicit: a
narrow page budget will under-reach an older foundational statute (a data-protection or
cybersecurity Act enacted years ago and not recently re-gazetted) unless it happens to still
rank inside the walked pages. Raising `_MAX_PAGES` is a one-line change; it is not raised
further here only to keep a single live-verification run's wall-clock and request count
reasonable for this task.

CRAWL DELAY: this host publishes no `Crawl-delay` of its own (there is no parseable
`robots.txt` at all, per above), so `search_la_gazette` sleeps `settings.crawl_delay_seconds`
— the project's shared default — between successful page fetches, rather than either hammering
the host with zero delay or inventing a portal-specific number nobody measured. The sleep is
skipped when `client is None`, which is only true in this module's own unit test.
"""
from __future__ import annotations

import re
import time
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from ..config import settings
from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

_BASE = "https://laoofficialgazette.gov.la"
_LIST_URL = _BASE + "/index.php?r=site/index&Document_page={page}"

#: Matches the detail link's id, tolerant of either a raw `&` or an HTML-entity-encoded
#: `&amp;` (BeautifulSoup already decodes entities in `.get("href")`, but the raw fixture on
#: disk still has `&amp;`, and this regex is also exercised against raw hrefs in `_rows`).
_DISPLAY_ID_RE = re.compile(r"r=site/display&(?:amp;)?id=\d+")

#: `Document_page` walks TWO independent grids at once (see the module docstring's "TWO
#: GRIDS" section): 1,479 + 292 = 1,771 rows total, 20 `table.items` rows per fetched page —
#: measured live 2026-09-08. This is a deliberate partial walk (~89 fetches would be exhaustive
#: — see the module docstring for why that is not done here), sized to stay a reasonable
#: single-run request count while `discovery._cap`'s 22-document trim decides what survives.
_MAX_PAGES = 20

#: `Document[legal_type_id]` dropdown values, copied verbatim from the portal's own filter
#: (verified live 2026-09-08 — not transliterated by hand, to avoid a typo turning into a
#: silent scoring miss). A row's own `td[4]` carries these same strings without the "- - "
#: sub-category prefix, so lookup in `_relevance` strips a leading "- " before matching.
#: Constitution/Law/Code outrank the rest because those are the instruments RDTII indicators
#: are usually citing; Decree/Ordinance sit in the middle; Decision/Order/Guideline — the bulk
#: of the day-to-day gazette traffic, per the fixture — sit lowest, mirroring how
#: `adapter_timor.py`'s `_CATEGORY_WEIGHT` orders Resolution below Law/Decree-Law.
_CATEGORY_WEIGHT: dict[str, float] = {
    "ລັດຖະທໍາມະນູນ": 0.95,          # Constitution
    "ກົດໝາຍ": 0.85,                # Law
    "ປະມວນກົດໝາຍ ແພ່ງ": 0.85,       # Civil Code
    "ປະມວນກົດໝາຍ ອາຍາ": 0.85,       # Criminal Code
    "ລັດຖະບັນຍັດ": 0.70,            # Presidential Ordinance
    "ລັດຖະດໍາລັດ": 0.70,            # Presidential Decree
    "ດໍາລັດ": 0.65,                 # Decree
    "ມະຕິຕົກລົງ": 0.55,             # Resolution
    "ຄໍາສັ່ງ": 0.45,                # Order
    "ຂໍ້ຕົກລົງ": 0.45,               # Decision
    "ຄໍາແນະນໍາ": 0.40,              # Guideline / Instruction
}
_DEFAULT_CATEGORY_WEIGHT = 0.40

#: Row dates are `DD-MM-YYYY` (e.g. "28-08-2026" — verified against the saved fixture). Lao
#: PDR's current constitutional order dates to 1975 (Lao People's Democratic Republic
#: founded); nothing in this catalogue predates that, and this module is read well before
#: 2035, so a year outside this band is not treated as a recency signal.
_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_YEAR_MIN, _YEAR_MAX = 1975, 2035


def _rows(html: str, base_url: str) -> list[tuple[str, str, str, str, str]]:
    """Every `table.items` row: (detail url, title, pdf url or "", category, document date).

    The one parser `_detail_ids`, `_pdf_links` and `_relevance`'s caller are all built from,
    so none of them can disagree about which rows exist (see the module docstring's "IDS
    COME FROM `table.items` ROWS ONLY" section for why the scope is `table.items` and not
    every `<a href>` on the page). `title` comes from the row's FIRST `<td>` — the anchor's
    own text is always the generic "ເບິ່ງ" ("View") button label, never the law name.
    `category` is the FIFTH `<td>` (index 4, the instrument-type column) and `date` the THIRD
    (index 2, the instrument's own "DD-MM-YYYY" date, not the later gazette-publish date in
    the fourth) — both verified against the saved fixture; both feed `_relevance`.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str, str, str, str]] = []
    for tr in soup.select("table.items tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        detail_href = None
        for a in tr.select("a[href]"):
            href = a.get("href") or ""
            if _DISPLAY_ID_RE.search(href):
                detail_href = href
                break
        if detail_href is None:
            continue
        detail_url = urllib.parse.urljoin(base_url, detail_href)
        if detail_url in seen:
            continue
        title = " ".join(tds[0].get_text(" ", strip=True).split())
        category = " ".join(tds[4].get_text(" ", strip=True).split()) if len(tds) > 4 else ""
        date_text = tds[2].get_text(" ", strip=True) if len(tds) > 2 else ""
        pdf_url = ""
        for a in tr.select("a[href]"):
            href = a.get("href") or ""
            if ".pdf" in href.lower():
                pdf_url = urllib.parse.urljoin(base_url, href)
                break
        seen.add(detail_url)
        out.append((detail_url, title, pdf_url, category, date_text))
    return out


def _detail_ids(html: str, base_url: str) -> list[tuple[str, str]]:
    """(absolute detail url, title) for every genuine document row on a list page.

    Pure and side-effect free — driven directly against the saved fixture by the test suite,
    no network. A guessed `id=1` 404s (verified 2026-09-07), so nothing anywhere walks a
    numeric id range; every id this adapter ever sees comes from here.
    """
    return [(u, t) for u, t, _pdf, _cat, _date in _rows(html, base_url)]


def _pdf_links(html: str, base_url: str) -> list[str]:
    """Every absolute PDF url a list page's `table.items` rows carry, deduplicated, in row
    order. These are the `/kcfinder/upload/files/*.pdf` gazette documents themselves — the
    actual `source_url` `search_la_gazette` builds each `DiscoveredDoc` from."""
    seen: set[str] = set()
    out: list[str] = []
    for _url, _title, pdf_url, _cat, _date in _rows(html, base_url):
        if pdf_url and pdf_url not in seen:
            seen.add(pdf_url)
            out.append(pdf_url)
    return out


def _relevance(category: str, title: str, date_text: str, indicators: list) -> float:
    """How much of the discovery budget one instrument deserves.

    Three signals, none requiring an extra fetch: instrument TYPE (`_CATEGORY_WEIGHT` — a Law
    or Code outranks a routine Decision), RECENCY (a small bonus for a newer document date,
    since both grids already sort newest-first and a narrow `_MAX_PAGES` walk mostly reaches
    recent instruments — see the module docstring), and topical fit against `indicators` via
    `discovery._score`. That third signal is included for completeness and for the rare
    English-titled row, but is expected to read near-zero for most rows: `_score` matches
    ENGLISH `query_terms` against the title, and `query_terms_i18n.py` carries no Lao
    vocabulary today (unlike CN/IN/MN) — a known, accepted bias recorded rather than papered
    over, the same call `adapter_timor.py` makes for Portuguese titles.
    """
    base = _CATEGORY_WEIGHT.get(category.strip().lstrip("- ").strip(), _DEFAULT_CATEGORY_WEIGHT)
    year_bonus = 0.0
    m = _DATE_RE.search(date_text or "")
    if m:
        year = int(m.group(3))
        if _YEAR_MIN <= year <= _YEAR_MAX:
            year_bonus = 0.08 * max(0.0, min(1.0, (year - _YEAR_MIN) / (_YEAR_MAX - _YEAR_MIN)))
    topic = portal.title_relevance(title, indicators, economy="LA")
    # `base` is scaled for the same reason `adapter_thailand._relevance` scales its own: a
    # ກົດໝາຍ (Law) weighs 0.85 against a 0.99 cap, so every Law in the gazette tied and the
    # ordering fell back to the crawl's page order. The type still separates a Law from an
    # Order; it no longer decides the whole ranking on its own.
    return round(min(0.99, max(0.05, 0.60 * base + year_bonus + 0.45 * topic)), 4)


def search_la_gazette(client, src: dict, query: str, economy: Economy, indicators: list,
                       log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    `query` is ignored — see the module docstring's "WHY `search_la_gazette` IGNORES `query`"
    section; this portal has no free-text search of its own. Walks `Document_page` 1.. up to
    `_MAX_PAGES`, stopping early at the first page that adds no row this call has not already
    seen — the same termination rule `portal_strategies.paginated_index` uses, applied here by
    hand because the generic helper cannot also recover the real (sibling-cell) title (see the
    module docstring for why the generic helper is not called directly).

    Each `DiscoveredDoc.source_url` is the row's own PDF link when the row has one (almost
    every row does — the Lao-language PDF column, verified live 2026-09-08), falling back to
    the `site/display` detail page only for the rare row with neither PDF column populated, so
    a document is never silently dropped for lacking a PDF.
    """
    portal_name = src.get("name", "Lao Official Gazette")
    out: list[DiscoveredDoc] = []
    seen_detail: set[str] = set()
    seen_doc_ids: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        url = _LIST_URL.format(page=page)
        resp = portal.portal_get(client, url, log)
        if resp is None:
            log(f"[la_gazette] pagination stopped at page {page}: no response")
            break
        try:
            rows = _rows(resp.text, url)
        except Exception as exc:                      # noqa: BLE001 — one bad page is not fatal
            log(f"[la_gazette] could not parse page {page}: {type(exc).__name__}: {exc}")
            rows = []
        added = 0
        for detail_url, title, pdf_url, category, date_text in rows:
            if detail_url in seen_detail:
                continue
            seen_detail.add(detail_url)
            added += 1
            target = pdf_url or detail_url
            score = _relevance(category, title, date_text, indicators)
            doc = portal.make_doc(economy, target, title or target, portal_name, score=score)
            if doc.doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc.doc_id)
            out.append(doc)
        log(f"[la_gazette] page {page}: +{added} rows ({len(out)} total)")
        if added == 0:
            log(f"[la_gazette] pagination stopped at page {page}: no new rows")
            break
        if client is not None and page < _MAX_PAGES:
            time.sleep(settings.crawl_delay_seconds)
    return out


portal.register("la_gazette", search_la_gazette, enumerates_portal=True)
