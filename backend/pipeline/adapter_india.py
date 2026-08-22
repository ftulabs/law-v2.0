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

──────────────────────────────────────────────────────────────────────────────────────────
WHY THIS ADAPTER SEARCHES IN TWO STAGES (2026-08-23)
──────────────────────────────────────────────────────────────────────────────────────────
The first version fired each generated query at `query=` and kept whatever SECTION items came
back. Measured against the live API, that lane was close to sampling the corpus at random, for
two reasons that only show up when you look at what it returns:

  * `query=` is a loose full-text match with no useful ranking. `cross-border transfer of
    personal data` returns 71 items whose top five are the Commercial Courts Act, the National
    Highways Rules, the Mineral Conservation Rules, a Maharashtra water authority and the
    Andaman & Nicobar Police Manual. The DPDP Act is not among them. Quote the phrases and the
    same idea — `"personal data" AND "outside India"` — returns two sections, the first being
    s.16 *Processing of personal data outside India*, which is India's 6.4 answer.
  * the generated query pack is SG/AU/MY's. Its "name" fragments (`companies act`,
    `income tax act`, `labour act`) exist to match a TITLE on a name-only portal. Fired at a
    full-text engine they match any Act whose body mentions the word, which is how a pillar-6
    run came back holding the Indian Reserve Forces Act 1888, the Bonded Labour System
    (Abolition) Act, the National Dairy Development Board Act and the Medical Termination of
    Pregnancy Act. Nine of eighteen documents arrived that way.

So: **stage 1 finds the Act, stage 2 takes the whole Act.**

Stage 1 fires a quoted statutory phrase and tallies the parent Acts of the Central SECTION
hits. Stage 2 asks `dc.title.act_name:"<act>"` and pages until the Act is exhausted — the
Information Technology Act 2000 yields its 125 sections, including 43A (security practices),
67C (preservation) and 69 (interception), none of which the old lane ever reached.

That also repairs a unit mismatch that no cap could have fixed. `discovery_max_docs` counts
DOCUMENTS, and everywhere else a document is an Act that extraction later splits into
hundreds of provisions. Here a document was one section, so India's entire pillar budget was
eighteen provisions where Singapore's is eighteen statutes. Discovery now spends that budget
on Acts (`unit: section` in data/sources.yaml), and the Act arrives whole.

The law names are never written down here: stage 1 discovers them from obligation phrases, so
the no-seed-URLs / no-hardcoded-law-names rule holds. What IS written down, in sources.yaml,
is the statutory language an Indian drafter uses — the same thing the CN and MN lanes carry,
for the same reason.
"""
from __future__ import annotations

import collections
import math
import re
import urllib.parse
import weakref

from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy

API = "https://indiacode.gov.in/server/api"

#: Central Acts are the RDTII unit; state legislation is out of scope and would multiply the
#: corpus by thirty. The API labels it, so this is a filter rather than a guess.
CENTRAL_ONLY = True

#: DSpace silently caps a page at 100 objects however large `size` is — asking for 200 returns
#: 100 and a totalPages computed as though it had returned 200. Paging is therefore mandatory,
#: and a run that assumed one big page would lose two thirds of the Information Technology Act
#: with no error to show for it.
PAGE_SIZE = 100

#: Sections harvested per Act before we stop and say so. The Acts that matter here run to ~125
#: sections (IT Act 2000); this only bites on a code such as Income-tax, which is not a P6/P7
#: instrument. Never silently truncate — `log` says what was dropped.
MAX_SECTIONS_PER_ACT = 400

#: Acts admitted from one query's hits. A precise phrase names one or two; a loose one names
#: sixteen, and taking its whole tail would spend the run's budget on the tail.
MAX_ACTS_PER_QUERY = 4

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_ALREADY_STRUCTURED = re.compile(r"[\"“”]|\bAND\b|\bOR\b")


def _md(item: dict, *keys: str) -> str:
    """First non-empty value among `keys`.

    Several fields exist under more than one name and the SEARCH payload does not always carry
    the same ones as a direct item fetch — the year is `dc.date.act_year` in search results and
    `dc.identifier.act_year` when the item is fetched by uuid. Reading a single key silently
    produced an empty Law Number for every Indian row, which is the quiet-wrong-field failure
    that costs an optional column without ever raising.
    """
    md = item.get("metadata") or {}
    for key in keys:
        vals = md.get(key) or []
        if vals and vals[0].get("value"):
            return vals[0]["value"]
    return ""


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


def is_central(item: dict) -> bool:
    return not CENTRAL_ONLY or _md(item, "dc.identifier.state_name").upper() == "CENTRAL"


def act_name(item: dict) -> str:
    return _md(item, "dc.title.act_name").strip().rstrip(".")


def _get(client, path: str, **params) -> dict:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    r = client.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def _objects(data: dict) -> tuple[int, list[dict]]:
    """(total matches, indexable items) out of a DSpace search payload."""
    sr = ((data.get("_embedded") or {}).get("searchResult") or {})
    objs = ((sr.get("_embedded") or {}).get("objects") or [])
    total = int((sr.get("page") or {}).get("totalElements") or 0)
    return total, [(o.get("_embedded") or {}).get("indexableObject") or {} for o in objs]


def as_phrase(query: str) -> str:
    """Quote a bare query so the engine matches a phrase rather than a bag of words.

    Left alone if it already carries quotes or a boolean operator, so a query written by hand
    in sources.yaml passes through exactly as written. This guards the fallback path, where
    the generic English pack reaches this portal: unquoted, `cross-border transfer of personal
    data` matches any Act containing *data*, and the top of that result set is highway rules.
    """
    q = (query or "").strip()
    if not q or _ALREADY_STRUCTURED.search(q):
        return q
    return '"%s"' % q if " " in q else q


def search_sections(client, query: str, size: int = 60) -> list[dict]:
    """SECTION items matching a query, in force, Central. Returns raw API items."""
    _total, items = _objects(_get(client, "/discover/search/objects", query=query,
                                 dsoType="item", size=size))
    out = []
    for item in items:
        if _md(item, "dc.identifier.collection") != "SECTION":
            continue          # ACT-level items carry no operative text of their own
        if not is_in_force(item):
            continue
        if not is_central(item):
            continue
        if not section_text(item):
            continue          # a heading with no body cannot support a citation
        out.append(item)
    return out


# ── stage 1: which Acts does this phrase point at? ────────────────────────────────────────

def phrase_acts(client, query: str) -> tuple[int, collections.Counter]:
    """Acts named by the Central SECTION hits for `query`, and the query's total match count.

    The total is kept because it measures the discriminating power of the phrase.
    `"transfer of personal data"` matches 4 items in the whole corpus and every one is the
    DPDP Act; `"retain" AND "period" AND "records"` matches 2,709 and names eleven Acts, most
    of them tenancy and benami-property law. Weighting by it is ordinary IDF, and it is the
    difference between ranking the Acts and merely listing them.
    """
    total, items = _objects(_get(client, "/discover/search/objects", query=query,
                                dsoType="item", size=PAGE_SIZE))
    acts: collections.Counter = collections.Counter()
    for item in items:
        if _md(item, "dc.identifier.collection") != "SECTION":
            continue
        if not (is_in_force(item) and is_central(item)):
            continue
        name = act_name(item)
        if name:
            acts[name] += 1
    return total, acts


def phrase_weight(total_hits: int) -> float:
    """How much one phrase's opinion is worth. Rare phrase → near 1, common phrase → near 0.3.

    The `+10` keeps a 2-hit phrase from scoring unboundedly above a 4-hit one: the corpus is
    130k items, so nothing here is rare enough for that distinction to mean anything.
    """
    return 1.0 / math.log10(max(int(total_hits), 0) + 10)


# ── stage 2: take the whole Act ───────────────────────────────────────────────────────────

def act_sections(client, act: str, log=lambda _m: None) -> list[dict]:
    """Every in-force Central SECTION of one Act, paged to exhaustion.

    This is the call the old lane never made, and it is where India's actual evidence lives:
    the Information Technology Act 2000 returns 125 sections here, s.43A, s.67C and s.69 among
    them. A phrase search returns at most a handful of an Act's sections — the ones whose text
    happens to contain the phrase — which is not the same thing as the Act.
    """
    query = 'dc.title.act_name:"%s"' % act.replace('"', " ")
    out: list[dict] = []
    seen: set[str] = set()
    page = 0
    while len(out) < MAX_SECTIONS_PER_ACT:
        total, items = _objects(_get(client, "/discover/search/objects", query=query,
                                    dsoType="item", size=PAGE_SIZE, page=page))
        if not items:
            break
        for item in items:
            if _md(item, "dc.identifier.collection") != "SECTION":
                continue
            if not (is_in_force(item) and is_central(item)):
                continue
            if act_name(item) != act:
                continue      # act_name is a phrase match, so a longer title can slip in
            if not section_text(item):
                continue
            if is_omitted(item):
                continue      # repealed in the text, not in the in-force flag
            handle = item.get("handle") or ""
            if handle in seen:
                continue
            seen.add(handle)
            out.append(item)
        page += 1
        if page * PAGE_SIZE >= total:
            break
    if len(out) >= MAX_SECTIONS_PER_ACT:
        log(f"[discovery] India Code: {act!r} truncated at {MAX_SECTIONS_PER_ACT} sections")
    return out


# ── per-run scratch ───────────────────────────────────────────────────────────────────────

_RUN: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _run_state(client) -> dict:
    """Which Acts this run has already harvested, and each one's running score.

    Keyed WEAKLY on the httpx client, which `discovery.discover` creates once per run inside a
    `with` block. That makes the lifetime exactly one run without a module global that would
    leak between runs in a long-lived process — the Streamlit server being precisely that.
    """
    if client is None:
        return {"score": collections.Counter(), "docs": {}}
    state = _RUN.get(client)
    if state is None:
        state = {"score": collections.Counter(), "docs": {}}
        _RUN[client] = state
    return state


def _doc(item: dict, src: dict, economy: Economy, score: float) -> DiscoveredDoc | None:
    handle = item.get("handle") or ""
    act = act_name(item)
    if not (handle and act):
        return None
    sec = _md(item, "dc.identifier.section_number")
    heading = (item.get("name") or "").strip()
    title = f"{act} — Section {sec}: {heading}" if sec else f"{act} — {heading}"
    number = _md(item, "dc.identifier.act_number")
    year = _md(item, "dc.identifier.act_year", "dc.date.act_year")
    return DiscoveredDoc(
        doc_id=f"IN:{handle}", economy=economy, title=title[:200],
        # The title carries the section so live-mode dedup keeps each one; the Law Name
        # column must carry only the Act.
        law_name=act,
        # The citable public URL, not the API endpoint — the Source URL column has to be
        # something a reviewer can open.
        source_url=f"https://indiacode.gov.in/handle/{handle}",
        portal=src.get("name", "India Code"), fmt=DocFormat.HTML,
        law_number=(f"Act {number} of {year}" if number and year else None),
        relevance_score=round(float(score), 4), discovery_tag=DiscoveryTag.NEW,
        amendment_date=(year or None))


#: India Code renders amended text with the publisher's own footnote marker: `1 [40A. Duties
#: of subscriber …]`. That is editorial apparatus, not the statute, and it also hides the
#: section marker behind a digit.
#: `[\[\]]` because the portal's own rendering is not consistent: s.70B of the IT Act opens
#: `1 ]70B. Indian Computer Emergency Response Team …` — a closing bracket where the marker
#: opens. Matching only `[` left that section with no readable marker.
_FOOTNOTE_LEAD = re.compile(r"^\d+\s*[\[\]]\s*")
#: The same apparatus with the footnote number absent: s.79A opens `[79A. Central Government …`.
_BRACKET_LEAD = re.compile(r"^\[\s*")


def body_text(item: dict) -> str:
    """The section's text with exactly one section marker, at the front.

    India Code publishes `section_page_note` in four shapes, and the difference is invisible
    until something reads the marker. Measured across the Information Technology Act 2000 and
    the DPDP Act 2023: 64 sections open on `(1)`, 53 on prose, 33 on a footnote marker, 16 on
    their own number, 3 on a number with a space before the stop.

    The old seed prepended `{sec}. ` to all of them, so a third of the Act came out as
    `69B. 1 [69B. Power to authorise …` and `21. 21. Licence to issue …`. A doubled marker is
    not a marker: `_boundaries` requires a non-digit after the stop — otherwise every "26. 3"
    cross-reference in a statute would open a new provision — so it found nothing, the whole
    section fell to the whole-document fallback, and 53 of the Act's 125 sections were cited
    as "(document)" with no article number at all. The citation column is the row's
    checkability, so that is a submission defect, not a cosmetic one.
    """
    text = section_text(item)
    if not text:
        return ""
    sec = _md(item, "dc.identifier.section_number")
    own_number = re.compile(r"^" + re.escape(sec) + r"\s*\.\s*") if sec else None
    # Peel the publisher's apparatus off the front until the statute's own words are first.
    # Order is not fixed — `1 [40A. Duties …`, `72A. 2 [Penalty] …`, `91 . [ Amendment …` — so
    # this loops rather than applying a fixed sequence.
    for _ in range(4):
        before = text
        text = _FOOTNOTE_LEAD.sub("", text).lstrip()
        text = _BRACKET_LEAD.sub("", text).lstrip()
        if own_number:
            text = own_number.sub("", text).lstrip()
        if text == before:
            break
    # A bracket the leading marker opened is now unmatched. Drop the surplus closer so the
    # snippet neither ends nor opens on punctuation the statute did not write.
    while text.count("]") > text.count("["):
        i = text.rfind("]")
        text = text[:i] + text[i + 1:]
    if sec:
        # Re-add the marker once, in the canonical form. `_NUMBERED_RE` requires a CAPITAL
        # after the stop — the guard that stops every "26. 3" cross-reference in a statute from
        # opening a new provision — so the peeling above is what makes the marker readable.
        text = f"{sec}. {text}"
    return text.strip()


#: India Code keeps repealed sections in place, with the repeal recorded in the text rather
#: than in `dc.identifier.repealed`: "[Composition of Cyber Appellate Tribunal.] Omitted by the
#: Finance Act, 2017 (7 of 2017), s. 169". The in-force flag says nothing, so without this the
#: Act's omitted sections are graded and can be cited — and a repealed provision scores zero.
_OMITTED = re.compile(r"\bomitted\s+by\b|\brepealed\s+by\b", re.I)


def is_omitted(item: dict) -> bool:
    return bool(_OMITTED.search(section_text(item)[:200]))


def _seed(item: dict, doc: DiscoveredDoc, log) -> None:
    """Put the section's text where `fetch` will find it.

    The text arrived with the search result and the citable HTML page 502s today, so this is
    not a shortcut around fetching — it is the only way the body is available at all. It is
    also why an India run finishes in seconds with no OCR: there is no PDF to download and no
    image layer to read, which is a property of this portal rather than a step being skipped.
    """
    heading = (item.get("name") or "").strip()
    body = (f"<html><body><h1>{heading}</h1>"
            f"<p>{body_text(item)}</p></body></html>").encode("utf-8")
    try:
        from .fetch import seed_cache
        seed_cache(doc.source_url, body, "text/html", log=lambda _m: None)
    except Exception as exc:                 # noqa: BLE001 — discovery still stands
        log(f"[discovery] could not seed India section {doc.doc_id}: {type(exc).__name__}")


def _search_in_dspace(client, src: dict, query: str, economy: Economy, indicators,
                      log) -> list[DiscoveredDoc]:
    """Adapter entry point, matching the signature `discovery` dispatches on.

    Returns one DiscoveredDoc per SECTION of every Act this query points at. That is
    deliberate and different from the other economies, where a document is an Act and
    extraction splits it: here the portal has already done the splitting, and re-joining
    sections into a synthetic Act only to split them again would reintroduce exactly the
    boundary errors this source lets us avoid.

    An Act already harvested by an earlier query is re-emitted with its updated cumulative
    score rather than re-fetched — `discovery` keeps the higher-scoring copy of a URL, so the
    score that survives is the one from the last query to name the Act, which is the total.
    """
    state = _run_state(client)
    phrase = as_phrase(query)
    try:
        total, acts = phrase_acts(client, phrase)
    except Exception as exc:                     # noqa: BLE001 — one dead query is not fatal
        log(f"[discovery] India Code API failed for {phrase!r}: {type(exc).__name__}: {exc}")
        return []
    if not acts:
        log(f"[discovery] India Code: no in-force Central sections for {phrase!r}")
        return []

    weight = phrase_weight(total)
    out: list[DiscoveredDoc] = []
    for act, hits in acts.most_common(MAX_ACTS_PER_QUERY):
        state["score"][act] += hits * weight
        score = state["score"][act]
        cached = state["docs"].get(act)
        if cached is None:
            try:
                items = act_sections(client, act, log=log)
            except Exception as exc:             # noqa: BLE001 — one dead Act is not fatal
                log(f"[discovery] India Code: could not harvest {act!r}: "
                    f"{type(exc).__name__}: {exc}")
                continue
            cached = []
            for item in items:
                doc = _doc(item, src, economy, score)
                if doc is None:
                    continue
                _seed(item, doc, log)
                cached.append(doc)
            state["docs"][act] = cached
            log(f"[discovery] India Code: {phrase!r} -> {act!r} "
                f"({hits} phrase hits, {len(cached)} sections)")
        for doc in cached:
            out.append(doc.model_copy(update={"relevance_score": round(float(score), 4)}))
    if len(acts) > MAX_ACTS_PER_QUERY:
        log(f"[discovery] India Code: {phrase!r} named {len(acts)} Acts, kept the top "
            f"{MAX_ACTS_PER_QUERY}")
    return out
