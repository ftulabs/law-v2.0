r"""Thailand — law.go.th's own REST API, recovered from its published JS bundle.

`law.go.th` is a React single-page app whose data comes from a plain JSON REST API, not from
scanned gazette PDFs: no PDF, no OCR, no scan. (`data/sources.yaml` used to call Thailand "the
OCR-heavy lane"; the superseded `krisdika.go.th` entry is kept there for the record.)

ROUTE — recovered from the app's own published static bundle
(`https://www.law.go.th/static/js/main.7a41c7a0.js`, the JS every visitor's browser downloads;
its API class is `nj`, whose methods are quoted below), not from defeating any protection:

    base    https://apig.law.go.th/
    header  x-api-key: <public bundle constant, see data/sources.yaml>
    POST    dga-user-service-phase2/law/searchResult   TITLE / FULL-TEXT search   (PASS 1)
    GET     dga-user-service-phase2/law/detail/{table_of_law_id}   per-มาตรา items (PASS 2)
    POST    dga-user-service-phase2/law            browse feed, `hirachy` filter  (fallback)

`apig.law.go.th` is an AWS API Gateway; an unauthenticated request to a route that does not
exist answers `{"message":"Missing Authentication Token"}` — route-not-found, not a refusal.
`robots.allowed()` was checked LIVE against both hosts with the project's own
`crawl_user_agent` (2026-09-07): `www.law.go.th/robots.txt` is a 403 WAF page and
`apig.law.go.th/robots.txt` the Gateway's 403 — `robots._fetch` treats any 4xx as "no rules
published" per RFC 9309, so `robots.allowed()` returns `(True, "")` for both, confirmed by
calling it rather than assumed from the raw status codes.

WHY THIS FILE WAS REWRITTEN (2026-09-26). A live pillar run on 2026-09-25 found 22 documents,
of which 20 were irrelevant, in 7-11 minutes, and every provision it produced was cited as a
whole document or a "(passage k of N)" block — never "มาตรา 28". Both had one root cause each,
and neither was the one the previous version of this docstring recorded.

  1. IRRELEVANT DISCOVERY. The previous primary pass fetched the whole Act tier
     (`{"hirachy": 1}`, 1,114 rows) and DROPPED every row whose `content_all` was empty. Measured
     live 2026-09-26: **19 of the 1,114 Act rows carry `content_all`** — 1.7%. The Computer-
     Related Crime Act, the Accounting Act, the Criminal Procedure Code, the National
     Intelligence Act, the Credit Information Act, the Telecommunications Business Act and the
     PDPA's own principal row are all among the 98% dropped. The 22 slots were therefore filled
     by whatever happened to carry text: the 19 survivors (the Nakhon Sawan Administrative
     Court Act, the Cheque Offences Act …) plus the secondary browse walk's newest-first
     Notifications. The browse walk was also the wall-time: 60 pages x (request + the 2 s
     politeness gap), then a fetch-cache seed — one full rewrite of the cache index — for each
     of the ~700 documents it produced, when discovery keeps 22.

     `law/searchResult` was recorded here as "400s on every payload shape tried". Its shape is
     in the same bundle (`nj.getSearchResult` is called with `{type:null, agency:null,
     hirachy:null, searchType, searchText, size, page}`), and it works — verified live
     2026-09-26: `searchType: 1` searches law TITLES across all 11,406 rows ("ข้อมูลเครดิต" -> 11
     rows, one family, the Credit Information Business Act), `searchType: 2` searches the
     `content_all` BODY ("ข้อมูลส่วนบุคคลไปยังต่างประเทศ" -> the PDPA and a Bank of Thailand IT-
     outsourcing notification), `searchType: 3` answers 400. So this adapter now SEARCHES, with
     pillar vocabulary in Thai (`_TITLE_TERMS` / `_BODY_TERMS`), instead of walking the feed.

  2. NO ARTICLE-LEVEL CITATIONS. `content_all` is one newline-free string, and the headings of
     the ORIGINAL articles are not in it at all — the PDPA row (table_of_law_id 382) opens
     "พระราชบัญญัตินี้เรียกว่า …" with no "มาตรา ๑" in front of it; only amendment-inserted
     articles carry a marker. No splitter, however clever, can recover a number the text does
     not contain. The DETAIL endpoint does contain it: `rows[i].content_list_process` is the
     statute as a list of structured items, `{content_type: "มาตรา", content_number: "28",
     content_desc: "<p>…</p>", seq}` — measured 2026-09-26: PDPA 94-96 มาตรา items (both of
     its table ids), Cybersecurity Act 83, Computer-Related Crime Act 38, Criminal Procedure
     Code up to 364. `_articles_text` rebuilds the statute with ONE ARTICLE PER LINE, each
     opening with its มาตรา heading, which is exactly what `extraction.ARTICLE_PATTERNS
     [Economy.TH]` (line-anchored so it never fires on a "ตามมาตรา ๗" cross-reference) was
     written to split. No change to extraction.py was needed.

     THE NUMBER IS ALWAYS THE SOURCE'S. Where `content_desc` already opens with its heading
     ("มาตรา ๒๘ ในกรณีที่…", the 8668 representation) the text is used verbatim. Where it does
     not (the 382 representation stores the heading only in `content_number`), the line is
     prefixed "มาตรา {content_number}" — the portal's own number for that item, never a
     counter, never inferred from position. An item with no number is not given one.

WHAT IS NOT CARRIED OVER from `content_list_process`, and why:
  * structural headings (หมวด chapter, ส่วน part, บทเฉพาะกาล transitional) — they carry a title
    and no rule, and, placed between articles, they would be glued onto the END of the previous
    article's verbatim snippet (the same reason extraction does not split Chinese 章/节);
  * everything after the last article (หมายเหตุ the enactment note, ผู้รับสนองพระบรมราชโองการ the
    countersignature) — same reason, onto the last article;
  * an appended AMENDING act. The detail row the list endpoint points at (e.g. the Computer-
    Related Crime Act's law_id 19250) carries the amending act's own ชื่อกฎหมาย and its
    transitional มาตรา 2, 20, 21 after the principal's มาตรา 31. Kept, they would produce a
    second "มาตรา ๒" under the principal's name — a citation to the wrong instrument. Reading
    stops at a second ชื่อกฎหมาย item.

A document whose detail carries NO มาตรา item (a Notification numbers its clauses "ข้อ", or the
detail is empty) falls back to the row's own `content_all`, unchanged — the pre-2026-09-26
behaviour; one with no text anywhere is emitted as its Royal Gazette PDF (`announce_url`) when
it has one, and dropped otherwise rather than emitted empty.

RANKING — `_family_score`, per LAW FAMILY rather than per row. The search answers one row per
VERSION: the Criminal Procedure Code alone is 77 rows under table_of_law_id 9280, most titled
"พระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายวิธีพิจารณาความอาญา (ฉบับที่ N)". Rows are grouped by
`table_of_law_id` and the family is named by its principal title (the one that is not an
"แก้ไขเพิ่มเติม" amendment and carries no "(ฉบับที่ N)"). Signals, all from the search rows:
  * which of the run's pillar terms the principal TITLE carries, and whether it carries it
    DIRECTLY — "พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร …" names the Revenue Code only as the
    Act it is issued under (`_REFERENCE_MARKERS`), and such a title is not ABOUT the topic;
  * how much of the title's core the term covers — a tie-break that puts the Criminal Procedure
    Code (core = the term) above the District Courts Act that also mentions criminal procedure;
  * body-search hits (`_BODY_TERMS`) — how a Notification with no topical title is found;
  * the instrument type (`_HIRACHY_WEIGHT`) as a prior, not the answer;
  * a family whose only titles are amendments is penalised, one titled "(ยกเลิก)" (repealed)
    is dropped.
NO LAW IS NAMED ANYWHERE IN THIS FILE AS AN ANSWER. `_TITLE_TERMS` are subject-matter words a
relevant law's title is drafted with — personal data, cybersecurity, computer, credit
information, criminal procedure, accounting — the same kind of vocabulary
`rdtii/keywords.py` holds in English ("criminal procedure code", "companies act"). A
jurisdiction without such a law matches nothing.

WALL TIME. Discovery keeps `settings.discovery_max_docs` (22) documents, so only that many
detail pages are requested, and each rebuilt text is kept for `fetch_ttl_hours` under
`cache/_th_articles/` so the second pillar of a run re-requests none of them. Measured live
2026-09-26 (adapter call only, 2 s politeness gap kept): 88 s for pillar 6 and 124-129 s for
pillar 7 with an empty article cache, 26-41 s with it warm — against 7-11 min on 2026-09-25.

KNOWN LIMIT, not fixed here: an article inserted by amendment as "มาตรา ๗ ทวิ" (bis) is split
correctly but LABELLED "มาตรา ๗", because `extraction._ARTICLE_RE_TH` captures digits and an
optional "/N" but not the ทวิ/ตรี/จัตวา suffix — two provisions then share a label (measured: 3
in the District Courts Act, 2 in the Revenue Code). The fix is one optional group in that regex,
in extraction.py, which this change deliberately did not touch.

`source_url` is still the human-openable `www.law.go.th/DetailLawPage?table_of_law_id=<id>`
(the app's own router path and its own "share this law" link), never `apig.law.go.th`, which
answers only with the key header. That page is a bare Create-React-App shell (`<div
id="root">`, 1,256 bytes, which `ocr.is_js_app_shell` does NOT recognise), so fetching it would
yield an empty "(document)" block; the adapter instead SEEDS the fetch cache for that URL
(`fetch.seed_cache`, as `adapter_india.py` does) and the orchestrator's ordinary
`fetch_to_cache` gets a cache hit. `DiscoveredDoc.raw_text` is not used: the orchestrator's
fetch stage never reads it.

CHARACTER ENCODING: the API sends `application/json; charset=utf-8` and httpx decodes it as
such; Thai titles round-trip correctly (verified 2026-09-07).
"""
from __future__ import annotations

import html as _html
import json
import re
import time
from pathlib import Path
from typing import Callable

from ..config import settings
from ..schemas import DiscoveredDoc, DocFormat, Economy
from . import portal, robots

Log = Callable[[str], None]

# ── vocabulary ──────────────────────────────────────────────────────────────────────────────
#
# Title terms per pillar. Each is a phrase a RELEVANT law's own title is drafted with, keyed to
# the indicator that needs it; every one was checked live 2026-09-26 against `searchType: 1`
# and returns a small, topical result set (counts are rows, i.e. versions, not laws). A term
# that is merely the Act a routine instrument is "issued under" is caught by
# `_REFERENCE_MARKERS`, not by leaving the term out.
_TITLE_TERMS: dict[int, tuple[str, ...]] = {
    6: (
        "ข้อมูลส่วนบุคคล",            # personal data — 6.1-6.4 (3 rows)
        "ความมั่นคงปลอดภัยไซเบอร์",    # cybersecurity — 6.3 infrastructure duties (11)
        "ธุรกรรมทางอิเล็กทรอนิกส์",     # electronic transactions — 6.2/6.3 (12)
        "โทรคมนาคม",                 # telecommunications — 6.2/6.3 licensing (28)
        "ข้อมูลเครดิต",               # credit information — 6.1 (11)
        "ระบบการชำระเงิน",            # payment systems — 6.1/6.2 (11)
        "คอมพิวเตอร์",                # computer — 6.2 traffic-data localisation (20)
        # NOT "สถาบันการเงิน" (financial institutions): tried 2026-09-26, it put nine
        # bail-out and loan-guarantee Emergency Decrees of 1997-2015 into the pillar-6 top 22.
        # The one financial-sector instrument that matters here — a Bank of Thailand
        # notification on outsourcing IT abroad — is found by its BODY instead (_BODY_TERMS).
    ),
    7: (
        "ข้อมูลส่วนบุคคล",            # personal data — 7.1, 7.4
        "ความมั่นคงปลอดภัยไซเบอร์",    # cybersecurity — 7.2
        "คอมพิวเตอร์",                # computer(-related crime) — 7.2, 7.3, 7.5
        "ธุรกรรมทางอิเล็กทรอนิกส์",     # electronic transactions — 7.1, 7.3
        "โทรคมนาคม",                 # telecommunications — 7.1, 7.2
        "ข้อมูลเครดิต",               # credit information — 7.1, 7.3
        "ข่าวกรอง",                  # intelligence — 7.5 (6)
        "วิธีพิจารณาความอาญา",         # criminal procedure — 7.5 (97)
        "สอบสวนคดีพิเศษ",             # special investigation — 7.5 (6)
        "ฟอกเงิน",                   # money laundering — 7.3 record keeping, 7.5 (19)
        "การบัญชี",                  # accounting — 7.3 retention (10)
        "ประมวลรัษฎากร",              # revenue code — 7.3 retention, 7.5 tax access
        "ข้อมูลข่าวสารของราชการ",      # official information — 7.5
    ),
}

# Body phrases, matched by `searchType: 2` against `content_all`. Operative wording, so they
# find an instrument whose TITLE says nothing about the topic — a Bank of Thailand
# notification on IT outsourcing is the measured example. Each was checked live 2026-09-26 to
# return a handful of rows, not hundreds ("เก็บรักษาข้อมูล" returned 58 and was left out).
_BODY_TERMS: dict[int, tuple[str, ...]] = {
    6: (
        "ข้อมูลส่วนบุคคลไปยังต่างประเทศ",   # personal data to a foreign country (2 rows)
        "ไว้ในประเทศไทย",                 # kept in Thailand (3 rows)
    ),
    7: (
        "เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล",  # data protection officer (1 row)
        "ข้อมูลจราจรทางคอมพิวเตอร์",        # computer traffic data (1 row)
    ),
}

#: A term after one of these names the PARENT Act an instrument is issued under or refers to,
#: not the instrument's own subject: "พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร …" (a Royal Decree
#: issued under the Revenue Code) is one of 1,634 rows a Revenue-Code search returns. "แห่ง"
#: alone is NOT a marker: "…ไซเบอร์แห่งชาติ" ("national") is part of a committee's own name.
_REFERENCE_MARKERS = ("ออกตามความใน", "ตามความใน", "ตามพระราชบัญญัติ", "ตามประมวล",
                      "แห่งพระราชบัญญัติ", "แห่งประมวล", "ตามกฎหมายว่าด้วย")

_AMENDING = re.compile(r"แก้ไขเพิ่มเติม|\(ฉบับที่\s*[๐-๙\d]+\)")
_REPEALED = re.compile(r"\(\s*ยกเลิก\s*\)")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

#: The portal's own `hirachy_of_law_id` codes, from `GET dga-user-service-phase2/law/master`
#: (verified live 2026-09-07 — the full list, not a guess).
_HIRACHY_WEIGHT: dict[int, float] = {
    1: 0.85,      # พระราชบัญญัติ — Act
    926: 0.85,    # พ.ร.บ.ประกอบรัฐธรรมนูญ — Organic Act
    883: 0.80,    # พระราชกำหนด — Emergency Decree (force of an Act)
    893: 0.85,    # ประมวลกฎหมาย — Code (the Criminal Procedure Code, the Revenue Code)
    889: 0.80,    # ประมวลรัษฎากร — Revenue Code
    887: 0.65,    # รัฐธรรมนูญ — Constitution
    884: 0.55,    # พระราชกฤษฎีกา — Royal Decree
    888: 0.50,    # กฎกระทรวง — Ministerial Regulation
    886: 0.40,    # ระเบียบ — Regulation
    885: 0.30,    # คำสั่ง — Order
    2: 0.35,      # ประกาศ — Notification (the panel cites several for 6.4 and 7.2)
}
_DEFAULT_HIRACHY_WEIGHT = 0.25

#: The Act-and-above tiers, used only by the FALLBACK walk (`_fetch_tier`) when the search
#: endpoint answers nothing at all. Totals measured live 2026-09-26: 1=1114, 926=4, 883=49,
#: 893=8, 889=0, 887=1.
_LEGISLATIVE_HIRACHY_TIERS: tuple[int, ...] = (1, 926, 883, 893, 889, 887)
#: `size=8000` answered in 14.7 s and `size=9000` timed out at least once (2026-09-08), so no
#: single request asks for more than this.
_TIER_FETCH_SIZE_CAP = 3000
#: Rows per search request. The widest term here ("ประมวลรัษฎากร") matches ~1,600 rows, almost
#: all of them Revenue Department notifications; the principal Code is among the first 300
#: (measured 2026-09-26), and ranking — not the request — decides what is kept.
_SEARCH_SIZE = 300
#: Bump when `_articles_text` changes what it writes, so a cached rebuild is not reused.
_ARTICLES_FORMAT = "a3"


def _detail_url(row: dict) -> str:
    """The human-openable `www.law.go.th` page for this row — NEVER `apig.law.go.th`.

    Keyed on `table_of_law_id` (what the app's router keys the detail route on) rather than
    `law_id`, which is a different id on the same row and would open another law's page.
    """
    tid = row.get("table_of_law_id") or row.get("law_id") or ""
    return f"https://www.law.go.th/DetailLawPage?table_of_law_id={tid}"


def _title(row: dict) -> str:
    # Titles arrive with a trailing "\n" on some rows ("…พ.ศ. 2562\n", measured on 8668).
    return re.sub(r"\s+", " ", row.get("law_name_og") or row.get("law_name_th")
                  or row.get("tableoflaw_name") or "").strip()


def _hirachy(row: dict) -> int | None:
    raw = row.get("hirachy_of_law_id")
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _iso_date(row: dict) -> str | None:
    """The row's own `effective_startdate`/`annouce_date`, date part only — never a guess."""
    for key in ("effective_startdate", "annouce_date"):
        raw = row.get(key) or ""
        if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
            return raw[:10]
    return None


def _core(title: str) -> str:
    """A title without its instrument-type word, its year and its edition number — what the
    law is ABOUT. "ประมวลกฎหมายวิธีพิจารณาความอาญา" -> "วิธีพิจารณาความอาญา"."""
    t = re.sub(r"พ\.\s*ศ\.\s*[๐-๙\d]{4}.*$", "", title)
    t = re.sub(r"\(ฉบับที่[^)]*\)", "", t)
    t = re.sub(r"^(พระราชบัญญัติ|พระราชกำหนด|ประมวลกฎหมาย|พระราชกฤษฎีกา|กฎกระทรวง|ประกาศ)",
               "", t.strip())
    t = re.sub(r"^(ว่าด้วย|การ)", "", t.strip())
    return re.sub(r"\s+", "", t)


def _direct(term: str, title: str) -> bool:
    """True when `term` names this title's OWN subject, not a parent Act it refers to."""
    at = title.find(term)
    if at < 0:
        return False
    marks = [title.find(m) for m in _REFERENCE_MARKERS if m in title]
    return not marks or at < min(marks)


def _principal(rows: list[dict]) -> dict:
    """The row that names the law itself rather than one of its amendments."""
    plain = [r for r in rows if not _AMENDING.search(_title(r))]
    pool = plain or rows
    return min(pool, key=lambda r: (len(_title(r)), -len(r.get("content_all") or "")))


def _family_score(rows: list[dict], title_terms, body_hits: int) -> float:
    """Relevance of one law family (all rows sharing a table_of_law_id) — see the module
    docstring's RANKING section for each signal."""
    head = _principal(rows)
    title = _title(head)
    prior = _HIRACHY_WEIGHT.get(_hirachy(head), _DEFAULT_HIRACHY_WEIGHT)
    hits = [t for t in title_terms if t in title]
    direct = [t for t in hits if _direct(t, title)]
    core = _core(title)
    coverage = max((min(1.0, len(t) / len(core)) for t in direct if core), default=0.0)
    title_sig = 1.0 if direct else (0.35 if hits else 0.0)
    # A body hit is an operative phrase ("…personal data to a foreign country") found in the
    # instrument's own text: at least as strong as a topical title, so it counts in the same
    # slot AND carries a bonus of its own. Without the bonus, measured 2026-09-26, the Bank of
    # Thailand's IT-outsourcing notification (body hit, no topical title, 0.4725) fell below
    # the pillar-6 cut behind payment-system notifications whose TITLES merely name the topic.
    body_sig = min(1.0, float(body_hits))
    score = (0.35 * prior + 0.35 * max(title_sig, body_sig) + 0.15 * coverage
             + 0.15 * body_sig)
    if not direct and not body_hits:
        score *= 0.5                     # reached only through a reference to another Act
    if _AMENDING.search(title):
        score *= 0.6                     # every title in the family is an amendment
    return round(min(0.99, max(0.01, score)), 4)


# ── the detail endpoint -> one article per line ─────────────────────────────────────────────

_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"^มาตรา[ \t]*[๐-๙\d]")
_SKIP_MID = ("หมวด", "ส่วน", "บทเฉพาะกาล", "ลักษณะ", "บรรพ")


def _plain(fragment: str) -> str:
    """HTML item text -> one line. Paragraphs join with a space, so no line of an article's
    BODY can ever start with "มาตรา" and be mistaken for a heading by the splitter."""
    text = _html.unescape(_TAG.sub(" ", fragment or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _articles_text(payload: dict, prefer_law_id=None) -> tuple[str, int]:
    """`law/detail/{id}` -> (text with one มาตรา per line, number of articles). ("", 0) when
    the detail carries no article items. Pure — the tests drive it on saved payloads.

    Row choice: the detail answers one row per stored VERSION (the Criminal Procedure Code:
    78 rows, 5 of the first 12 empty; the Revenue Code: 100). The row with the most articles
    wins, except that the row the search pointed at is kept when it has at least 80% as many —
    it is the portal's current version, and the others can be older ones. Measured 2026-09-26,
    the pointed-at row alone gave the Revenue Code 6 articles, when another version holds the
    Code.
    """
    rows = [r for r in (payload or {}).get("rows") or [] if isinstance(r, dict)]
    built = [(r, *_row_articles(r)) for r in rows]
    built = [b for b in built if b[2]]
    if not built:
        return "", 0
    best = max(built, key=lambda b: b[2])
    chosen = next((b for b in built if prefer_law_id is not None
                   and str(b[0].get("law_id")) == str(prefer_law_id)
                   and b[2] >= 0.8 * best[2]), best)
    return chosen[1], chosen[2]


#: Items that END an instrument inside one detail row. After them, articles can start again at
#: มาตรา ๑ — as a DIFFERENT instrument. See `_row_articles`.
_INSTRUMENT_END = ("ชื่อกฎหมาย", "ผู้รับสนองพระบรมราชโองการ", "ผู้มีอำนาจลงนาม")
#: What may stand before an instrument's first article: its title, the royal assent, the
#: preamble. Anything else there (a "สารบาญ" table of contents, measured on the Criminal
#: Procedure Code) is dropped.
_PREAMBLE = ("ชื่อกฎหมาย", "พระปรมาภิไธย", "คำปรารภ")


def _row_articles(row: dict) -> tuple[str, int]:
    """One detail row -> (text with one มาตรา per line, number of articles).

    ONE ROW CAN HOLD TWO INSTRUMENTS, each numbering from มาตรา ๑. Measured 2026-09-26: the
    Criminal Procedure Code's row opens with the five-article Act that PROMULGATES the Code
    (มาตรา ๑-๕, then its countersignature) and only then the Code (มาตรา ๑-…); the Computer-
    Related Crime Act's row closes with its amending act (a second ชื่อกฎหมาย, then that act's
    own มาตรา ๒, ๒๐, ๒๑). Concatenated, either yields two different "มาตรา ๑" under one law
    name — a citation to the wrong instrument. So the row is cut into instruments at each
    `_INSTRUMENT_END` item and the one with the most articles is kept: the Code, not the Act
    that brings it into force; the principal Act, not its amendment.
    """
    items = row.get("content_list_process") or row.get("content_list") or []
    items = sorted((it for it in items if isinstance(it, dict)),
                   key=lambda it: it.get("seq") or 0)

    parts: list[tuple[list[str], int]] = []
    lines: list[str] = []
    n = 0
    for it in items:
        kind = (it.get("content_type") or "").strip()
        body = _plain(it.get("content_desc") or "")
        if kind in _INSTRUMENT_END and n:
            parts.append((lines, n))     # this instrument is complete
            lines, n = [], 0
        if kind == "มาตรา":
            number = (it.get("content_number") or "").strip()
            if not body and not number:
                continue
            if _HEADING.match(body):
                line = body              # the source's own heading, verbatim
            elif number and number != "-":
                line = f"มาตรา {number} {body}".rstrip()
            else:
                continue                 # no number in the source -> none is invented
            lines.append(line)
            n += 1
            continue
        if n == 0:
            if body and kind in _PREAMBLE:
                lines.append(body)       # title, royal assent, preamble — before article 1
            continue
        # After the articles began: chapter/part headings (`_SKIP_MID`) carry a title and no
        # rule, and anything else would be glued onto the previous article's snippet — see
        # the module docstring. Neither is carried over.
    if n:
        parts.append((lines, n))
    if not parts:
        return "", 0
    best_lines, best_n = max(parts, key=lambda p: p[1])
    return "\n".join(best_lines), best_n


def _articles_cache(tid) -> Path:
    d = settings.cache_path / "_th_articles"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{tid}_{_ARTICLES_FORMAT}.json"


def _cached_articles(tid) -> tuple[str, int] | None:
    try:
        p = _articles_cache(tid)
        if not p.exists():
            return None
        if settings.fetch_ttl_hours > 0 and \
                time.time() - p.stat().st_mtime > settings.fetch_ttl_hours * 3600:
            return None
        blob = json.loads(p.read_text(encoding="utf-8"))
        return blob.get("text") or "", int(blob.get("articles") or 0)
    except Exception:                                  # noqa: BLE001 — a cache miss, no more
        return None


def _store_articles(tid, text: str, n: int) -> None:
    try:
        _articles_cache(tid).write_text(
            json.dumps({"text": text, "articles": n}, ensure_ascii=False), encoding="utf-8")
    except Exception:                                  # noqa: BLE001 — caching is best-effort
        pass


def _fetch_detail(client, api_base: str, headers: dict, tid, prefer_law_id,
                  log: Log) -> tuple[str, int, bool]:
    """(text, articles, whether the network was used). A failed request is not cached, so
    the next run retries it; an answered one is, articles or not."""
    cached = _cached_articles(tid)
    if cached is not None:
        return (*cached, False)
    try:
        resp = client.get(f"{api_base}/dga-user-service-phase2/law/detail/{tid}",
                          headers=headers, timeout=120)
    except Exception as exc:                          # noqa: BLE001 — one law is not the run
        log(f"[th_law_api] detail {tid}: {type(exc).__name__}: {exc}")
        return "", 0, True
    if resp.status_code != 200:
        log(f"[th_law_api] detail {tid} -> HTTP {resp.status_code}")
        return "", 0, True
    try:
        text, n = _articles_text(resp.json(), prefer_law_id)
    except Exception as exc:                          # noqa: BLE001
        log(f"[th_law_api] detail {tid}: unparsable ({type(exc).__name__})")
        return "", 0, True
    _store_articles(tid, text, n)
    return text, n, True


# ── candidate rows ──────────────────────────────────────────────────────────────────────────

def _search(client, api_base: str, headers: dict, term: str, search_type: int,
            log: Log) -> list[dict] | None:
    """One `searchResult` call. None on a transport/HTTP failure (so the caller can tell "the
    endpoint is down" from "no law matches")."""
    body = {"type": None, "agency": None, "hirachy": None, "searchType": search_type,
            "searchText": term, "size": _SEARCH_SIZE, "page": 1}
    try:
        resp = client.post(f"{api_base}/dga-user-service-phase2/law/searchResult",
                           headers=headers, json=body, timeout=60)
    except Exception as exc:                          # noqa: BLE001
        log(f"[th_law_api] search {term!r}: {type(exc).__name__}: {exc}")
        return None
    if resp.status_code != 200:
        log(f"[th_law_api] search {term!r} -> HTTP {resp.status_code}")
        return None
    try:
        rows = resp.json().get("rows") or []
    except Exception as exc:                          # noqa: BLE001
        log(f"[th_law_api] search {term!r}: unparsable JSON ({type(exc).__name__})")
        return None
    return [r for r in rows if isinstance(r, dict)]


def _fetch_tier(client, url: str, headers: dict, hirachy: int, log: Log) -> list[dict]:
    """Every row in one `hirachy` tier of the browse feed, in one atomic request (probe
    `total` at size=1, then fetch size=total). FALLBACK ONLY — see `search_th_law`."""
    try:
        probe = client.post(url, headers=headers,
                            json={"page": 1, "size": 1, "hirachy": hirachy}, timeout=60)
        if probe.status_code != 200:
            log(f"[th_law_api] hirachy={hirachy} probe -> HTTP {probe.status_code}")
            return []
        # `total` comes back as a STRING ("1113") — cast, or a str/int compare crashes.
        raw_total = probe.json().get("total")
        total = int(raw_total) if raw_total not in (None, "") else 0
    except Exception as exc:                          # noqa: BLE001
        log(f"[th_law_api] hirachy={hirachy} probe failed: {type(exc).__name__}: {exc}")
        return []
    if not total:
        return []
    try:
        resp = client.post(url, headers=headers,
                           json={"page": 1, "size": min(total, _TIER_FETCH_SIZE_CAP),
                                 "hirachy": hirachy}, timeout=120)
        if resp.status_code != 200:
            log(f"[th_law_api] hirachy={hirachy} fetch -> HTTP {resp.status_code}")
            return []
        return [r for r in resp.json().get("rows") or [] if isinstance(r, dict)]
    except Exception as exc:                          # noqa: BLE001
        log(f"[th_law_api] hirachy={hirachy} fetch failed: {type(exc).__name__}: {exc}")
        return []


def _pillars(indicators) -> list[int]:
    got = sorted({getattr(i, "pillar", None) for i in indicators or []} - {None})
    return [p for p in got if p in _TITLE_TERMS] or sorted(_TITLE_TERMS)


def rank_families(rows: list[dict], title_terms, body_hits: dict | None = None
                  ) -> list[tuple[float, list[dict]]]:
    """Group rows into law families and rank them, best first. Pure (tests drive it).

    Families that name the same law twice under different ids (the PDPA is 8668, titled
    "… พ.ศ. 2562", AND 382, "… พ.ศ. ๒๕๖๒") collapse to one, keeping both id lists in rank
    order so the caller can fall back to the second when the first has no article items.
    """
    body_hits = body_hits or {}
    fams: dict = {}
    for r in rows:
        tid = r.get("table_of_law_id") or r.get("law_id")
        if tid in (None, ""):
            continue
        fams.setdefault(tid, []).append(r)
    ranked = []
    for tid, fam in fams.items():
        title = _title(_principal(fam))
        if not title or _REPEALED.search(title):
            continue
        ranked.append((_family_score(fam, title_terms, body_hits.get(tid, 0)), fam))
    ranked.sort(key=lambda sf: sf[0], reverse=True)
    return ranked


def _same_law_key(title: str) -> str:
    return re.sub(r"\s+", "", title.translate(_THAI_DIGITS))


def search_th_law(client, src: dict, query: str, economy: Economy, indicators: list,
                  log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point (`PortalEnumerator` signature). `query` is unused: this adapter
    runs its own pillar vocabulary (`_TITLE_TERMS`/`_BODY_TERMS`) in one call, which is why it
    stays registered `enumerates_portal=True` — discovery must not call it once per term.

      PASS 1  search titles (and a few operative phrases in bodies) -> rows
      RANK    group rows into law families, score each (`rank_families`)
      PASS 2  for the top `discovery_max_docs` families only: `law/detail` -> one มาตรา per
              line (`_articles_text`), seeded into the fetch cache under the citable URL.
    If every search request fails, the Act-tier browse walk (`_fetch_tier`) supplies the
    candidate rows instead, ranked the same way.
    """
    api_base = (src.get("api_base") or "").rstrip("/")
    api_key = src.get("api_key")
    if not api_base or not api_key:
        log("[error] th_law_api: sources.yaml entry has no api_base/api_key — "
            "cannot query apig.law.go.th (see data/sources.yaml's TH law.go.th entry)")
        return []
    feed = f"{api_base}/dga-user-service-phase2/law"
    ok, why = robots.allowed(feed, settings.crawl_user_agent)
    if not ok:
        log(f"[th_law_api] robots refuses {feed} — {why}")
        return []
    headers = {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Origin": "https://www.law.go.th",
        "Referer": "https://www.law.go.th/",
    }
    portal_name = src.get("name", "law.go.th")
    pillars = _pillars(indicators)
    title_terms = list(dict.fromkeys(t for p in pillars for t in _TITLE_TERMS[p]))
    body_terms = list(dict.fromkeys(t for p in pillars for t in _BODY_TERMS.get(p, ())))

    def pause():
        if client is not None:
            time.sleep(settings.crawl_delay_seconds)

    rows: list[dict] = []
    body_hits: dict = {}
    answered = 0
    for term in title_terms:
        got = _search(client, api_base, headers, term, 1, log)
        if got is not None:
            answered += 1
            rows.extend(got)
            log(f"[th_law_api] title {term!r}: {len(got)} rows")
        pause()
    for term in body_terms:
        got = _search(client, api_base, headers, term, 2, log)
        if got is not None:
            answered += 1
            rows.extend(got)
            for tid in {r.get("table_of_law_id") for r in got}:
                body_hits[tid] = body_hits.get(tid, 0) + 1
            log(f"[th_law_api] body {term!r}: {len(got)} rows")
        pause()
    if not answered:
        log("[th_law_api] searchResult answered nothing — falling back to the Act-tier walk")
        for hirachy in _LEGISLATIVE_HIRACHY_TIERS:
            rows.extend(_fetch_tier(client, feed, headers, hirachy, log))
            pause()

    # The same law under several ids (see rank_families) is ONE candidate: its ids are tried in
    # rank order until one has article items, and only then does it fall back to content_all.
    laws: dict[str, list[tuple[float, list[dict]]]] = {}
    for score, fam in rank_families(rows, title_terms, body_hits):
        laws.setdefault(_same_law_key(_title(_principal(fam))), []).append((score, fam))

    budget = settings.discovery_max_docs
    out: list[DiscoveredDoc] = []
    for group in laws.values():
        if len(out) >= budget:
            break
        score = group[0][0]
        pick, text, n = None, "", 0
        for _s, fam in group:
            head = _principal(fam)
            tid = head.get("table_of_law_id") or head.get("law_id")
            text, n, used_network = _fetch_detail(client, api_base, headers, tid,
                                                  head.get("law_id"), log)
            if used_network:
                pause()
            if n:
                pick = (head, fam)
                break
        if pick is None:
            # No article items under any id: the longest content_all any of them carries,
            # unchanged (the pre-2026-09-26 behaviour).
            bodies = [((r.get("content_all") or "").strip(), fam)
                      for _s, fam in group for r in fam]
            text, fam = max(bodies, key=lambda b: len(b[0]), default=("", group[0][1]))
            if not text:
                # Nothing in the API at all. Many rows still point at their Royal Gazette
                # publication (`announce_url`, ratchakitcha.soc.go.th). Measured 2026-09-26:
                # all six National Cybersecurity Committee notifications — which the panel
                # cites for 7.2 — have no text and no items here, and each has a Gazette PDF
                # with a text layer. Emitted as that PDF, the ordinary fetch/extract chain
                # reads it; nothing is seeded, because there is nothing to seed.
                pdf = next((r.get("announce_url") for _s, f in group for r in f
                            if str(r.get("announce_url") or "").lower().endswith(".pdf")), None)
                head = _principal(group[0][1])
                if not pdf:
                    log(f"[th_law_api] no text for {_title(head)[:60]} — skipped")
                    continue
                out.append(portal.make_doc(economy, pdf, _title(head), portal_name,
                                           score=score, amendment_date=_iso_date(head)))
                log(f"[th_law_api] {score:.3f} {_title(head)[:70]} — Royal Gazette PDF")
                continue
            pick = (_principal(fam), fam)
        head = pick[0]
        title = _title(head)
        doc = portal.make_doc(economy, _detail_url(head), title, portal_name,
                              fmt=DocFormat.TEXT, score=score, amendment_date=_iso_date(head))
        try:
            from .fetch import seed_cache
            seed_cache(doc.source_url, text.encode("utf-8"), "text/plain", log=lambda _m: None)
        except Exception as exc:                      # noqa: BLE001 — discovery still stands
            log(f"[th_law_api] could not seed cache for {doc.doc_id}: {type(exc).__name__}")
        shape = f"{n} articles" if n else "whole text, no article items"
        log(f"[th_law_api] {score:.3f} {title[:70]} — {shape}")
        out.append(doc)
    return out


portal.register("th_law_api", search_th_law, enumerates_portal=True)
