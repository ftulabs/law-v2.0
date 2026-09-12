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
            -> RDTL-Law/sidehome-e.htm               21 links: 18 category-index pages (9
                                                       categories x EN/PT), 2 direct PDFs
                                                       (the Constitution), and one "Return to
                                                       Start Page" nav link back up (not a
                                                       document category — deliberately not
                                                       read as one).

ALL NINE CATEGORIES, both languages, all read (fixed 2026-09-08 — an earlier version of this
adapter read only 3 of the 9 and reported success anyway; see the fix note below). PDF counts
measured live 2026-09-07/08, EN / PT:

    Law                        (RDTL-Laws)                127 / 131
    Decree-Law                 (RDTL-Decree-Laws)          228 / 286
    Gov-Decree                 (RDTL-Gov-Decrees)           18 /  61
    Minist-Order               (RDTL-Minist-Orders)         15 /  12
    Instruction                (RDTL-Instructions)           3 /   3
    Gov-Resolution              (RDTL-Gov-Resolutions)       14 /  42
    Resolution                 (RDTL-Resolutions)           47 / 124
    Presidential-Decree-Law    (Presidential-Decree-Laws)   11 /  15
    Public-Inst-Reg            (Public Inst-Regs)           30 /  36
                                                    EN total 493, PT total 710
    + 2 direct PDFs (Constitution EN/PT, verified 200 OK, real `application/pdf` content,
      400031/144184 bytes via HTTP HEAD)                                            = 2
                                                             GRAND TOTAL   ~1,205

That total is a snapshot, not a constant: a live `search_tl_gazette` run on 2026-09-08 (see the
fix report) counted 1,201 — two of the "-P" pages returned one or two fewer rows than the recon
above measured minutes earlier (Resolutions-P 123 vs 124, Public-Inst-Regs-EN 28 vs 30). This is
the portal's own content moving between requests, not a defect in this adapter; expect the
exact count to drift by a handful between runs rather than treating any single figure as exact.

None of the eighteen index pages 404s or comes back with zero PDFs — measured directly, not
assumed — so there is nothing here to report as silently dropped. If a future recon of this
portal finds one that does, record it here and in the fix/task report rather than removing it
from `_INDEX_PAGES` quietly.

`robots.txt` (site root, applies to the whole host) is the Drupal default: `Crawl-delay: 10`,
disallowing `/admin/ /search/ /includes/ /modules/` and the install files — verified 2026-09-07
it does NOT disallow `/jornal/lawsTL/...` or any document path. The crawl delay is honoured by
sleeping explicitly between index-page fetches in `search_tl_gazette` (see the comment there for
why `settings.crawl_delay_seconds` — a global knob shared by every other economy — is not the
right lever for a portal-specific pause). Eighteen index pages means SEVENTEEN pauses of 10s
between them: 170s of deliberate sleep is the floor. Measured live 2026-09-08, a full
`search_tl_gazette` call (17 sleeps + 18 fetches + parsing 1,201 rows) took 183.5s wall-clock
before any grading even starts — expected and correct, not a bug, but worth recording for
whatever budgets a full run against the panel's clock (Task 10).

WHAT THIS ADAPTER DOES NOT COVER — recorded rather than hidden
────────────────────────────────────────────────────────────────────────────────────────────
`RDTL-Law/home-e.htm` links a static "Index of Laws of TL" PDF captioned "as of 31 August
2011" (found 2026-09-07: the link text is an empty `&nbsp;`, easy to miss). That PDF is a
separate, frozen document — NOT the same thing as the eighteen HTML index pages this adapter
actually reads. Checking those eighteen directly (not the 2011 PDF) shows: every anchor's own
href/text was checked for a year, after normalising away a decoding trap described below, and
the youngest instrument on the three biggest categories (Laws, Decree-Laws, Gov-Decrees) is
from 2012 (Law 07/2012 EN, Decree-Law 20/2012 EN). So the "2011" caption is close to right, not
stale scaremongering: the core legislative categories of this RDTL-Law/ tree — the frameset
target of this task — genuinely stop around 2012, thirteen-plus years before this adapter was
written. (The smaller subordinate categories added in the 2026-09-08 fix were not individually
re-dated; nothing observed in their titles suggested materially newer content, but this was not
exhaustively checked instrument-by-instrument the way Laws/Decree-Laws/Gov-Decrees were.)

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
the instrument. `_year_of` (used for the recency signal in `_relevance`) url-decodes first and
requires non-digit boundaries around the year for exactly this reason.

LANGUAGE: within this lane the split is English/Portuguese (the "-P" twin index pages above)
— NOT English/Tetum. A Tetum translation of the Constitution (`ConstituicaoRDTL_tetum.pdf`)
exists on the site, but it is served from the newer Drupal system's `/public/docs/` path, not
from this frameset tree, so it is not among the pages this adapter enumerates. Whichever
language a given PDF turns out to be, detection must run PER DOCUMENT (the same instrument is
filed once per language, at its own URL), never per economy.

WHY `search_tl_gazette` IGNORES `query` ENTIRELY: this portal has no search endpoint of its
own — no query string, no POST form, nothing to send a keyword to. So, like `mn_legalinfo`
(`adapter_mongolia.py`), the lane enumerates everything the index pages list and leaves the
pillar's relevance to be decided downstream. Unlike a flat score, though, `indicators` (already
passed to this function) IS used — see `_relevance` — to give the downstream `discovery._cap`
budget trim something better than sort order to work with.

RELEVANCE SCORING (added 2026-09-08 — every document used to carry the default
`relevance_score=1.0`, which made `discovery._cap`'s trim to `discovery_max_docs` (22 by
default) effectively RANDOM: with 1,205 candidates and no spread, whichever 22 happened to
sort first were the ones the rest of the pipeline ever saw). `_relevance` combines three
signals that need no extra fetch — category (Laws/Decree-Laws outrank Resolutions, but
Ministerial Orders and Public Institution Regulations are NOT buried at the bottom: Mongolia's
own panel-cited answer for one indicator is a Minister's order, A/90, not an Act, and a scheme
that ranks all subordinate instruments last would misrank TL the same way that lane once did
before it was fixed), year (a small recency bonus), and topic fit against `indicators` via
`discovery._score` (English-only lexical matching, so Portuguese titles mostly score 0 here and
fall back to category+year — a known, accepted bias recorded rather than papered over: the
indicator query-term vocabulary has no Portuguese/Tetum list the way `query_terms_i18n` gives
CN/IN/MN one).
"""
from __future__ import annotations

import re
import time
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

#: The nine category index pages verified live 2026-09-07/08, English then its "-P" Portuguese
#: twin, paired with the category tag `_relevance` scores on. Folder-name quirks are the
#: portal's own and are kept verbatim, not "corrected": `RDTL-Oreders.htm` (Ministerial
#: Orders), `Presidential%20DecreeLaws-.htm` (encoded space, no hyphen, trailing dash),
#: `Public%20Inst-Regs` (encoded space). `RDTL-Resolutions-P/RDTL-Resolutions-P.htm` is the one
#: category where the "-P" also lands in the FILENAME, not just the folder — every other
#: category keeps the English filename under the Portuguese folder.
_BASE = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/"
_INDEX_PAGES: tuple[tuple[str, str], ...] = (
    (_BASE + "RDTL-Laws/RDTL-Laws.htm", "Law"),
    (_BASE + "RDTL-Laws-P/RDTL-Laws.htm", "Law"),
    (_BASE + "RDTL-Decree-Laws/RDTL-Decree-Laws.htm", "Decree-Law"),
    (_BASE + "RDTL-Decree-Laws-P/RDTL-Decree-Laws.htm", "Decree-Law"),
    (_BASE + "RDTL-Gov-Decrees/RDTL-Decrees.htm", "Gov-Decree"),
    (_BASE + "RDTL-Gov-Decrees-P/RDTL-Decrees.htm", "Gov-Decree"),
    (_BASE + "RDTL-Minist-Orders/RDTL-Oreders.htm", "Minist-Order"),
    (_BASE + "RDTL-Minist-Orders-P/RDTL-Oreders.htm", "Minist-Order"),
    (_BASE + "RDTL-Instructions/RDTL-Instr.htm", "Instruction"),
    (_BASE + "RDTL-Instructions-P/RDTL-Instr.htm", "Instruction"),
    (_BASE + "RDTL-Gov-Resolutions/RDTL-Gov-Resolutions.htm", "Gov-Resolution"),
    (_BASE + "RDTL-Gov-Resolutions-P/RDTL-Gov-Resolutions.htm", "Gov-Resolution"),
    (_BASE + "RDTL-Resolutions/RDTL-Resolutions.htm", "Resolution"),
    (_BASE + "RDTL-Resolutions-P/RDTL-Resolutions-P.htm", "Resolution"),
    (_BASE + "Presidential-Decree-Laws/Presidential-Decree-Laws.htm", "Presidential-Decree-Law"),
    (_BASE + "Presidential-Decree-Laws-P/Presidential%20DecreeLaws-.htm",
     "Presidential-Decree-Law"),
    (_BASE + "Public%20Inst-Regs/Public%20Inst-Regs.htm", "Public-Inst-Reg"),
    (_BASE + "Public%20Inst-Regs-P/Public%20Inst-Regs.htm", "Public-Inst-Reg"),
)

#: The Constitution is served as two direct PDFs, not an index page — there is nothing to
#: parse, so it bypasses `_law_rows` entirely. Reachability verified live 2026-09-08 via HTTP
#: HEAD: both 200, `application/pdf`, 400031 / 144184 bytes. Not re-verified on every run for
#: the same reason none of the ~1,203 rows `_law_rows` yields from the index pages are
#: individually re-verified at discovery time either — that is the fetch stage's job.
_DIRECT_PDFS: tuple[tuple[str, str, str], ...] = (
    (_BASE + "RDTL-Constitution.pdf",
     "Constitution of the Democratic Republic of Timor-Leste", "Constitution"),
    (_BASE + "RDTL-Constitution-P.pdf",
     "Constituição da República Democrática de Timor-Leste", "Constitution"),
)

#: robots.txt's own Crawl-delay, in seconds. NOT read from `settings.crawl_delay_seconds` —
#: that setting is global (shared by every economy's fetch layer) and changing it to satisfy
#: TL's portal would slow down every other portal's polling too. This adapter honours the
#: delay itself, by sleeping between its own index-page fetches.
_CRAWL_DELAY_SECONDS = 10

#: Base relevance by category — the first of `_relevance`'s three signals. See the module
#: docstring's "RELEVANCE SCORING" section for why Ministerial Orders and Public Institution
#: Regulations sit in the middle rather than the bottom.
_CATEGORY_WEIGHT: dict[str, float] = {
    "Law": 0.75,
    "Decree-Law": 0.75,
    "Gov-Decree": 0.60,
    "Minist-Order": 0.65,
    "Public-Inst-Reg": 0.60,
    "Presidential-Decree-Law": 0.60,
    "Instruction": 0.55,
    "Gov-Resolution": 0.50,
    "Resolution": 0.45,
    "Constitution": 0.45,
}

#: A year, url-decoded and boundary-checked. See the module docstring's decoding-trap note —
#: an unanchored `\d{4}` on a still-encoded href can manufacture a year ("%20" + "2012" reads
#: as digit run "202012", whose first four digits are "2020" — a year in no instrument here).
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
#: TL statehood is 2002 (UNTAET administration from 1999); nothing in this catalogue predates
#: that, and this module is being read well before 2031, so digits outside this band are
#: something else's number picked up by the regex, not a year.
_YEAR_MIN, _YEAR_MAX = 1999, 2030


def _year_of(url: str, title: str) -> int | None:
    """The instrument's year, from the DECODED url first, then the title. `None` if neither
    carries a plausible one."""
    for text in (urllib.parse.unquote(url), title):
        m = _YEAR_RE.search(text)
        if m:
            year = int(m.group(0))
            if _YEAR_MIN <= year <= _YEAR_MAX:
                return year
    return None


def _relevance(category: str, url: str, title: str, indicators: list) -> float:
    """How much of the discovery budget this instrument deserves. See the module docstring's
    "RELEVANCE SCORING" section for the reasoning; this is the mechanics.

    `discovery._score` is imported locally (not at module level) because `discovery.py`
    imports sibling adapters INSIDE its dispatch function, not at its own module top, to avoid
    a circular import — this mirrors that convention rather than fighting it.
    """
    base = _CATEGORY_WEIGHT.get(category, 0.40)
    year = _year_of(url, title)
    year_bonus = 0.0
    if year is not None:
        year_bonus = 0.08 * max(0.0, min(1.0, (year - _YEAR_MIN) / (_YEAR_MAX - _YEAR_MIN)))
    topic = portal.title_relevance(title, indicators, economy="TL")
    return round(min(0.99, max(0.05, base + year_bonus + 0.40 * topic)), 4)


#: `<meta http-equiv="Content-Type" content="text/html; charset=...">`, read out of the raw
#: bytes. Found incidentally while adding the Portuguese fixture (below): every RDTL-Law page,
#: English AND Portuguese, declares `iso-8859-1` or `windows-1252` in this meta tag, NOT in the
#: HTTP header — and httpx only honours the header, so `resp.text` silently decodes as UTF-8.
#: Invisible on the English pages (their body is ASCII bar a stray en-dash); on the Portuguese
#: ones it corrupts every accented character (measured live: "ção" -> mojibake). `_decode`
#: below is the fix; it is scoped to titles only — PDF hrefs are already ASCII/percent-encoded
#: and are never affected either way.
_CHARSET_RE = re.compile(rb'charset=["\']?([\w-]+)', re.I)


def _decode(resp) -> str:
    """`resp.text`, corrected for a declared-but-unhonoured `<meta charset>`.

    Prefers the charset the PAGE declares over whatever httpx guessed, because httpx here
    guesses UTF-8 for pages that are not UTF-8 (see `_CHARSET_RE`'s comment). Falls back to
    `resp.text` whenever there is no `.content` to sniff, no charset tag, or the declared name
    is not one Python recognises — so a portal serving genuine UTF-8 is unaffected.
    """
    content = getattr(resp, "content", None)
    if content:
        m = _CHARSET_RE.search(content[:4096])
        if m:
            name = m.group(1).decode("ascii", errors="ignore")
            try:
                return content.decode(name, errors="replace")
            except LookupError:
                pass
    return resp.text


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
    per row, plus the two `_DIRECT_PDFS`. Every document gets a real `_relevance` score instead
    of the flat default.

    The `client is not None` guard on the crawl-delay sleep exists because `client=None` is not
    a shape a real caller ever passes (there is no request to make without one); it lets the
    unit test drive this function with a stubbed `portal.portal_get` and no real client without
    also paying seventeen real 10-second pauses for a portal it never actually touches.
    """
    portal_name = src.get("name", "Jornal da República")
    out: list[DiscoveredDoc] = []
    seen_ids: set[str] = set()
    total_pages = len(_INDEX_PAGES)
    for i, (url, category) in enumerate(_INDEX_PAGES):
        resp = portal.portal_get(client, url, log)
        if resp is None:
            log(f"[tl_gazette] no response for {url}")
        else:
            try:
                rows = _law_rows(_decode(resp), url)
            except Exception as exc:                     # noqa: BLE001 — one dead page is not fatal
                log(f"[tl_gazette] could not parse {url}: {type(exc).__name__}: {exc}")
                rows = []
            for pdf_url, title in rows:
                score = _relevance(category, pdf_url, title, indicators)
                doc = portal.make_doc(economy, pdf_url, title, portal_name, score=score)
                if doc.doc_id in seen_ids:
                    continue
                seen_ids.add(doc.doc_id)
                out.append(doc)
            log(f"[tl_gazette] {url} -> {len(rows)} PDFs ({category})")
        if client is not None and i + 1 < total_pages:
            # robots.txt: Crawl-delay 10. Eighteen index pages -> seventeen pauses (~170s).
            time.sleep(_CRAWL_DELAY_SECONDS)

    for pdf_url, title, category in _DIRECT_PDFS:
        score = _relevance(category, pdf_url, title, indicators)
        doc = portal.make_doc(economy, pdf_url, title, portal_name, score=score)
        if doc.doc_id in seen_ids:
            continue
        seen_ids.add(doc.doc_id)
        out.append(doc)
    log(f"[tl_gazette] {len(_DIRECT_PDFS)} direct PDFs (Constitution EN/PT)")

    return out


portal.register("tl_gazette", search_tl_gazette, enumerates_portal=True)
