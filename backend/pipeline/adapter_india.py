"""India Code — discovery through the portal's own DSpace REST API.

This is the cleanest source in the whole set, and finding it corrected two wrong beliefs.

The first: `indiacode.nic.in` was recorded as "a JS shell — 200 with no statute text". It is
not a shell. It is a **site-migration notice** — the body carries
`<meta http-equiv="refresh" content="3;url=https://indiacode.gov.in">` and 249 characters of
prose explaining the move. Every other path on the old host answers 504, because its backend
is gone. We had diagnosed a rendering problem and the portal had simply moved.

The second: the new host's HTML front end answers 502 for `/`, `/browse` and `/sitemap.xml` —
so anything reading the site as a website concludes India is unreachable. Its **API is up**.
`/server/api` is DSpace 7, and it exposes what a discovery adapter actually wants.

What the API gives us, and why it matters here more than anywhere else:

    dc.identifier.collection      "SECTION" — sections are separate items, so the article-level
                                  citation the submission requires is the unit the portal ships
    dc.identifier.section_number  the section number, already parsed
    dc.title                      the section heading
    dc.title.act_name             the parent Act
    dc.identifier.section_page_note   THE OPERATIVE TEXT of the section, as HTML
    dc.identifier.act_repealed    an in-force flag, so repealed Acts can be dropped up front
    dc.identifier.act_number / act_year / ministry_name / state_name

So for India there is no PDF, no OCR, no HTML scraping and no article-splitting heuristic:
the provision boundaries are the publisher's own. Every other economy needs
`extraction._boundaries` to guess where one section ends; India does not.

One consequence worth stating plainly: because the text arrives already structured, India is
the economy where a mis-citation cannot be blamed on extraction. If a row is wrong here, the
mapping is wrong.
"""
from __future__ import annotations

import re
import urllib.parse

from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy

API = "https://indiacode.gov.in/server/api"

#: Central Acts are the RDTII unit; state legislation is out of scope and would multiply the
#: corpus by thirty. The API labels it, so this is a filter rather than a guess.
CENTRAL_ONLY = True

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _md(item: dict, key: str) -> str:
    vals = (item.get("metadata") or {}).get(key) or []
    return vals[0].get("value", "") if vals else ""


def section_text(item: dict) -> str:
    """The section's operative text, HTML stripped, whitespace normalised.

    Kept verbatim in every other respect: the Verbatim Snippet column is the statute's own
    words, and `section_page_note` is where India Code publishes them. Only markup and runs of
    whitespace are removed — no re-casing, no re-punctuation, no summarising.
    """
    raw = _md(item, "dc.identifier.section_page_note")
    if not raw:
        return ""
    text = _TAG.sub(" ", raw)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return _WS.sub(" ", text).strip()


def is_in_force(item: dict) -> bool:
    """False when the portal marks the Act or the section repealed.

    Two separate flags, and both must be clear: an Act can stand while one section is repealed.
    A repealed instrument scores zero however well it reads, so this is a correctness filter
    rather than an optimisation — see `rdtii/instrument.py` for the same rule applied to names.
    """
    return not (_md(item, "dc.identifier.act_repealed").lower() == "true"
                or _md(item, "dc.identifier.repealed").lower() == "true")


def _get(client, path: str, **params) -> dict:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    r = client.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def search_sections(client, query: str, size: int = 60) -> list[dict]:
    """SECTION items matching a query, in force, Central. Returns raw API items."""
    data = _get(client, "/discover/search/objects", query=query, dsoType="item", size=size)
    objects = (((data.get("_embedded") or {}).get("searchResult") or {})
               .get("_embedded") or {}).get("objects") or []
    out = []
    for o in objects:
        item = (o.get("_embedded") or {}).get("indexableObject") or {}
        if _md(item, "dc.identifier.collection") != "SECTION":
            continue          # ACT-level items carry no operative text of their own
        if not is_in_force(item):
            continue
        if CENTRAL_ONLY and _md(item, "dc.identifier.state_name").upper() != "CENTRAL":
            continue
        if not section_text(item):
            continue          # a heading with no body cannot support a citation
        out.append(item)
    return out


def _search_in_dspace(client, src: dict, query: str, economy: Economy, indicators,
                      log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the signature `discovery` dispatches on.

    One DiscoveredDoc per SECTION. That is deliberate and different from the other economies,
    where a document is an Act and extraction splits it: here the portal has already done the
    splitting, and re-joining sections into a synthetic Act only to split them again would
    reintroduce exactly the boundary errors this source lets us avoid.
    """
    try:
        items = search_sections(client, query)
    except Exception as exc:                     # noqa: BLE001 — one dead query is not fatal
        log(f"[discovery] India Code API failed for {query!r}: {type(exc).__name__}: {exc}")
        return []

    out: list[DiscoveredDoc] = []
    for item in items:
        handle = item.get("handle") or ""
        act = _md(item, "dc.title.act_name").strip().rstrip(".")
        sec = _md(item, "dc.identifier.section_number")
        heading = (item.get("name") or "").strip()
        if not (handle and act):
            continue
        title = f"{act} — Section {sec}: {heading}" if sec else f"{act} — {heading}"
        number = _md(item, "dc.identifier.act_number")
        year = _md(item, "dc.identifier.act_year")
        # The text came back with the search result, and the citable HTML page is 502 today.
        # Seed it so every downstream stage sees an ordinary cached document.
        body = (f"<html><body><h1>{heading}</h1>"
                f"<p>{sec}. {section_text(item)}</p></body></html>").encode("utf-8")
        try:
            from .fetch import seed_cache
            seed_cache(f"https://indiacode.gov.in/handle/{handle}", body, "text/html",
                       log=lambda _m: None)
        except Exception as exc:                 # noqa: BLE001 — discovery still stands
            log(f"[discovery] could not seed India section {handle}: {type(exc).__name__}")
        out.append(DiscoveredDoc(
            doc_id=f"IN:{handle}", economy=economy, title=title[:200],
            # The citable public URL, not the API endpoint — the Source URL column has to be
            # something a reviewer can open.
            source_url=f"https://indiacode.gov.in/handle/{handle}",
            portal=src.get("name", "India Code"), fmt=DocFormat.HTML,
            law_number=(f"Act {number} of {year}" if number and year else None),
            relevance_score=1.0, discovery_tag=DiscoveryTag.NEW,
            amendment_date=(year or None)))
    log(f"[discovery] India Code API: {len(out)} in-force Central sections for {query!r}")
    return out
