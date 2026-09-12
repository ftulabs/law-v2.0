"""Russia — `pravo.gov.ru`'s IPS ("Законодательство России"), read through its own list frame.

WHY THIS EXISTS. Russia was the one economy of eleven with no portal lane, and its two
`data/sources.yaml` entries were both `adapter: websearch`. With every search engine answering
403, what that lane actually returned on 2026-09-11 was fifteen documents of which NOT ONE was
on a Russian government host: an advert for a VPN subscription served by duckduckgo.com,
en.wikipedia.org, cloudflare.com, imperva.com, two Vietnamese law-reference sites publishing
Vietnam's own 91/2025/QH15, and pdpc.gov.sg — Singapore's regulator. `discovery` now refuses
off-host results outright, so that lane returns nothing at all, which is honest and useless.

THE RECORDED BELIEF WAS WRONG, AND THAT IS THE INTERESTING PART. `data/sources.yaml` said, from
a 2026-08-28 probe: "the rows are injected client-side: neither plain HTTP nor a default browser
render surfaces a single nd= id (measured, both routes, 25.2k rendered bytes, zero ids)". That
measurement was real; the conclusion drawn from it was not. IPS is a THREE-DEEP frameset and
the probe stopped at the second level:

    ?searchres=&bpas=cd00000&a1=<q>     1.3 kB   frameset      ->  ?searchlist=…
    ?searchlist=&bpas=cd00000&a1=<q>    25.2 kB  toolbar+frame ->  ?list_itself=…&page=first
    ?list_itself=&bpas=cd00000&a1=<q>   105  kB  THE ROWS, server-rendered, no JS

25.2 kB with zero ids is exactly the second line — the frame that HOLDS the list, not the list.
Nothing is injected client-side; the rows are plain HTML one level further down. Verified
2026-09-12 against the live host.

WHAT THE ROW CARRIES, and the last of it is the reason this adapter can be trusted:

    <span class="tiny_italic_bold">   "Действует без изменений" / "Действует c изменениями"
                                      / "Утратил силу"  — THE PORTAL'S OWN IN-FORCE STATUS
    <a class="bold">                  designation: type, date, number
    <span class="bold">               the subject line — the instrument's actual name
    nd=<id>                           the document id

A repealed instrument scores zero however well it reads, and Russia is the one economy here
that states the answer in the listing itself rather than leaving it to be inferred from a
title (compare `adapter_mongolia._is_repealed`, which has to fetch a second page to find out).

TWO LIMITS, BOTH MEASURED, NEITHER WORKED AROUND:

1. PAGINATION IS NOT DRIVEN FROM THE URL. `page=next`, `page=2`, `page=21` and `page=last` all
   return the SAME twenty rows (measured 2026-09-12, and the client holds no cookies, so the
   server keys the cursor on something not yet found). Walking the frameset in browser order
   first does not change it. So each query yields twenty rows and no more.

2. THOSE TWENTY ARE THE OLDEST, NOT THE BEST. The list is chronological, so a broad query
   spends all twenty on Soviet-era decrees: "О персональных данных" returns twenty 1991
   resolutions of the USSR Cabinet of Ministers, because the stemmer matches "персонального
   состава" (personnel composition) just as happily as "персональных данных".

Both limits point the same way, and it is the shape of this adapter: QUERY PRECISELY. A narrow
statutory phrase returns a set small enough to fit inside the twenty. "трансграничная передача
персональных данных" returns SIX rows, and all six are real cross-border-transfer instruments —
the Government's Rules on prohibiting or restricting cross-border transfer, the list of cases
where operators face additional requirements, the Council of Europe Convention protocol. That
is a pillar-6 answer set. A vague phrase returns twenty rows of nothing.

WHAT THIS LANE DOES NOT REACH. The principal Federal Laws themselves — 152-ФЗ on personal data,
149-ФЗ on information, 187-ФЗ on critical information infrastructure — do not surface as their
own rows under these queries; what surfaces is the Government and chamber instruments made
under them, plus chamber resolutions on the bills that became them (dropped as DRAFT by
`rdtii/instrument.py`). This is disclosed rather than fixed. It is also consistent with what
the panel itself cites for Russia: 24 of its 28 references are base.garant.ru and consultant.ru,
commercial mirrors, and only ONE is the official portal.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Callable

from ..schemas import DiscoveredDoc, Economy
from . import portal

Log = Callable[[str], None]

BASE = "http://pravo.gov.ru/proxy/ips/"

#: The list frame. `bpas=cd00000` is the IPS database selector the portal's own search form
#: submits; `a1` is the free-text query. Both are read off the live form, not guessed.
LIST_URL = BASE + "?list_itself=&bpas=cd00000&a1={query}&page=first"

#: The body. Verified: returns the whole document server-rendered. NOT `?docbody=&nd=<id>`,
#: which is a frameset carrying 586 characters of chrome and no law — the trap `sources.yaml`
#: already recorded, and the reason this constant is written down rather than assembled.
BODY_URL = BASE + "?doc_itself=&nd={nd}&page=1&rdk=0"

#: EVERYTHING ON THIS HOST IS windows-1251. Decoded as UTF-8 it does not raise — it produces
#: mojibake that flows all the way to the Verbatim Snippet column looking like an OCR problem.
ENCODING = "cp1251"

_ROW = re.compile(
    r'<table class="list_elem[^"]*".*?'
    r'<span class="tiny_italic_bold">(?P<status>.*?)</span>.*?'
    r'nd=(?P<nd>\d+).*?'
    r'class="bold"[^>]*>(?P<desig>.*?)</a>.*?'
    r'<span class="bold">(?P<subject>.*?)</span>',
    re.S)

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

#: The portal's own words for "no longer in force". Matched on the status span, which is the
#: portal's answer and not our inference.
_NOT_IN_FORCE = re.compile(r"утратил\s+силу|отменен|не\s+вступил|признан\s+утратившим", re.I)

#: Instrument type -> prior. A Federal Law outranks a Government Resolution, which outranks a
#: ministerial order. Deliberately a SMALL spread against the topical signal below, for the
#: reason `adapter_thailand._relevance` records: a type weight that approaches the cap decides
#: the ranking on its own and every instrument of that type ties.
_TYPE_WEIGHT: tuple[tuple[str, float], ...] = (
    ("федеральный конституционный закон", 0.95),
    ("федеральный закон", 0.90),
    ("кодекс", 0.88),
    ("указ президента", 0.80),
    ("постановление правительства", 0.75),
    ("распоряжение правительства", 0.60),
    ("постановление", 0.55),
    ("приказ", 0.50),
    ("распоряжение", 0.45),
)
_DEFAULT_TYPE_WEIGHT = 0.40


def _clean(fragment: str) -> str:
    return _WS.sub(" ", _TAGS.sub(" ", fragment or "")).strip()


def _list_url(query: str) -> str:
    """The list-frame URL for `query`.

    The query string is percent-encoded from windows-1251 BYTES, not UTF-8. This is not a
    detail: UTF-8-encoded Cyrillic reaches the server as a different word, the search succeeds,
    and it returns results for something else — a silent wrong answer rather than an error.
    """
    return LIST_URL.format(query=urllib.parse.quote(query.encode(ENCODING, "replace")))


def body_url(nd: str) -> str:
    return BODY_URL.format(nd=nd)


def parse_rows(html: str) -> list[dict]:
    """Every result row: `nd`, `status`, `designation`, `subject`.

    Pure and network-free, so the test suite drives it against a saved fixture.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in _ROW.finditer(html or ""):
        nd = m.group("nd")
        if nd in seen or nd == "0":
            continue
        seen.add(nd)
        out.append({"nd": nd, "status": _clean(m.group("status")),
                    "designation": _clean(m.group("desig")),
                    "subject": _clean(m.group("subject"))})
    return out


def in_force(row: dict) -> bool:
    """The portal's own verdict, not ours. An unlabelled row is KEPT — silence is not a repeal,
    and deleting evidence on an absent field is the worse of the two mistakes."""
    return not _NOT_IN_FORCE.search(row.get("status", ""))


def _relevance(row: dict, indicators: list) -> float:
    """Rank from the subject line plus the instrument type.

    The subject is the instrument's real name, so it is what `portal.title_relevance` is given;
    the designation carries only type, date and number and would score every row identically.
    """
    low = (row.get("designation") or "").lower()
    base = _DEFAULT_TYPE_WEIGHT
    for needle, weight in _TYPE_WEIGHT:
        if needle in low:
            base = weight
            break
    topic = portal.title_relevance(row.get("subject", ""), indicators, economy="RU")
    return round(min(0.99, max(0.05, 0.45 * base + 0.55 * topic)), 4)


def _queries(src: dict, indicators: list, query: str) -> list[str]:
    """This source's own Russian phrases for the pillar(s) in play, else the caller's `query`.

    Same vehicle every other portal-native lane uses (`queries_p6`/`queries_p7` in
    `data/sources.yaml`), and for the same reason: the portal indexes Russian, and an English
    phrase fired at it matches nothing while raising nothing.
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
    return out


def _seed_body(client, nd: str, log: Log) -> bool:
    """Fetch this document and put it in the cache ALREADY DECODED, as UTF-8.

    This is the trap `data/sources.yaml` recorded and the first version of this adapter still
    walked into. Everything on this host is windows-1251, and `fetch` stores raw bytes and later
    reads them back with `read_text(encoding="utf-8", errors="ignore")`. cp1251 Cyrillic is not
    valid UTF-8, so `errors="ignore"` DELETES it — silently, and only the Cyrillic. Measured
    2026-09-12, a Government resolution on cross-border transfer reached extraction as:

        ", , , , , , 3 - 6, 8 - 11 12 \\" \\" Complex 29 2022 . 2526 , , , , , , 3 - 6, ..."

    Every letter gone, every digit and comma kept. Nothing raised, the provision count was
    normal, and that string is what the Verbatim Snippet column would have carried — a citation
    to a Russian statute containing no Russian.

    Decoding here, where the encoding is known, is the same arrangement India Code and
    legalinfo.mn already use, and it keeps `fetch` from having to guess.
    """
    from .fetch import seed_cache                                   # noqa: PLC0415
    url = body_url(nd)
    resp = portal.portal_get(client, url, log)
    if resp is None or not resp.content:
        return False
    text = resp.content.decode(ENCODING, "replace")
    seed_cache(url, text.encode("utf-8"), "text/html; charset=utf-8", log=lambda _m: None)
    return True


def search_ru_ips(client, src: dict, query: str, economy: Economy, indicators: list,
                  log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the signature `discovery` dispatches on.

    Bodies are fetched here and seeded into the ordinary fetch cache, the same arrangement
    India Code and legalinfo.mn use, so extraction and the audit trail see a normal document.
    Seeding is also what makes the windows-1251 decode happen exactly once, here, where the
    encoding is known — rather than in `fetch`, which would have to guess.
    """
    portal_name = src.get("name", "Законодательство России (IPS)")
    terms = _queries(src, indicators, query)
    if not terms:
        log("[ru_ips] no Russian query terms configured — nothing to search for")
        return []

    out: list[DiscoveredDoc] = []
    seen_nd: set[str] = set()
    repealed = 0
    for i, term in enumerate(terms):
        url = _list_url(term)
        resp = portal.portal_get(client, url, log)
        if resp is None:
            log(f"[ru_ips] term {i + 1}/{len(terms)} -> no response")
            continue
        rows = parse_rows(resp.content.decode(ENCODING, "replace"))
        kept = 0
        for row in rows:
            if row["nd"] in seen_nd:
                continue
            if not in_force(row):
                repealed += 1
                continue
            seen_nd.add(row["nd"])
            doc = portal.make_doc(
                economy, body_url(row["nd"]),
                row["subject"] or row["designation"], portal_name,
                law_number=row["designation"] or None,
                score=_relevance(row, indicators))
            _seed_body(client, row["nd"], log)
            out.append(doc)
            kept += 1
        log(f"[ru_ips] {term[:46]!r}: {len(rows)} rows, {kept} new in-force")
    if repealed:
        log(f"[ru_ips] dropped {repealed} row(s) the portal marks 'Утратил силу'")
    log(f"[ru_ips] {len(out)} unique documents")
    return out


#: `enumerates_portal=True`: this adapter runs the whole configured query list itself on one
#: call and ignores the `query` argument once `data/sources.yaml` supplies terms. Without the
#: flag, `discovery` would call it once per generated query term and each call would re-run
#: every configured term — the multiplication `adapter_china.py` and `adapter_indonesia.py`
#: both had to fix.
portal.register("ru_ips", search_ru_ips, enumerates_portal=True)
