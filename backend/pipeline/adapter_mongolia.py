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
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
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
    title = urllib.parse.unquote(m.group(1)) if m else ""
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
        html = body.decode("utf-8")
    except UnicodeDecodeError:
        html = body.decode("cp1251", errors="replace")
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = _BLOCK_END.sub("\n", html)
    text = _TAG.sub(" ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    text = text.replace("{worksheet}", " ")
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
    return data.get("laws", []) if isinstance(data, dict) else data


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
    hay = title.lower()
    words = [w for w in query.strip().lower().split() if w]
    return bool(words) and all(w in hay for w in words)


def _doc(law_id: str, title: str, economy: Economy, portal: str) -> DiscoveredDoc:
    return DiscoveredDoc(
        doc_id=f"MN:{law_id}", economy=economy, title=title[:200], law_name=title[:200],
        # The citable page a reviewer can open — not the POST export they cannot.
        source_url=DETAIL.format(id=law_id),
        portal=portal, fmt=DocFormat.HTML,
        relevance_score=1.0, discovery_tag=DiscoveryTag.NEW)


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
    hits: list[tuple[str, str]] = []

    if catalogue:
        found = [(str(r["id"]), r["title"]) for r in catalogue
                 if _matches(r.get("title", ""), query)]
        # Shortest title first. Mongolian names a principal Act "<subject> тухай" and names
        # everything made under it by its own instrument type with the subject in parentheses
        # — "ЖУРАМ БАТЛАХ ТУХАЙ (Кибер аюулгүй байдлын зөвлөл)". So title length is a good
        # proxy for tier, and it puts "БАНКНЫ ТУХАЙ" ahead of its 192 subordinate instruments.
        found.sort(key=lambda t: (len(t[1]), t[1]))
        if len(found) > MN_MAX_PER_QUERY:
            log(f"[discovery] legalinfo.mn: {len(found)} titles match {query!r}; taking the "
                f"{MN_MAX_PER_QUERY} shortest-titled (principal instruments first)")
        hits.extend(found[:MN_MAX_PER_QUERY])
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
                hits.append((law_id, title))

    out: list[DiscoveredDoc] = []
    for law_id, title in hits:
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
        out.append(_doc(law_id, title, economy, portal))

    log(f"[discovery] legalinfo.mn: {len(out)} instruments for {query!r}")
    return out
