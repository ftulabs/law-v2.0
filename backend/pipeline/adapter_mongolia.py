"""Mongolia — legalinfo.mn, enumerated by sitemap and read through the portal's own export.

This adapter exists because the obvious reading of legalinfo.mn is wrong, and I made that
mistake twice before writing it down properly.

**Attempt 1 (wrong).** The detail page returns 200 with ~110 KB of markup and ~12k Cyrillic
characters, so it was recorded as "the text is there, no OCR needed". Those characters are
the navigation menu, a registration modal, the Cyrillic alphabet index and a list of industry
sectors. `main-huuliin-content` and `law_content` are present but EMPTY: the body is injected
client-side. Zero article headings. Counting Cyrillic is not the same as reading it.

**Attempt 2 (wrong the other way).** Having found no statute text, the note then said
"legalinfo.mn serves no .doc or .docx, unlike China — body retrieval is unsolved." Also
false, and falsifiable in one request. The detail page's own toolbar carries

    <a onclick="downloadAnnexFile(this, '', '4801')">Word</a>

and `assets/custom/legal/js/static.js` defines it as

    $.fileDownload(URL_APP + URL_LANG + '/downloadFile?file=' + path + '&lawId=' + lawId
                   + '&fDownload=1', {httpMethod: "POST"})

So a POST to `/mn/downloadFile` returns the whole instrument. Two useful surprises in the
response:

  • it is labelled `.doc` but the bytes begin `<html xm…` — Word-flavoured HTML in UTF-8.
    There is nothing to OCR and no binary format to parse; `extraction` reads it as HTML.
  • `Content-Disposition: filename="…"` carries **the law's title in Mongolian**, which is
    the only place on the site a title is available without rendering JavaScript.

That second point decides the shape of this module. legalinfo.mn's listing pages are
DataTables-style and build their rows in the browser, so there is no server-rendered index to
scrape titles from — but `/sitemap.xml` answers 200 with 13,070 distinct `/mn/detail?lawId=N`
URLs, a complete enumeration of the corpus with no titles attached. Sitemap gives us *which
instruments exist*; only the export gives us *what each one is called*.

Hence a catalogue, built once by `tools/build_mn_catalogue.py` and shipped as
`data/catalogues/MN_titles.json` (id + title + size, no bodies). That is the same arrangement
Malaysia already uses — the portal's own table of contents, held locally so discovery can
filter by name without 13,070 live requests per run. It is a table of contents, not an answer
key: it contains no provision text, no indicator, and no mapping, and every body is still
fetched live at run time.

If the catalogue is absent the adapter still works, by walking the sitemap directly and
downloading titles as it goes, capped by `MN_MAX_PROBE`. Slower, and honest about it in the
log, rather than silently returning nothing — which is the failure mode this whole economy
keeps producing.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path

from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy

BASE = "https://legalinfo.mn"
SITEMAP = f"{BASE}/sitemap.xml"
DETAIL = BASE + "/mn/detail?lawId={id}"
EXPORT = BASE + "/mn/downloadFile?file=&lawId={id}&fDownload=1"

CATALOGUE = (Path(__file__).resolve().parents[2] / "data" / "catalogues" / "MN_titles.json")

#: Without a catalogue we probe the sitemap live. A live run cannot afford 13,070 requests, so
#: this caps the walk — and the log says the cap was hit, so a thin result is never mistaken
#: for "Mongolia has no such law".
MN_MAX_PROBE = 400

#: An unknown lawId still answers 200, with a ~6.7 KB shell and an EMPTY filename. Length alone
#: is a fragile test (a one-line decree is legitimately short), so the empty filename is what
#: distinguishes "no such instrument" from "a short one".
_EMPTY_EXPORT = 7000

#: How many instruments one query may contribute. Mongolia publishes the principal Act and
#: every order, rule and list made under it in the same catalogue: "банкны тухай" matches 193
#: titles, of which one is the Banking Law. Without a cap a single query would fetch two
#: hundred documents and bury the statute among its own implementing paperwork.
MN_MAX_PER_QUERY = 12

_LAW_ID = re.compile(r"lawId=(\d+)")
_FILENAME = re.compile(r'filename="([^"]*)"')
#: A tag needs a NAME (or a `!`/`?` declaration) after the "<". `<[^>]+>` also matched
#: "хугацаа < 30 хоног > бол" and swallowed the text between. That was latent while this only
#: ever saw the portal's own markup; it stops being latent now that the loop in `export_text`
#: can run over text an unescape produced.
_TAG = re.compile(r"</?[a-zA-Z][^>]*>|<[!?][^>]*>")
_WS = re.compile(r"\s+")
#: Title carries the repeal flag. legalinfo.mn has no in-force field, but it names a repealed
#: instrument "... ХҮЧИНГҮЙ" ("… no longer in force") and a repeal declaration "… ХҮЧИНГҮЙ
#: БОЛСОНД ТООЦОХ ТУХАЙ" — both contain хүчингүй. Citing either scores zero however well the
#: text reads (India drops them on dc.identifier.repealed; Mongolia drops them on the title,
#: measured on lawId=16758861545771).
_REPEALED_TITLE = re.compile(r"хүчингүй", re.I)
#: Word's HTML export wraps every paragraph, so these are where the line breaks the article
#: pattern needs actually live. `<br>` is included because the export uses it inside a
#: paragraph for a numbered clause.
_BLOCK_END = re.compile(
    r"</(?:p|div|tr|td|th|li|h[1-6]|table|blockquote)\s*>|<br\s*/?>", re.I)


def sitemap_law_ids(client, log=print) -> list[str]:
    """Every lawId the portal lists, in sitemap order, de-duplicated.

    The sitemap is the only complete enumeration legalinfo.mn offers, and it is a plain 5.5 MB
    XML file — no pagination, no token, no JavaScript.
    """
    r = client.get(SITEMAP)
    r.raise_for_status()
    seen: dict[str, None] = {}
    for m in _LAW_ID.finditer(r.text):
        seen.setdefault(m.group(1), None)
    log(f"[discovery] legalinfo.mn sitemap: {len(seen)} distinct lawId")
    return list(seen)


def export_law(client, law_id: str) -> tuple[str, bytes]:
    """(title, body) for one instrument, via the portal's Word-export route.

    Returns ("", b"") when the id does not resolve. The Referer is sent because the export is
    reached from the detail page in a browser; omitting it has not been observed to fail, but
    sending it keeps the request shaped like the one the site expects.
    """
    r = client.post(EXPORT.format(id=law_id),
                    headers={"Referer": DETAIL.format(id=law_id)})
    if r.status_code != 200:
        return "", b""
    m = _FILENAME.search(r.headers.get("content-disposition", ""))
    # Unescaped for the same reason `load_catalogue` does it: the portal writes a quoted short
    # title as `&quot;…&quot;` and it is carried straight into the Law Name column. This is the
    # no-catalogue probe path, so without it the two paths disagree about a law's own name.
    title = html.unescape(urllib.parse.unquote(m.group(1))) if m else ""
    title = re.sub(r"\.docx?$", "", title.strip(), flags=re.I).strip()
    if not title and len(r.content) < _EMPTY_EXPORT:
        return "", b""
    return title, r.content


def export_text(body: bytes) -> str:
    """The instrument's text, markup and Word artefacts removed, otherwise verbatim.

    The export is UTF-8 HTML whatever its `.doc` extension says, and `{worksheet}` appears at
    the head of every file as an export marker rather than as anything the legislature wrote.

    **Block elements become newlines, and that is the whole point.** The first version of this
    function flattened the document with a single `\\s+ → " "` and returned 34,196 characters of
    perfectly good Mongolian for the Personal Data Protection Law — from which
    `extraction._STRUCT_RE_MN` found **zero** articles, because that pattern is line-anchored
    to keep cross-references out. A law arriving as one 34k-character line is not an error any
    test would catch: it extracts, it maps, it just answers "no provision found" for everything.
    Mongolia has produced that exact silence twice already, so the boundaries are restored
    before the tags are dropped rather than after.
    """
    try:
        markup = body.decode("utf-8")
    except UnicodeDecodeError:
        markup = body.decode("cp1251", errors="replace")

    # Strip, unescape, and REPEAT while the unescaping revealed more markup.
    #
    # The order used to be strip-then-unescape, once, and that inverts on a doubly-encoded
    # export. lawId=16759949645981 carries 11,597 `&lt;` — an HTML fragment pasted into the
    # Word document as escaped TEXT, so it survives the strip untouched and the unescape then
    # turns it back into 11,597 live tags. The function returned 458,472 characters beginning
    # `<meta http-equiv="Content-Type"…`, no article pattern could match any of it, and the
    # whole file became ONE provision whose 20,000-character head was markup. That is a
    # garbage citation in the CSV and, on a grade-all run, twenty thousand characters of
    # Cyrillic markup in every prompt for every indicator — which is what a run reports as an
    # LLM failure rather than as a bad document.
    #
    # Unescaping FIRST is the other obvious order and is worse: a statute writing a genuine
    # "<" would have everything up to the next ">" eaten. Looping is what actually matches the
    # input — one pass per level of encoding — and it stops as soon as no real markup is left,
    # so a stray "<" costs nothing. Three is a stop, not a target; nothing seen needs over two.
    for _ in range(3):
        markup = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
        markup = _BLOCK_END.sub("\n", markup)
        unescaped = html.unescape(_TAG.sub(" ", markup))
        if unescaped == markup:
            break
        markup = unescaped
        if not _TAG.search(markup):
            break
    text = markup.replace("{worksheet}", " ")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n\s*", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_catalogue() -> list[dict]:
    """The shipped id→title index, or [] if it has not been built."""
    if not CATALOGUE.exists():
        return []
    try:
        data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    except Exception:                               # noqa: BLE001 — a corrupt index is not fatal
        return []
    rows = data.get("laws", []) if isinstance(data, dict) else data
    # Titles come from Content-Disposition and reach the catalogue still HTML-escaped, so a
    # law whose short title is quoted arrives as `&quot;…&quot;` and is carried straight into
    # the Law Name column of the submission CSV. Unescape once, here, rather than at each of
    # the places that read a title.
    for r in rows:
        t = r.get("title")
        if t and "&" in t:
            r["title"] = html.unescape(t)
    return rows


#: Mongolian FLEETING VOWEL. The docstring below used to claim a stem reaches its declined
#: form by plain substring, with "мэдээлэл inside мэдээллийн" as the worked example. That example is
#: FALSE, and it is checkable in one line: the second э is not kept, it is DROPPED before the
#: suffix, so мэдээлэл → мэдээлл-ийн and `"мэдээлэл" in "мэдээллийн"` is False. Every
#: query carrying that word could therefore never reach a title carrying its genitive.
#:
#: What that cost, measured against the panel's own Mongolia key: the query "нийтийн
#: мэдээлэл" could not match НИЙТИЙН МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДЛЫН ТУХАЙ — the Law on
#: Transparency of Public Information, which is the key's citation for 6.3 and for 8.2. A
#: pillar-6 run returned four documents, of which one was a statute.
#:
#: So a query word also matches with its final syllable's vowel elided. Restricted to words of
#: six characters or more, where an elision is a real morphological alternation rather than a
#: coincidental three-letter prefix.
_MN_VOWELS = "аэиоөуүяеёюы"


def _word_variants(word: str) -> set[str]:
    """The query word, plus its fleeting-vowel form when the language allows one."""
    out = {word}
    if len(word) >= 6 and word[-2] in _MN_VOWELS:
        out.add(word[:-2] + word[-1])
    return out


#: An AMENDING instrument — "… ХУУЛЬД НЭМЭЛТ ОРУУЛАХ ТУХАЙ" ("on making additions to the Law
#: on …"). Its body is a DIFF, not a law: a few hundred characters saying which sentence of
#: another Act changes. It cites beautifully and means nothing, and because legalinfo.mn often
#: files it under the PARENT Act's own title it outranked the parent whenever the parent's
#: title was one character longer. Repeals are caught by _REPEALED_TITLE; this is the other half.
_AMENDING_TITLE = re.compile(r"(н[эе]м[эе]лт|өөрчл[өе]лт).{0,40}оруулах", re.I)

#: Two rows are the SAME instrument when their titles agree once the qualifier is stripped
#: ("АРХИВЫН ТУХАЙ" and "АРХИВЫН ТУХАЙ /Шинэчилсэн найруулга/").
_TITLE_QUALIFIER = re.compile(r"\s*[/(].*$")


def _size(row: dict) -> int:
    """Byte size of the instrument's export, as recorded in the catalogue (0 if absent)."""
    try:
        return int(row.get("bytes") or 0)
    except (TypeError, ValueError):
        return 0


def _title_key(title: str) -> str:
    return _TITLE_QUALIFIER.sub("", title).strip().lower()


def _is_principal(title: str) -> bool:
    """A principal statute, as opposed to something made under one.

    Mongolia names an Act "<subject> тухай" and names an instrument made under it
    "<type> БАТЛАХ ТУХАЙ (<subject>)" — "on approving the <type>". Both end in тухай,
    so the батлах is what separates them.
    """
    base = _title_key(title)
    return base.endswith("тухай") and "батлах" not in base


#: A query may quote a group of words to require them ADJACENT: '"харилцаа холбоо" тухай'.
#:
#: Order-independent per-word matching is right for most of Mongolian — it is what reaches
#: ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ from a query written in the English name's order — but it has one
#: expensive false friend. холбоо is "communication" in харилцаа холбоо (telecommunications)
#: and "union/federation" in Холбооны Улс (Federal Republic). Mongolia has a treaty Act for
#: every country it recognises, each titled "… Холбооны Улстай дипломат харилцаа тогтоох
#: тухай", which carries all three words of "харилцаа холбооны тухай" and is a principal Act,
#: so it outranked genuine subordinate telecom instruments. Three of the 22 pillar-6 slots
#: went to establishing diplomatic relations with Comoros, Micronesia and Saint Kitts.
_QUOTED = re.compile(r'"([^"]+)"')


def _query_parts(query: str) -> list[tuple[str, bool]]:
    """(term, is_phrase) for each part of the query, quoted groups kept whole."""
    q = query.strip().lower()
    parts: list[tuple[str, bool]] = []
    pos = 0
    for m in _QUOTED.finditer(q):
        for w in q[pos:m.start()].split():
            parts.append((w, False))
        phrase = _WS.sub(" ", m.group(1).strip())
        if phrase:
            parts.append((phrase, True))
        pos = m.end()
    for w in q[pos:].split():
        parts.append((w, False))
    return parts


def _matches(title: str, query: str) -> bool:
    """Every word of the query appears somewhere in the title, in any order.

    A whole-phrase substring test is what this started as, and the catalogue killed it twice
    over on the single most important law in the country:

      • **Word order.** The Personal Data Protection Law is "ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ …", not
        "ХУВЬ ХҮНИЙ …". A phrase written from the English name misses it entirely.
      • **A missing space in the portal's own filename.** Its Content-Disposition reads
        "ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛХАМГААЛАХ ТУХАЙ" — no space between МЭДЭЭЛЭЛ and ХАМГААЛАХ. A
        phrase test fails on that; per-word substrings do not, because "хамгаалах" is still
        inside "мэдээлэлхамгаалах".

    Per-word substring also carries Mongolian's agglutination in the right direction: a query
    STEM matches a declined title form ("мэдээлэл" inside "мэдээллийн"), while an inflected
    query still will not match a bare stem. Write queries as stems and check them with
    `tools/audit_native_terms.py --economy MN`.
    """
    hay = _WS.sub(" ", title.lower())
    parts = _query_parts(query)
    if not parts:
        return False
    for part, is_phrase in parts:
        if is_phrase:
            # A quoted group must appear CONTIGUOUSLY. See _query_parts.
            if part not in hay:
                return False
        elif not any(v in hay for v in _word_variants(part)):
            return False
    return True


def _relevance(title: str, size: int) -> float:
    """How much of the 22-document discovery budget this instrument deserves.

    Every MN document used to be scored a flat 1.0, which made `discovery._cap` arbitrary:
    it trims to `discovery_max_docs` in score order, and with no spread the order it trimmed
    on was whichever query happened to run first. Pillar 7 alone offers ~77 candidates for
    22 slots, so the flat score was deciding, silently, that a Government resolution about an
    education database outranked the Banking Law.

    Principal statutes take the top band, subordinate instruments the lower one, and size
    orders within each — the same two signals the shortlist itself is built on, so a document
    cannot be ranked one way for selection and another way for the budget.
    """
    base = 0.90 if _is_principal(title) else 0.60
    return round(min(0.99, base + min(0.09, size / 6_000_000)), 4)


def _doc(law_id: str, title: str, economy: Economy, portal: str,
         size: int = 0) -> DiscoveredDoc:
    return DiscoveredDoc(
        doc_id=f"MN:{law_id}", economy=economy, title=title[:200], law_name=title[:200],
        # The citable page a reviewer can open — not the POST export they cannot.
        source_url=DETAIL.format(id=law_id),
        portal=portal, fmt=DocFormat.HTML,
        relevance_score=_relevance(title, size), discovery_tag=DiscoveryTag.NEW)


def _search_mn_legalinfo(client, src: dict, query: str, economy: Economy, indicators,
                         log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the signature `discovery` dispatches on.

    Titles come from the catalogue when it exists and from a capped live probe when it does
    not. Bodies are always fetched live in this call and seeded into the ordinary fetch cache,
    so extraction, hashing and the audit trail see a normal document and cannot tell the
    difference — the same arrangement India Code uses.
    """
    portal = src.get("name", "Unified Legal Information System")
    catalogue = load_catalogue()
    hits: list[tuple[str, str, int]] = []

    if catalogue:
        rows = [r for r in catalogue if _matches(r.get("title", ""), query)]

        # Repealed instruments are not evidence (the panel scores them zero). The portal has
        # no in-force flag, but the TITLE marks them, and an AMENDING act is dropped for the
        # same reason: its body is the diff, not the law.
        kept = [r for r in rows
                if not _REPEALED_TITLE.search(r.get("title", ""))
                and not _AMENDING_TITLE.search(r.get("title", ""))]
        if len(kept) < len(rows):
            log(f"[discovery] legalinfo.mn: dropped {len(rows) - len(kept)} repealed/amending "
                f"for {query!r}")

        # One row per instrument, keeping the LARGEST. legalinfo.mn files the same statute
        # several times under one title, and the small ones are stubs: lawId=100956 is
        # "XAPИЛЦAA XOЛБOOHЫ TУXAЙ /Шинэчилсэн найруулга/" at 9,867 bytes whose body opens
        # "...ХУУЛЬД НЭМЭЛТ ОРУУЛАХ ТУХАЙ" and yields 458 characters, against lawId=523 at
        # 251,215 bytes and 55,972 characters for the Act itself. Same for АРХИВЫН ТУХАЙ
        # (100518 vs 13,717) and ТӨРИЙН НУУЦЫН ТУХАЙ (83,163 vs 8,039).
        best: dict[str, dict] = {}
        for r in kept:
            k = _title_key(r.get("title", ""))
            if k not in best or _size(r) > _size(best[k]):
                best[k] = r

        # Principal statutes first, then by SIZE, and the size half is the correction.
        # Ordering by title length was a proxy for "principal instrument" that inverts on the
        # documents above: the stub and the Act share a title, so the tie broke on a trailing
        # qualifier and the 458-character diff won. Byte size is the portal's own measure of
        # how much instrument is behind an id, it is already in the catalogue, and it puts
        # БАНКНЫ ТУХАЙ (545,709) ahead of its 192 subordinate instruments the same way the
        # length rule was meant to.
        found = sorted(best.values(),
                       key=lambda r: (0 if _is_principal(r.get("title", "")) else 1,
                                      -_size(r), r.get("title", "")))
        if len(found) > MN_MAX_PER_QUERY:
            log(f"[discovery] legalinfo.mn: {len(found)} titles match {query!r}; taking the "
                f"{MN_MAX_PER_QUERY} largest principal instruments first")
        hits.extend((str(r["id"]), r["title"], _size(r)) for r in found[:MN_MAX_PER_QUERY])
    else:
        log(f"[discovery] MN catalogue missing — probing the sitemap live, capped at "
            f"{MN_MAX_PROBE} instruments. Build it with tools/build_mn_catalogue.py.")
        try:
            ids = sitemap_law_ids(client, log)
        except Exception as exc:                    # noqa: BLE001 — one dead portal is not fatal
            log(f"[discovery] legalinfo.mn sitemap failed: {type(exc).__name__}: {exc}")
            return []
        for law_id in ids[:MN_MAX_PROBE]:
            title, _ = export_law(client, law_id)
            if title and _matches(title, query):
                hits.append((law_id, title, 0))

    out: list[DiscoveredDoc] = []
    for law_id, title, size in hits:
        # The no-catalogue path discovers titles one export at a time; apply the same
        # repealed-title gate in both paths so a probe cannot smuggle in what the catalogue
        # already dropped.
        if _REPEALED_TITLE.search(title):
            continue
        try:
            _, body = export_law(client, law_id)
        except Exception as exc:                    # noqa: BLE001
            log(f"[discovery] MN export failed for lawId={law_id}: {type(exc).__name__}")
            continue
        if not body:
            continue
        try:
            from .fetch import seed_cache
            seed_cache(DETAIL.format(id=law_id), body, "text/html", log=lambda _m: None)
        except Exception as exc:                    # noqa: BLE001 — discovery still stands
            log(f"[discovery] could not seed MN lawId={law_id}: {type(exc).__name__}")
        out.append(_doc(law_id, title, economy, portal, size))

    log(f"[discovery] legalinfo.mn: {len(out)} instruments for {query!r}")
    return out
