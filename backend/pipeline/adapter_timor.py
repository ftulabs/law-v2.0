"""Timor-Leste — the Ministry of Justice's 1990s frameset tree of gazette laws.

TL is on the panel's published list of eight and carries the difficulty bonus, and until this
adapter it had no lane at all: every document had to arrive through a web search, and every
engine answered that search with HTTP 403 (measured against the pre-existing `websearch` lane
before this adapter existed).

The portal turns out to be the simplest of the eleven economies in this phase: static HTML,
no JS, no WAF, no API. The route, verified live 2026-09-07:

    https://mj.gov.tl/jornal/lawsTL/index-e.htm      frameset: sidehome-e.htm + home-e.htm
      -> sidehome-e.htm                              nav: 6 category links
          RDTL-Law/index-e.htm                       another frameset
            -> RDTL-Law/sidehome-e.htm               21 links (19 index pages + 2 direct PDFs:
                                                       RDTL-Constitution.pdf / -P.pdf)
                RDTL-Laws/RDTL-Laws.htm               127 PDFs, Law of the National Parliament
                RDTL-Decree-Laws/RDTL-Decree-Laws.htm 228 PDFs, Government Decree-Laws
                RDTL-Gov-Decrees/RDTL-Decrees.htm     18 PDFs, Government Decrees
                (each has a "-P" twin under the same folder name: the Portuguese edition,
                 e.g. RDTL-Laws-P/RDTL-Laws.htm — 131/286/61 PDFs respectively, measured
                 2026-09-07; Portuguese indexes are LARGER than the English ones, not smaller)

`robots.txt` (site root, applies to the whole host) is the Drupal default: `Crawl-delay: 10`,
disallowing `/admin/ /search/ /includes/ /modules/` and the install files — verified 2026-09-07
it does NOT disallow `/jornal/lawsTL/...` or any document path. The crawl delay is honoured by
sleeping explicitly between index-page fetches in `search_tl_gazette` (see the comment there for
why `settings.crawl_delay_seconds` — a global knob shared by every other economy — is not the
right lever for a portal-specific pause).

WHAT THIS ADAPTER DOES NOT COVER — recorded rather than hidden
────────────────────────────────────────────────────────────────────────────────────────────
`RDTL-Law/home-e.htm` links a static "Index of Laws of TL" PDF captioned "as of 31 August
2011" (found 2026-09-07: the link text is an empty `&nbsp;`, easy to miss). That PDF is a
separate, frozen document — NOT the same thing as the six HTML index pages this adapter
actually reads. Checking those six directly (not the 2011 PDF) shows: every anchor's own
href/text was checked for a (19|20)dd year, after normalising away a decoding trap described
below, and the youngest instrument on ANY of the six pages is from 2012 (Law 07/2012 EN,
Decree-Law 20/2012 EN; the Portuguese twins run to the same or a slightly later point). So the
"2011" caption is close to right, not stale scaremongering: this whole RDTL-Law/ tree — the
frameset target of this task — genuinely stops in 2012, thirteen-plus years before this
adapter was written. This lane's coverage year range is **2001-2012**.

That is NOT the limit of what mj.gov.tl publishes. The site also runs a separate, current
Drupal CMS at `/jornal/` (node URLs like `?q=node/7068`), and at least one of its nodes links
gazette editions filed under `/jornal/public/docs/2026/serie_2/...` — i.e. material from THIS
YEAR. That system is a different portal shape (node-listing, not a static index-per-category)
and is out of this task's scope (the brief names "the static frameset tree" specifically); it
is recorded here so nobody mistakes "TL has a lane" for "TL's statute book is covered past
2012" — it is not, by this adapter alone.

DECODING TRAP FOUND DURING RECON, for the next person who touches year-extraction here: the
naive `re.search(r"(\\d{4})", href)` the brief's own recon script uses can manufacture a
phantom year. `Law%20no.%205%20-%202012%20of%2029...pdf` has `%20` (percent-encoded space)
sitting directly against `2012` with no separator, so the encoded string contains the digit
run `202012`, and an unanchored 4-digit search reports "2020" — a year that appears nowhere in
the instrument. `_law_rows` never extracts a year at all (the tests do that from the URL text
`Law-YYYY-NN` for the OLDEST filename convention only), but a future date-aware version of
this adapter must url-decode first and require non-digit boundaries around the year, or it
will silently misdate the newer, space-separated filenames ("Decree Law 49-2011.pdf" etc.).

LANGUAGE: within this lane the split is English/Portuguese only (the "-P" twin index pages
above) — NOT English/Tetum. A Tetum translation of the Constitution
(`ConstituicaoRDTL_tetum.pdf`) exists on the site, but it is served from the newer Drupal
system's `/public/docs/` path, not from this frameset tree, so it is not among the pages this
adapter enumerates. Whichever language a given PDF turns out to be, detection must run PER
DOCUMENT (the same instrument is filed once per language, at its own URL), never per economy.

WHY `search_tl_gazette` IGNORES `query` ENTIRELY: this portal has no search endpoint of its
own — no query string, no POST form, nothing to send a keyword to. So, like `mn_legalinfo`
(`adapter_mongolia.py`), the lane enumerates everything the six index pages list and leaves
the pillar's relevance to be decided downstream by retrieval, which already has to rank a
whole corpus rather than trust a portal's own search ranking.
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

#: The three English category indexes verified live 2026-09-07, plus their "-P" Portuguese
#: twins (same folder pattern, different leaf name: RDTL-Laws-P not RDTL-Laws/-P). All six
#: sit under the same base and were confirmed reachable (HTTP 200) during recon.
_BASE = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/"
_INDEX_PAGES: tuple[str, ...] = (
    _BASE + "RDTL-Laws/RDTL-Laws.htm",                        # 127 PDFs, EN
    _BASE + "RDTL-Laws-P/RDTL-Laws.htm",                      # 131 PDFs, PT
    _BASE + "RDTL-Decree-Laws/RDTL-Decree-Laws.htm",          # 228 PDFs, EN
    _BASE + "RDTL-Decree-Laws-P/RDTL-Decree-Laws.htm",        # 286 PDFs, PT
    _BASE + "RDTL-Gov-Decrees/RDTL-Decrees.htm",              # 18 PDFs, EN
    _BASE + "RDTL-Gov-Decrees-P/RDTL-Decrees.htm",            # 61 PDFs, PT
)

#: robots.txt's own Crawl-delay, in seconds. NOT read from `settings.crawl_delay_seconds` —
#: that setting is global (shared by every economy's fetch layer) and changing it to satisfy
#: TL's portal would slow down every other portal's polling too. This adapter honours the
#: delay itself, by sleeping between its own index-page fetches.
_CRAWL_DELAY_SECONDS = 10


def _law_rows(html: str, base_url: str) -> list[tuple[str, str]]:
    """Every (absolute PDF url, title) pair a category index page lists.

    Pure and side-effect free, so the test suite can drive it against a saved fixture with no
    network. `base_url` is required because the index uses RELATIVE hrefs (`Law-2002-01.pdf`);
    resolving against the page that served them is the only way to get a fetchable URL.

    The index is a table: the cell holding the PDF link carries only the instrument's number
    ("05/2012"), and the real title ("Strike Law") sits in the NEXT `<td>` of the same row —
    verified by reading the raw fixture HTML directly, not assumed. A citation reading just the
    law number, or the filename, is not a Law Name, so this walks to that sibling cell for the
    title and falls back to the anchor's own text only if the row shape is unexpected.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    rows: list[tuple[str, str]] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if ".pdf" not in href.lower():
            continue
        url = urllib.parse.urljoin(base_url, href)
        if url in seen:
            continue
        title = ""
        td = a.find_parent("td")
        if td is not None:
            sib = td.find_next_sibling("td")
            if sib is not None:
                title = " ".join(sib.get_text(" ", strip=True).split())
        if not title:
            title = " ".join(a.get_text(" ", strip=True).split())
        seen.add(url)
        rows.append((url, title))
    return rows


def search_tl_gazette(client, src: dict, query: str, economy: Economy, indicators: list,
                       log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the `PortalEnumerator` signature `discovery` dispatches on.

    `query` is deliberately unused (see the module docstring: this portal has no search of its
    own). Fetches each of `_INDEX_PAGES` through `portal.portal_get` — which already checks
    robots before every request — parses it with `_law_rows`, and returns one `DiscoveredDoc`
    per row.

    The `client is not None` guard on the crawl-delay sleep exists because `client=None` is not
    a shape a real caller ever passes (there is no request to make without one); it lets the
    unit test drive this function with a stubbed `portal.portal_get` and no real client without
    also paying five real 10-second pauses for a portal it never actually touches.
    """
    portal_name = src.get("name", "Jornal da República")
    out: list[DiscoveredDoc] = []
    seen_ids: set[str] = set()
    for i, url in enumerate(_INDEX_PAGES):
        resp = portal.portal_get(client, url, log)
        if resp is None:
            log(f"[tl_gazette] no response for {url}")
        else:
            try:
                rows = _law_rows(resp.text, url)
            except Exception as exc:                     # noqa: BLE001 — one dead page is not fatal
                log(f"[tl_gazette] could not parse {url}: {type(exc).__name__}: {exc}")
                rows = []
            for pdf_url, title in rows:
                doc = portal.make_doc(economy, pdf_url, title, portal_name)
                if doc.doc_id in seen_ids:
                    continue
                seen_ids.add(doc.doc_id)
                out.append(doc)
            log(f"[tl_gazette] {url} -> {len(rows)} PDFs")
        if client is not None and i + 1 < len(_INDEX_PAGES):
            # robots.txt: Crawl-delay 10. Six index pages -> five pauses between them.
            time.sleep(_CRAWL_DELAY_SECONDS)
    return out


portal.register("tl_gazette", search_tl_gazette)
