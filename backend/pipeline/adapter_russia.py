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

ONE LIMIT, MEASURED, NOT WORKED AROUND: PAGINATION IS NOT DRIVEN FROM THE URL. `page=next`,
`page=2`, `page=21` and `page=last` all return the SAME twenty rows (measured 2026-09-12, and
the client holds no cookies, so the server keys the cursor on something not yet found). So each
query yields twenty rows and no more — which rows, though, IS ours to choose. See below.

WHY THE PRINCIPAL FEDERAL LAWS WERE MISSING, AND WHAT CHANGED (2026-09-26). The 2026-09-25 run
produced 44 documents and not one of them was 152-ФЗ "О персональных данных", the statute every
Russian pillar-6/7 answer hangs from. Four defects, each silent, each measured against the live
host that day:

1. `a1` IS THE TITLE FIELD, NOT FULL TEXT. The portal's own search form labels `a1`
   "Наименование" and `a0` "Текст". The configured queries were full-text phrases —
   "хранение персональных данных на территории", "запрет трансграничной передачи персональных
   данных" — which occur in no instrument's NAME, so three of five pillar-6 terms came back
   HTTP 204 with an empty body ("term 2/5 -> no response"), indistinguishable in the log from a
   dead portal.

2. THE LIST WAS SORTED OLDEST-FIRST BECAUSE NO `sort=` WAS SENT. The form's own default is
   `sort=7` (newest first); a URL without the field gets ascending date. So "базы данных на
   территории Российской Федерации" spent its twenty rows on 1990s treaties about a Russian
   military BASE ("базе") on Armenian TERRITORY — eleven of the pillar-6 run's final 22
   documents. The twenty-row cap was never the problem; the ORDER was.

3. NOTHING ASKED FOR A FEDERAL LAW. The form carries an instrument-type filter (`a3`, a
   classifier the portal resolves by name through its own autocomplete). Title "персональных
   данных" + type Федеральный закон + OLDEST first puts 152-ФЗ sixth of twenty — because a
   principal law predates every law that amends it, and its title IS the topic. The same
   shape finds 149-ФЗ ("защите информации", 2nd) and 187-ФЗ ("критической информационной
   инфраструктуры", 1st). So each term now runs TWO passes: principal laws oldest-first, and
   every instrument newest-first (current Government resolutions and orders made under them).

4. `rdk=0` IS THE ORIGINAL TEXT, NOT THE CURRENT ONE. 152-ФЗ at `rdk=0` is the 2006 enactment:
   25 articles, no 18.1, no 22.1, and NOT the data-localisation rule (art. 18 part 5, inserted
   by 242-ФЗ in 2014) that is the whole of Russia's 6.2 answer. The frameset `?docbody=&nd=`
   names the current redaction in its list iframe (`rdk=38` for 152-ФЗ on 2026-09-26), and that
   body carries art. 18 part 5 verbatim. So a row the portal marks "Действует c изменениями" is
   now fetched at its current redaction; "без изменений" rows have one redaction and keep 0.

Amending laws ("О внесении изменений в Федеральный закон …") still arrive — their titles quote
the principal's, so they score as high on the title — and are demoted, not dropped: the body
fetched for the principal is already consolidated, so an amendment only repeats a change the
principal already carries. A chamber's resolution APPROVING a law ("О Федеральном законе …")
is a vote, not a measure, and is dropped here.

The panel itself cites Russia almost entirely through commercial mirrors (24 of 28 references
are base.garant.ru and consultant.ru; only ONE is the official portal), so the answer key's
URLs cannot be a discovery target; the law NAME is the join key, as in Round 1.
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
#: submits; `a1` is the TITLE ("Наименование") — not the text, which is `a0`. `sort` is the
#: form's own select: 7 = newest first (the form's default), -7 = oldest first. Leaving `sort`
#: out does NOT get the form's default; it gets oldest first. All read off the live form.
LIST_URL = BASE + "?list_itself=&bpas=cd00000&a1={query}{type_filter}&sort={sort}&page=first"

SORT_NEWEST = 7
SORT_OLDEST = -7

#: The form's instrument-type classifier is resolved BY NAME through the portal's own
#: autocomplete (`nclassif=3` is the type field's classifier), rather than a code written down
#: here: the portal owns that code, and a stale one would filter to some other type silently.
AUTOCOMPLETE_URL = BASE + "?autocomplete&bpa=cd00000&nclassif=3&area=110&query={query}"
PRINCIPAL_TYPE = "Федеральный закон"

#: The frameset around a document. It is NOT the body (586 characters of chrome, see
#: BODY_URL), but its list iframe names the CURRENT redaction: `…&page=1&rdk=38`.
FRAME_URL = BASE + "?docbody=&nd={nd}"
_CURRENT_RDK = re.compile(r'id="list"[^>]*src="[^"]*doc_itself=[^"]*?rdk=(\d+)')


def _budget() -> int:
    """How many documents the lane hands back, and therefore how many bodies it fetches.

    Ranked first, fetched second: the old order fetched EVERY row's body before anything was
    ranked, which with two passes per term would be ~200 fetches for a 22-document budget.
    """
    from ..config import settings                                   # noqa: PLC0415
    return max(1, int(settings.discovery_max_docs))

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


def _cp1251(text: str) -> str:
    return urllib.parse.quote(text.encode(ENCODING, "replace"))


def _list_url(query: str, *, sort: int = SORT_NEWEST, type_code: str | None = None) -> str:
    """The list-frame URL for `query`.

    The query string is percent-encoded from windows-1251 BYTES, not UTF-8. This is not a
    detail: UTF-8-encoded Cyrillic reaches the server as a different word, the search succeeds,
    and it returns results for something else — a silent wrong answer rather than an error.
    `sort` is ALWAYS sent, because omitting it silently means oldest-first.
    """
    type_filter = f"&a3={type_code}&a3type=1" if type_code else ""
    return LIST_URL.format(query=_cp1251(query), type_filter=type_filter, sort=sort)


def body_url(nd: str, rdk: int | str = 0) -> str:
    return BODY_URL.replace("rdk=0", f"rdk={rdk}").format(nd=nd)


def parse_type_code(text: str, name: str = PRINCIPAL_TYPE) -> str | None:
    """The classifier code for the type called exactly `name`, from an autocomplete response.

    Each line is "<label>\\t<code>" percent-encoded from cp1251 AS A WHOLE — the tab arrives as
    "%09", so the line is decoded before it is split. EXACT match, because the prefix
    "Федеральный" also returns "Федеральный конституционный закон" and a prefix match would
    take whichever the portal lists first.
    """
    want = name.strip().casefold()
    for line in (text or "").splitlines():
        line = urllib.parse.unquote(line.strip(), encoding=ENCODING, errors="replace")
        label, _, code = line.partition("\t")
        if code.strip().isdigit() and label.strip().casefold() == want:
            return code.strip()
    return None


def parse_current_rdk(frame_html: str) -> int | None:
    """The current redaction number named by the document frameset, or None."""
    m = _CURRENT_RDK.search(frame_html or "")
    return int(m.group(1)) if m else None


def _has_redactions(row: dict) -> bool:
    """"Действует c изменениями" — the portal's own word that later redactions exist. (Its "c"
    is a LATIN c, so the match is on the Cyrillic stem, not the preposition — and "без
    изменений", which carries the same stem, is excluded explicitly.)"""
    status = row.get("status", "")
    return bool(re.search(r"изменени", status, re.I)) and not re.search(
        r"без\s+изменени", status, re.I)


def _resolve_type_code(client, log: Log) -> str | None:
    resp = portal.portal_get(client, AUTOCOMPLETE_URL.format(query=_cp1251(PRINCIPAL_TYPE)),
                             log, tries=2)
    code = parse_type_code(resp.content.decode(ENCODING, "replace")) if resp is not None else None
    if code is None:
        log(f"[ru_ips] could not resolve the portal's '{PRINCIPAL_TYPE}' type code — the "
            f"principal-law pass is SKIPPED, so principal Federal Laws may be missing")
    return code


def _current_body_url(client, row: dict, log: Log) -> str:
    """The body URL at the row's CURRENT redaction. Falls back to `rdk=0` (the original text)
    only when the frameset cannot be read — and says so, because that fallback is exactly the
    2006-text-without-article-18(5) defect this function exists to prevent."""
    if not _has_redactions(row):
        return body_url(row["nd"])
    resp = portal.portal_get(client, FRAME_URL.format(nd=row["nd"]), log, tries=2)
    rdk = parse_current_rdk(resp.content.decode(ENCODING, "replace")) if resp is not None else None
    if rdk is None:
        log(f"[ru_ips] nd={row['nd']}: current redaction not found — using the ORIGINAL text")
        return body_url(row["nd"])
    return body_url(row["nd"], rdk)


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
    score = 0.45 * base + 0.55 * topic
    # The title signal alone CANNOT separate a principal law from the laws amending it: an
    # amendment's title quotes the principal's ("О внесении изменений в Федеральный закон
    # "О персональных данных""), so on 2026-09-26 152-ФЗ and its 261-ФЗ amendment both scored
    # 0.5748 for pillar 6, and 187-ФЗ (critical information infrastructure) scored 0.4178 for
    # pillar 7 — BELOW the amendment and below a ratification of an unrelated treaty. The
    # instrument's CLASS is what separates them, so it moves the score by more than the whole
    # title spread (~0.2): principal +0.20, amending x0.6, treaty act x0.75.
    #
    # The principal bonus is paid only when the name actually carries the words searched for
    # (`row["terms"]`, set by the search loop). The portal's stemmer is generous: "персональных
    # данных" also returns 93-ФЗ on military PERSONNEL ("персонала") and 136-ФЗ on medical aid
    # to civilian personnel, and with an unconditional bonus both outranked every Government
    # resolution on cross-border transfer (measured 2026-09-26, 0.617 vs 0.507).
    # A row whose name carries NONE of the words that fetched it is the stemmer's false
    # positive, and is discounted (x0.7) rather than trusted: on 2026-09-26 five ratifications
    # of bilateral agreements on military "персонал" held pillar-7 slots at 0.418 above the
    # FSB's order on protecting information in state information systems.
    named = not row.get("terms") or any(
        names_term(row.get("subject", ""), t) for t in row["terms"])
    if is_principal(row) and named:
        score += 0.20
    elif is_amending(row):
        score *= 0.6
    elif _TREATY_RU.search(row.get("subject") or ""):
        score *= 0.75
    if not named:
        score *= 0.7
    return round(min(0.99, max(0.05, score)), 4)


def _stem(word: str) -> str:
    """A crude Russian stem: drop up to three letters of inflection, keep at least four.
    "персональных" -> "персональ" (so "персонала" does not match), "данных" -> "данн",
    "информации" -> "информа" (so "информационных" does)."""
    return word[:max(4, len(word) - 3)]


def names_term(subject: str, term: str) -> bool:
    """True when every content word of `term` occurs, stemmed, in the instrument's name."""
    low = (subject or "").lower().replace("ё", "е")
    words = [w for w in re.findall(r"[\w-]+", (term or "").lower().replace("ё", "е"))
             if len(w) > 3]
    return bool(words) and all(_stem(w) in low for w in words)


#: Drafting conventions of the INSTRUMENT CLASS, not law names: "on the introduction of
#: amendments/additions", "on recognising as no longer in force", "on suspending".
_AMENDING_RU = re.compile(
    r"^\s*о\s+(?:внесении\s+(?:изменени|дополнени)|признании\s+утративш|приостановлении)", re.I)
#: International-agreement acts: a Federal Law, but its operative content is a treaty.
_TREATY_RU = re.compile(r"^\s*о\s+(?:ратификации|присоединении|денонсации|подписании)", re.I)
#: A chamber's resolution on a law: "О Федеральном законе "…"" (the Federation Council approving
#: it) — a vote about the measure, not the measure. Bills ("О проекте федерального закона") are
#: already DRAFT in `rdtii/instrument.py`.
_CHAMBER_VOTE_RU = re.compile(r"^\s*о\s+федеральн\w*\s+(?:конституционн\w*\s+)?законе\b", re.I)
_PRINCIPAL_TYPES = ("федеральный конституционный закон", "федеральный закон", "кодекс")


def is_amending(row: dict) -> bool:
    return bool(_AMENDING_RU.search(row.get("subject") or ""))


def is_chamber_vote(row: dict) -> bool:
    return bool(_CHAMBER_VOTE_RU.search(row.get("subject") or ""))


def is_principal(row: dict) -> bool:
    """A Federal Law (or code) that is itself the measure: not amending, not a treaty act."""
    desig = (row.get("designation") or "").lower()
    if not any(desig.startswith(t) for t in _PRINCIPAL_TYPES):
        return False
    subject = row.get("subject") or ""
    return not (_AMENDING_RU.search(subject) or _TREATY_RU.search(subject))


def normalise_superscripts(html: str) -> str:
    """Write an inserted article's superscript number the way Russian legal citation does:
    "Статья 18<span class="W9">1</span>" -> "Статья 18.1".

    The portal marks an article inserted between 18 and 19 as 18 with a superscript 1 — a CSS
    class whose rule is `vertical-align:super` (or `:top`), not a <sup>. Text extraction puts
    that span on its own line, so the heading came out "Статья 18\\n1\\n." and the whole of
    article 18.1 (the operator's compliance measures, 7.4) was split as a SECOND "Статья 18".
    Measured on 152-ФЗ's current redaction 2026-09-26: 51 such superscripts, in headings,
    part numbers ("1¹.") and cross-references ("статьей 18¹"). The classes are read from the
    document's own stylesheet rather than assumed, since the class name is the portal's choice.
    A second-level insertion is a hyphenated superscript — 149-ФЗ has "Статья 10" + "2-1" —
    and becomes "10.2-1".
    """
    classes = set(re.findall(
        r"\.([A-Za-z][\w-]*)\s*\{[^}]*vertical-align\s*:\s*(?:super|top)", html or ""))
    num = r"\s*(\d{1,2}(?:-\d{1,2})?)\s*"
    pattern = r"<sup[^>]*>" + num + r"</sup>"
    if classes:
        alt = "|".join(re.escape(c) for c in sorted(classes))
        pattern = (r"(?:<sup[^>]*>|<span[^>]*class=\"(?:" + alt + r")\"[^>]*>)"
                   + num + r"</(?:sup|span)>")
    return re.sub(r"(\d)" + pattern, r"\1.\2", html or "")


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


def _seed_body(client, url: str, log: Log) -> bool:
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
    resp = portal.portal_get(client, url, log)
    if resp is None or not resp.content:
        return False
    text = normalise_superscripts(resp.content.decode(ENCODING, "replace"))
    seed_cache(url, text.encode("utf-8"), "text/html; charset=utf-8", log=lambda _m: None)
    return True


def search_ru_ips(client, src: dict, query: str, economy: Economy, indicators: list,
                  log: Log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the signature `discovery` dispatches on.

    Two passes per term (see the module docstring): principal Federal Laws oldest-first, then
    every instrument newest-first. Every row is ranked BEFORE any body is fetched, and only the
    top `discovery_max_docs` are fetched — at their current redaction — and seeded into the
    ordinary fetch cache (the arrangement India Code and legalinfo.mn use), so the windows-1251
    decode happens exactly once, here, where the encoding is known. A row whose body could not
    be seeded is NOT returned: `fetch` would re-read it as UTF-8 and delete every Cyrillic
    letter, which is worse than the row's absence.
    """
    portal_name = src.get("name", "Законодательство России (IPS)")
    terms = _queries(src, indicators, query)
    if not terms:
        log("[ru_ips] no Russian query terms configured — nothing to search for")
        return []

    type_code = _resolve_type_code(client, log)
    passes = [("principal", SORT_OLDEST, type_code)] if type_code else []
    passes.append(("newest", SORT_NEWEST, None))

    rows_by_nd: dict[str, dict] = {}
    repealed = votes = 0
    for i, term in enumerate(terms):
        for label, sort, code in passes:
            resp = portal.portal_get(client, _list_url(term, sort=sort, type_code=code), log,
                                     tries=2)
            if resp is None:
                # HTTP 204 with an empty body is how this server says "no title matches";
                # portal_get cannot tell that from a dead host, so this line claims neither.
                log(f"[ru_ips] term {i + 1}/{len(terms)} ({label}) -> no rows / no response")
                continue
            rows = parse_rows(resp.content.decode(ENCODING, "replace"))
            kept = 0
            for row in rows:
                if row["nd"] in rows_by_nd:
                    rows_by_nd[row["nd"]]["terms"].append(term)
                    continue
                row["terms"] = [term]
                if not in_force(row):
                    repealed += 1
                    continue
                if is_chamber_vote(row):
                    votes += 1
                    continue
                rows_by_nd[row["nd"]] = row
                kept += 1
            log(f"[ru_ips] {term[:46]!r} ({label}): {len(rows)} rows, {kept} new in-force")
    if repealed:
        log(f"[ru_ips] dropped {repealed} row(s) the portal marks 'Утратил силу'")
    if votes:
        log(f"[ru_ips] dropped {votes} chamber resolution(s) approving a law — a vote, "
            f"not a measure")

    # Asked here, before the fetch, for the reason `discovery._drop_unscoreable` gives: a row
    # the instrument class rules out would otherwise take a fetch slot and then be binned.
    from ..rdtii import instrument                                  # noqa: PLC0415
    unscoreable = (instrument.Status.DRAFT, instrument.Status.REPEALED,
                   instrument.Status.COMMENTARY)
    ranked = sorted(
        ((_relevance(r, indicators), r) for r in rows_by_nd.values()
         if instrument.classify(r["subject"] or r["designation"]) not in unscoreable),
        key=lambda t: (-t[0], t[1]["nd"]))

    out: list[DiscoveredDoc] = []
    principals = 0
    budget = _budget()
    for score, row in ranked:
        if len(out) >= budget:
            break
        url = _current_body_url(client, row, log)
        if not _seed_body(client, url, log):
            log(f"[ru_ips] nd={row['nd']}: body not fetched — not returned")
            continue
        out.append(portal.make_doc(
            economy, url, row["subject"] or row["designation"], portal_name,
            law_number=row["designation"] or None, score=score))
        principals += is_principal(row)
    log(f"[ru_ips] {len(rows_by_nd)} candidates, {len(out)} documents fetched "
        f"(budget {budget}), {principals} of them principal laws")
    return out


#: `enumerates_portal=True`: this adapter runs the whole configured query list itself on one
#: call and ignores the `query` argument once `data/sources.yaml` supplies terms. Without the
#: flag, `discovery` would call it once per generated query term and each call would re-run
#: every configured term — the multiplication `adapter_china.py` and `adapter_indonesia.py`
#: both had to fix.
portal.register("ru_ips", search_ru_ips, enumerates_portal=True)
