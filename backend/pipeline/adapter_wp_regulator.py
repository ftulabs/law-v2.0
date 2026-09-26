"""A regulator's own publication listing, read from its WordPress REST index.

WHY THIS LANE EXISTS. Much of what the panel cites for Malaysia is not an Act: the Cross
Border Personal Data Transfer Guideline (6.4), the DPO and DPIA guidelines (7.4), the Data
Breach Notification guideline, the sectoral Codes of Practice and the PDP Standard 2015. They
are published by the regulator (pdp.gov.my), not by the statute portal, and the only lane that
reached them was a `site:`-scoped web search. On 2026-09-26 that lane returned NOTHING: Serper
answered "Not enough credits", DuckDuckGo a challenge page and Mojeek 403, so every one of its
five queries came back empty and the run went ahead on statutes alone. The 2026-09-25 run that
did reach some codes was reading search results cached before the key ran dry.

WHAT IT READS. The site's own index, not a search engine's copy of it. pdp.gov.my runs
WordPress, whose REST API lists every public post type — `/wp-json/wp/v2/types`, then each
collection 100 items a page. Measured 2026-09-26: 5 collections, 472 items; the regulator's
publication listing is the custom `docs` type (90 items, 45 per language), each an HTML page
titled with the instrument's real name ("Personal Data Protection Guidelines on the
Appointment of Data Protection Officer (DPO)") whose body links the PDF. Media attachments
(315) supply the file for anything published without such a page. Nothing here names a
document: the site root is configuration (`base_url`), and what is taken from it is decided by
the instrument's KIND and its relevance to the PILLAR being run.

WHAT IT KEEPS, and why each rule is general:

* A document file (PDF/Word) on the same host — an image or an HTML shell is not a text to
  quote.
* Not a consultation draft (`rdtii.instrument` says DRAFT): the site publishes the draft of
  each guideline beside its final text, and 13 of its 45 English items are drafts.
* Not an Act. The statute portal is the authoritative source for Acts and already carries
  them; the regulator's copy (Act 709, Act A1727) would take a second slot for the same law.
  A regulator's subsidiary instruments — Regulations, Orders, Standards, Circulars — stay:
  the AGC "updated" catalogue lists principal Acts only, so this is the only lane that
  reaches them.
* The preferred language first. A multilingual WordPress routes each language under its own
  path segment (pdp.gov.my: `/ppdpv1/en/akta/…` English, `/ppdpv1/akta/…` Malay), which is a
  property of the site, not of any document. Items in another language are demoted, not
  dropped, because an instrument published in one language only must still be reachable.

HOW IT RANKS. Instrument kind (code, standard, regulations → full weight; guideline, circular → 0.8;
user manuals and quick guides → low), times the language factor, plus the pillar's concept
vocabulary in the title and filename (`confidence._PILLAR_CONCEPT_TERMS`, less the words every
title on a data-protection site carries). The lane keeps its best `max_docs` (default 8); the
discovery-wide cap then decides how many of those fit beside the statutes.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

from ..schemas import DiscoveredDoc, DocFormat, Economy
from . import portal

#: WordPress types that hold site machinery, never a publication. Same list the corpus
#: sweep (`backend/corpus/regulator.py`) uses — the live pipeline may not import that package.
_SKIP_TYPES = {"nav_menu_item", "wp_block", "wp_template", "wp_template_part",
               "wp_global_styles", "wp_navigation", "wp_font_family", "wp_font_face",
               "elementor_library", "wppopups-templates"}

_DOC_EXT_RE = re.compile(r"\.(pdf|docx?)(?:$|[?#])", re.I)
_HREF_RE = re.compile(r'href="([^"\s]+)"', re.I)

# The KIND of instrument, English and Malay. Deliberately about form, never subject. A
# BINDING instrument (a registered code of practice, a standard, regulations, an order) ranks
# above ADVISORY guidance at equal topicality: the RDTII scores measures, and under the PDPA a
# registered code binds its sector while a guideline explains.
_BINDING_RE = re.compile(
    r"\b(code[s]? of practice|practices|standards?|regulations?|order|rules|directions?|"
    r"tataamalan|kod amalan|piawaian|peraturan|perintah)\b", re.I)
_ADVISORY_RE = re.compile(
    r"\b(guidelines?|guidance|circulars?|notice|framework|garis panduan|pekeliling)\b", re.I)
#: Help material: how to use a portal or fill a form. Real, official, and not an instrument.
_HELP_RE = re.compile(
    r"\b(manual|user guide|quick guide|registration guide|faq|infographic|brochure|poster|"
    r"pengguna|panduan pendaftaran|annual report|laporan tahunan|newsletter|slides?)\b", re.I)
#: PROCEDURAL subsidiary instruments — fees, compounding of offences, registration forms,
#: an appointment or a commencement notice. Binding, but they administer the regime rather
#: than state its rules, so none of them can be evidence for a pillar-6/7 indicator. Without
#: this the "Regulations (Fees)" and "(Compounding of Offences)" ranked level with the codes
#: of practice and, on the site's own ordering, ahead of the PDP Standard 2015.
_PROCEDURAL_RE = re.compile(
    r"\b(fees?|compound(?:ing)?|offences|registration|appointment of (?:the )?(?:personal data "
    r"protection )?commissioner|commencement|coming into operation|class of data users|"
    r"kompaun|pendaftaran|permulaan|penetapan tarikh)\b", re.I)
#: An Act, i.e. primary legislation, and nothing subsidiary in the same title.
_ACT_RE = re.compile(r"\b(act|akta)\b", re.I)
_SUBSIDIARY_RE = re.compile(
    r"\b(regulations?|order|rules|standards?|guidelines?|code[s]? of practice|circulars?|"
    r"peraturan|perintah|piawaian|pekeliling|garis panduan)\b", re.I)

#: Concept words every title on a data-protection regulator's site carries; counting them
#: would give every document the same topical score.
_GENERIC_CONCEPTS = {"personal data", "personal information", "data protection", "privacy",
                     "process", "collect", "data", "information", "access", "disclos",
                     "consent", "store", "storage", "located", "domestic", "period"}

# One enumeration per site per process: a P6+P7 run asks twice and the index is the same.
_site_cache: dict[str, list[tuple[str, str, str]]] = {}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _stem(url: str) -> str:
    from urllib.parse import unquote
    s = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return re.sub(r"[-_]+", " ", _DOC_EXT_RE.sub("", s)).strip()


def enumerate_site(client, base: str, log, max_pages: int = 10) -> list[tuple[str, str, str]]:
    """Every document file the site's REST index links → [(file_url, title, page_link)].

    A file reached from a CONTENT item takes that item's title and permalink (the name a
    reader knows it by, and the page that states its language); a file known only as a media
    attachment keeps the attachment's title, which is usually its filename.
    """
    root = base.rstrip("/")
    if root in _site_cache:
        return _site_cache[root]
    host = urlparse(root).netloc.lower()
    if not portal._allowed(root + "/wp-json/wp/v2/types", log):
        _site_cache[root] = []
        return []
    try:
        r = client.get(f"{root}/wp-json/wp/v2/types")
        types = r.json() if r.status_code == 200 else {}
    except Exception as e:  # noqa: BLE001 — not a WordPress site, or not today
        log(f"[regulator] {host}: no WordPress REST index ({type(e).__name__})")
        types = {}
    bases = []
    for slug, meta in (types or {}).items():
        rest = (meta or {}).get("rest_base") or slug
        if slug in _SKIP_TYPES or "(?P<" in rest:
            continue
        bases.append(rest)
    content: dict[str, list[tuple[str, str]]] = {}   # file url -> [(title, page link), ...]
    media: dict[str, tuple[str, str]] = {}
    for rest in bases:
        for page in range(1, max_pages + 1):
            try:
                resp = client.get(f"{root}/wp-json/wp/v2/{rest}",
                                  params={"per_page": "100", "page": str(page)})
                items = resp.json() if resp.status_code == 200 else []
            except Exception:  # noqa: BLE001
                break
            if not isinstance(items, list) or not items:
                break
            for it in items:
                title = _clean((it.get("title") or {}).get("rendered", ""))
                link = str(it.get("link") or "")
                src = str(it.get("source_url") or "")
                if src and _DOC_EXT_RE.search(src):
                    media.setdefault(src, (title or _stem(src), link))
                body = (it.get("content") or {}).get("rendered", "") or ""
                for href in _HREF_RE.findall(body):
                    url = urljoin(root + "/", html.unescape(href))
                    if not _DOC_EXT_RE.search(url):
                        continue
                    if not urlparse(url).netloc.lower().endswith(host.removeprefix("www.")):
                        continue
                    # Several content items can link ONE file — pdp.gov.my publishes each
                    # instrument's page once per language and both pages link the same
                    # English PDF. All are kept; `rank` picks the page in the preferred
                    # language. Keeping "the longer title" instead chose the Malay page for
                    # the PDP Standard 2015 and the aviation code (their Malay titles are a
                    # few characters longer) and demoted both out of the lane.
                    pair = (title or _stem(url), link)
                    if pair not in content.setdefault(url, []):
                        content[url].append(pair)
            total = int(resp.headers.get("X-WP-TotalPages") or 0)
            if not total or page >= total:
                break
    out = [(u, t, l) for u, pairs in content.items() for t, l in pairs]
    out += [(u, t, l) for u, (t, l) in media.items() if u not in content]
    only_media = sum(1 for u in media if u not in content)
    log(f"[regulator] {host}: REST index, {len(bases)} collections -> {len(content)} files "
        f"named by a publication page, {only_media} by attachment only")
    _site_cache[root] = out
    return out


def _pillars(indicators) -> set[int]:
    return {int(ind.pillar) for ind in indicators or [] if getattr(ind, "pillar", None)}


def _concepts(pillars: set[int]) -> list[str]:
    from .confidence import _PILLAR_CONCEPT_TERMS
    out: list[str] = []
    for p in sorted(pillars):
        out += [t for t in _PILLAR_CONCEPT_TERMS.get(p, ()) if t not in _GENERIC_CONCEPTS]
    return list(dict.fromkeys(out))


def rank(cands: list[tuple[str, str, str]], indicators, *, prefer_language: str | None = "en",
         ) -> list[tuple[float, str, str]]:
    """Score each candidate for the pillar(s) behind `indicators` → [(score, url, title)],
    best first, with drafts and Acts removed. Pure: no network, unit-tested on a fixture."""
    from ..rdtii import instrument
    concepts = _concepts(_pillars(indicators))
    seg = f"/{prefer_language.strip('/').lower()}/" if prefer_language else None
    # Only demote by language on a site that actually routes languages by path segment.
    routed = bool(seg) and any(seg in (link or "").lower() for _, _, link in cands)
    # One entry per FILE: the page in the preferred language names it, else the fullest name.
    best: dict[str, tuple[str, str]] = {}
    for url, title, link in cands:
        prev = best.get(url)
        if prev is None:
            best[url] = (title, link)
            continue
        pref_new = bool(routed and seg in (link or "").lower())
        pref_old = bool(routed and seg in (prev[1] or "").lower())
        if (pref_new, len(title)) > (pref_old, len(prev[0])):
            best[url] = (title, link)
    scored: list[tuple[float, str, str]] = []
    for url, (title, link) in best.items():
        if instrument.classify(title) is instrument.Status.DRAFT:
            continue
        if _ACT_RE.search(title) and not _SUBSIDIARY_RE.search(title):
            continue                      # an Act: the statute portal's lane owns it
        blob = f"{title} {_stem(url)}".lower()
        if _HELP_RE.search(blob):
            kind = 0.3
        elif _PROCEDURAL_RE.search(blob):
            kind = 0.4
        elif _BINDING_RE.search(blob):
            kind = 1.0
        elif _ADVISORY_RE.search(blob):
            kind = 0.8
        else:
            kind = 0.6
        hits = sum(1 for c in concepts if c in blob)
        topical = min(1.0, hits / 2.0)
        lang = 1.0 if (not routed or seg in (link or "").lower()) else 0.5
        scored.append((round(lang * (0.5 * kind + 0.5 * topical), 4), url, title))
    scored.sort(key=lambda s: -s[0])      # stable: ties keep the site's own order
    return scored


def search_wp_regulator(client, src: dict, query: str, economy: Economy, indicators,
                        log) -> list[DiscoveredDoc]:
    """The lane: enumerate, rank for this pillar, keep the best `max_docs`.

    Scores map onto 0.60–0.95 — the same floor the regulator's web-search lane uses, so these
    instruments stay in contention under the global cap without outranking a statute the
    portal matched by name (1.0)."""
    base = src.get("api_base") or src.get("base_url") or ""
    if not base:
        return []
    cands = enumerate_site(client, base, log, max_pages=int(src.get("max_pages") or 10))
    ranked = rank(cands, indicators, prefer_language=src.get("prefer_language", "en"))
    keep = ranked[: int(src.get("max_docs") or 8)]
    if ranked:
        log(f"[regulator] {urlparse(base).netloc}: {len(ranked)} instruments after drafts/Acts "
            f"removed; keeping {len(keep)}: " + "; ".join(t[:50] for _, _, t in keep[:4]))
    name = src.get("name", urlparse(base).netloc)
    return [portal.make_doc(economy, url, title, name, fmt=DocFormat.PDF_TEXT
                            if url.lower().split("?")[0].endswith(".pdf") else None,
                            score=round(0.60 + 0.35 * s, 4))
            for s, url, title in keep]


portal.register("wp_regulator", search_wp_regulator, enumerates_portal=True)
