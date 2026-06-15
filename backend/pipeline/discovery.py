"""ZONE 1 — Legal discovery.

Two modes:
  • sample mode (default for demo): reads bundled docs from data/samples/<economy>/
    and the manifest in data/samples/manifest.yaml. Deterministic, offline.
  • live mode (optional): a polite HTTP crawler skeleton that hits a portal's
    search endpoint, fetches result pages, and classifies format. Wire real
    portals via data/sources.yaml. Playwright/Scrapy can drop in behind the same
    interface for JS-heavy portals.

Both modes return ranked DiscoveredDoc records tagged KNOWN/NEW. "KNOWN" = present
in the reference manifest; "NEW" = surfaced beyond the sample set (live crawl, or a
sample explicitly flagged new).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from ..config import ROOT, settings
from ..rdtii import get_indicators
from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, Indicator

SAMPLES_DIR = ROOT / "data" / "samples"
MANIFEST = SAMPLES_DIR / "manifest.yaml"


def _doc_id(economy: str, source_url: str) -> str:
    return f"{economy}-" + hashlib.sha1(source_url.encode()).hexdigest()[:10]


def _score(text_blob: str, indicators: list[Indicator]) -> float:
    """Relevance = indicator query-term coverage over the doc's searchable text."""
    blob = text_blob.lower()
    all_terms = {t.lower() for ind in indicators for t in ind.query_terms}
    if not all_terms:
        return 0.0
    hits = sum(1 for t in all_terms if t in blob)
    return round(min(1.0, hits / max(4, len(all_terms) * 0.25)), 3)


# Over-generic words that appear in almost any legal text — kept out of the snippet vocabulary
# so they don't give an off-topic law spurious relevance (the snippet gate ranks on the
# DISTINCTIVE indicator vocabulary: server/centre/cross-border/stored/transfer/…, not "data").
_RELEVANCE_STOP = {
    "data", "personal", "information", "protection", "shall", "with", "within", "must", "this",
    "that", "from", "into", "under", "such", "which", "person", "public", "national", "country",
    "territory", "located", "individual", "least", "level", "standard", "where", "unless", "been",
}


def _snippet_relevance(text_blob: str, indicators: list[Indicator]) -> float:
    """Word-level indicator-term coverage — the right signal for a short SEARCH SNIPPET.

    `_score` matches whole query phrases ("data shall be stored in"), which a Google snippet
    almost never reproduces verbatim, so it would score real snippets 0 and silently disable the
    gate. Here we split the query terms into their DISTINCTIVE words (server, centre, cross-border,
    stored, transferred, infrastructure …) and measure how many appear in the title+snippet. An
    on-topic law (Companies Act snippet: 'accounting records … stored … transfer … approval')
    covers several; an off-topic one (Gambling: 'license … casino') covers none. Generic legal
    words are dropped (see _RELEVANCE_STOP) so coverage reflects topical fit, not boilerplate."""
    blob = text_blob.lower()
    vocab: set[str] = set()
    for ind in indicators:
        for term in ind.query_terms:
            for w in re.findall(r"[a-z][a-z-]{3,}", term.lower()):
                if w not in _RELEVANCE_STOP:
                    vocab.add(w)
    if not vocab:
        return 0.0
    hits = sum(1 for w in vocab if w in blob)
    return round(hits / len(vocab), 4)


# ─────────────────────── version-resolution helpers (live mode) ──────────────
_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')
_AMEND_RE = re.compile(r'\b(amendments?|amending|supplementary|supplemental)\b', re.I)
_CONSOL_RE = re.compile(r'\b(consolidated|compilation|reprint|revised|current)\b', re.I)
_DEAD_URL_RE = re.compile(r'historical|repealed|superseded|revoked|expired|mansuh|archive', re.I)
# Strip disambiguation suffixes like "(No. 2)", "No.3", "(Number 2)" so that
# "Overseas Telecommunications Act (No. 2) 1968" groups with "... Act 1946" etc.
_LAWNO_RE = re.compile(r'\(?\bno\.?\s*\d+\b\)?|\bnumber\s+\d+\b', re.I)

# Search-result title noise: engines prefix "[PDF]"/"PDF"/"DOC" and append the portal
# name/domain ("… - Singapore Statutes Online", "… | lom.agc.gov.my"). Stripping this so
# that "Personal Data Protection Act 2012 - Singapore Statutes Online" and "Personal Data
# Protection Act 2012" collapse to ONE law instead of being fetched + extracted twice.
_TITLE_PREFIX_RE = re.compile(r'^\s*(\[?\b(?:pdf|doc|docx|html|htm)\b\]?[\s\-–—:|]*)+', re.I)
_PORTAL_SUFFIX_RE = re.compile(
    r'[\s\-–—|]+(?:singapore statutes online|laws of malaysia|'
    r'malaysia federal legislation|federal register of legislation|'
    r"attorney[- ]general'?s? chambers|"
    r'(?:[\w-]+\.)+(?:gov|com|org|net|go|nic|int|edu)(?:\.[a-z]{2})?)\s*$', re.I)
# Titles a search engine returns for a portal nav/landing page — never a real law name.
# When the title IS one of these, dedup must key off the URL (not the title) so several
# distinct laws sharing the same generic portal <title> are not collapsed into one.
_GENERIC_TITLE_RE = re.compile(
    r'^\s*(?:malaysia federal legislation|singapore statutes online|laws of malaysia|'
    r'federal register of legislation|attorney[- ]general|home|search(?: results?)?|'
    r'untitled|document|pdf'
    # law-type + bare number/code only ("Act A1727", "Akta 709") — no descriptive name
    r'|(?:act|akta|ordinance|enactment|p\.?u\.?)\s*\(?[a-z]?\d+[a-z]?\)?'
    r')\s*$', re.I)

# Malaysia (MY): detect language so we can prefer the English versions. lom.agc.gov.my
# encodes language in the PATH and filename, NOT in a vague 'akta' token (every act lives
# under /portal/akta/, English and Malay alike — matching 'akta' misclassifies them all):
#   English: /akta/LOM/EN/Act 709 ….pdf, …_BI/… folders, ?language=BI, filename "Act …"
#   Malay:   /akta/…/BM/Akta A1727.pdf,  …_BM/… folders, ?language=BM, filename "Akta …"
# (AGC uses BI = Bahasa Inggeris = English, BM = Bahasa Malaysia = Malay.)
_MY_MALAY_TITLE_RE = re.compile(
    r'\b(akta|perlindungan|peribadi|pindaan|kaedah|warta|jadual|bahagian|peraturan)\b', re.I)
_MY_ENGLISH_URL_RE = re.compile(r'/en/|_bi[/.]|[?&]lang(?:uage)?=bi\b|/act[ %_]', re.I)
_MY_MALAY_URL_RE = re.compile(r'/bm/|_bm[/.]|[?&]lang(?:uage)?=bm\b|/akta[ %_]', re.I)
# MY law identity: the act number (709, A1727) shared by every language/reprint/landing form.
_MY_ACT_RE = re.compile(r'(?:[?&]act=|/(?:act|akta)[ %_]+)([A-Za-z]?\d+[A-Za-z]?)\b', re.I)

# A title that contains one of these reads like a real law name (vs a section heading
# such as "Transfer of Personal Data Outside Singapore").
_LAW_NAME_HINT_RE = re.compile(
    r"\b(act|akta|ordinance|enactment|regulations?|rules|by[- ]?laws?|code|decree|order)\b",
    re.I)

# Singapore SSO statute identity from the URL. The portal exposes the SAME instrument under
# many landing URLs (a consolidated /SL/ view, an as-published /SL-Supp/.../Published/
# snapshot, and per-provision ?ProvIds= slices) with unrelated titles — but every URL
# carries the unique subsidiary-legislation number, e.g. S63-2021. Keying dedup on that
# number collapses all of them into one law even when titles and bytes differ.
_SG_SL_RE = re.compile(r"S(\d+)-((?:19|20)\d{2})", re.I)


def _sg_statute_id(url: str) -> str | None:
    from urllib.parse import unquote, urlsplit
    path = unquote(urlsplit(url).path)
    m = _SG_SL_RE.search(path)
    if m:
        return f"sl-s{m.group(1)}-{m.group(2)}"
    # principal Acts: /Act/PDPA2012, /Acts-Supp/1-2026/...
    m = re.search(r"/(?:act|acts-supp)/([a-z0-9]+(?:-\d+)?)", path, re.I)
    if m:
        return f"act-{m.group(1).lower()}"
    return None


def _is_as_published(url: str) -> bool:
    """SG as-published snapshot (…/Published/<timestamp>) — the as-made text, superseded by
    the consolidated in-force view of the same statute."""
    return "/published/" in url.lower()


def _is_malay_my(d: DiscoveredDoc) -> bool:
    """MY: True for a Bahasa-Malaysia document. English markers (path /EN/, _BI suffix,
    ?language=BI, filename 'Act …') win over Malay markers so the portal's /portal/akta/
    directory — present on EVERY act — never misclassifies an English PDF as Malay."""
    url = d.source_url.lower()
    if _MY_ENGLISH_URL_RE.search(url):
        return False
    if _MY_MALAY_URL_RE.search(url):
        return True
    return bool(_MY_MALAY_TITLE_RE.search(d.title))


def _my_act_id(url: str, title: str = "") -> str | None:
    """MY act number (709, A1727) from the URL query (?act=709) or the PDF filename
    ('Act 709 …pdf', 'Akta A1727.pdf') — the identity shared across every reprint, language
    and landing-page form of the same act, so all of them collapse to one law."""
    from urllib.parse import unquote
    m = _MY_ACT_RE.search(unquote(url))
    return f"my-{m.group(1).lower()}" if m else None


def _clean_title(title: str) -> str:
    """Strip search-engine format prefixes and trailing portal-name/domain noise."""
    t = _TITLE_PREFIX_RE.sub('', title or '')
    # A title may carry several portal suffixes ("… - AGC - lom.agc.gov.my"); peel repeatedly.
    prev = None
    while prev != t:
        prev = t
        t = _PORTAL_SUFFIX_RE.sub('', t).strip()
    return t.strip()


def _is_generic_title(title: str) -> bool:
    """True when the title is not a usable law name — a portal nav/landing label, a bare
    law number, or a filename/UUID blob (e.g. 'PDF bc248903-f874-…'). Such titles trigger
    content-based name recovery at extraction time."""
    cleaned = _clean_title(title)
    if not cleaned.strip():
        return True
    if _GENERIC_TITLE_RE.match(cleaned):
        return True
    # no real word (≥4 consecutive letters) → a UUID / filename / number blob, not a name
    if not re.search(r"[A-Za-z]{4,}", cleaned):
        return True
    return False


def _latest_year(*texts: str) -> int:
    """Highest 19xx/20xx year found across the given strings (0 if none)."""
    years = [int(m.group(0)) for s in texts if s for m in _YEAR_RE.finditer(s)]
    return max(years) if years else 0


def _law_key(title: str) -> str:
    """Canonical key for grouping law variants.

    Strips: portal/format noise, years (1988, 2012…), 'Amendment/Amending',
    'Consolidated/Compilation', and disambiguation suffixes like '(No. 2)' so that e.g.
    all variants of 'Overseas Telecommunications Act' — and the same Act surfaced under a
    "… - Singapore Statutes Online" search title — collapse to one group.
    """
    t = _clean_title(title)
    t = _YEAR_RE.sub('', t)
    t = _AMEND_RE.sub('', t)
    t = _CONSOL_RE.sub('', t)
    t = _LAWNO_RE.sub('', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip().lower()


def _url_law_key(url: str) -> str:
    """Fallback grouping key from a URL's filename/last path segment, used when the title
    is generic (e.g. MY's portal-wide "Malaysia Federal Legislation" <title>). Keeps the
    document distinct (akta_709 ≠ akta_855) while collapsing pure query-string variants of
    the same path. Years/'reprint' are stripped so 'akta709reprint2023' ≈ 'akta709'."""
    from urllib.parse import urlsplit
    path = urlsplit(url).path.rsplit('/', 1)[-1] or urlsplit(url).path
    stem = re.sub(r'\.(pdf|html?|docx?|txt)$', '', path, flags=re.I)
    stem = re.sub(r'[_\-.]+', ' ', stem)            # underscores would block \b boundaries
    stem = _CONSOL_RE.sub('', _YEAR_RE.sub('', stem))
    return re.sub(r'[^a-z0-9]', '', stem.lower()) or url.lower()


def _dedup_key(d: DiscoveredDoc) -> str:
    """Grouping key for a document.

    SG: key on the SSO statute number from the URL (the only stable identity — titles are
    section headings / UUIDs / portal labels). Otherwise: cleaned-title law key, falling
    back to a URL key when the title is a generic portal label (so distinct laws with
    identical portal <title>s don't merge)."""
    if d.economy.value == "SG":
        sid = _sg_statute_id(d.source_url)
        if sid:
            return "sg:" + sid
    if d.economy.value == "MY":
        aid = _my_act_id(d.source_url, d.title)
        if aid:
            return aid
    if _is_generic_title(d.title):
        return "url:" + _url_law_key(d.source_url)
    return _law_key(d.title) or ("url:" + _url_law_key(d.source_url))


def _is_superseded(url: str, title: str) -> bool:
    """True when URL or title signals the document is no longer in force."""
    return bool(_DEAD_URL_RE.search(url) or _DEAD_URL_RE.search(title))


def _pick_best(docs: list[DiscoveredDoc]) -> DiscoveredDoc:
    """From a group of same-law docs pick the most current IN-FORCE version.

    Ranking (higher wins): in-force > principal(non-amendment) > consolidated > NEWEST
    year > later amendment_date. The year term is the fix for "kept the 2 oldest" — when
    amendment_date is absent (web-search docs), the year parsed from the title breaks the
    tie toward the latest revision instead of falling back to first-encountered (oldest).
    """
    if len(docs) == 1:
        return docs[0]

    def _key(d: DiscoveredDoc) -> tuple:
        alive = 0 if _is_superseded(d.source_url, d.title) else 1
        # In-force consolidated view beats an as-published /Published/ snapshot of same law
        not_aspublished = 0 if _is_as_published(d.source_url) else 1
        # Prefer English over Bahasa Malaysia (English-only cross-encoder), and a direct PDF
        # over an act-detail landing page (it still resolves, but the PDF needs no round-trip)
        english = 0 if (d.economy.value == "MY" and _is_malay_my(d)) else 1
        direct_pdf = 1 if d.source_url.lower().endswith(".pdf") else 0
        # A proper law-name title ("… Regulations 2021") beats a section-heading or UUID
        # title ("Transfer of Personal Data Outside Singapore"), so the kept doc is named.
        has_lawname = 1 if _LAW_NAME_HINT_RE.search(_clean_title(d.title)) else 0
        consolidated = 1 if _CONSOL_RE.search(d.title) else 0
        # Base acts (e.g. "Privacy Act") outrank amendment-only acts
        is_amendment = 0 if _AMEND_RE.search(d.title) else 1
        year = _latest_year(d.amendment_date or "", d.title)
        date = d.amendment_date or "0000-00-00"
        return (alive, english, not_aspublished, has_lawname, is_amendment, consolidated,
                direct_pdf, year, date)

    return max(docs, key=_key)


def _dedup_by_law_title(docs: list[DiscoveredDoc]) -> list[DiscoveredDoc]:
    """Collapse multiple versions/compilations of the same law into the best one.

    Steps:
    1. Pre-filter: remove documents whose URL or title signals they are no longer in
       force (repealed, historical, superseded, …).  If ALL docs would be removed we
       keep the full list so the caller surfaces a real discovery failure rather than
       silently returning nothing.
    2. Group remaining docs by a normalised title key (years, 'amendment', and
       'consolidated' words stripped).
    3. Within each group pick the most current/consolidated/in-force document.

    Applied exclusively in live mode so the manually-curated sample corpus is untouched.
    """
    alive = [d for d in docs if not _is_superseded(d.source_url, d.title)]
    working = alive if alive else docs   # safety: never return empty when input isn't

    groups: dict[str, list[DiscoveredDoc]] = {}
    for d in working:
        groups.setdefault(_dedup_key(d), []).append(d)
    return [_pick_best(g) for g in groups.values()]


def _prefer_english_my(docs: list[DiscoveredDoc]) -> list[DiscoveredDoc]:
    """MY only: drop Malay-language documents when an English version exists.

    lom.agc.gov.my publishes most Acts in both Bahasa Malaysia and English.
    Processing Malay text with an English-only cross-encoder degrades retrieval
    quality, so we filter them out.  Falls back to the full list when NO English
    document can be identified (e.g. the act was never translated), so we still
    surface something rather than returning nothing.
    """
    english = [d for d in docs if not _is_malay_my(d)]
    return english if english else docs


def _clean_source_url(economy: Economy, url: str) -> str:
    """SG: drop the section-specific query (?ProvIds=pr26-, DocDate, ViewType) so the cited
    Source URL points to the LAW, not to whichever provision the search engine happened to
    index — otherwise every section of an Act links to, say, section 26. The whole-Act page
    is a correct, stable citation; a precise per-section anchor isn't reconstructable here."""
    if economy.value != "SG":
        return url
    from urllib.parse import urlsplit, urlunsplit
    s = urlsplit(url)
    return urlunsplit((s.scheme, s.netloc, s.path, "", ""))


def _drop_amendment_docs(docs: list[DiscoveredDoc]) -> list[DiscoveredDoc]:
    """Drop standalone Amendment instruments. SG SSO publishes CONSOLIDATED in-force texts —
    the principal Act/Regulations already incorporate their amendments — so fetching e.g.
    'Personal Data Protection (Amendment) Regulations 2026' separately just re-extracts
    changes already present in the consolidated 'Personal Data Protection Regulations 2021'.
    Keeps the full list if EVERYTHING is an amendment, so a run never returns nothing."""
    principal = [d for d in docs if not _AMEND_RE.search(d.title)]
    return principal if principal else docs


# ─────────────────────────── sample mode ───────────────────────────
def discover_from_samples(economy: Economy, pillar: int | None = None) -> list[DiscoveredDoc]:
    if not MANIFEST.exists():
        return []
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    indicators = get_indicators(pillar)
    docs: list[DiscoveredDoc] = []
    for entry in manifest.get("documents", []):
        if entry.get("economy") != economy.value:
            continue
        local = SAMPLES_DIR / entry["path"]
        searchable = entry.get("title", "")
        # include first chunk of the file so ranking sees the body, not just title
        if local.exists() and local.suffix in {".html", ".txt"}:
            searchable += " " + local.read_text(encoding="utf-8", errors="ignore")[:4000]
        sidecar = local.with_suffix(".ocr.txt")
        if sidecar.exists():
            searchable += " " + sidecar.read_text(encoding="utf-8", errors="ignore")[:4000]

        doc = DiscoveredDoc(
            doc_id=_doc_id(economy.value, entry["source_url"]),
            economy=economy,
            title=entry["title"],
            source_url=entry["source_url"],
            portal=entry.get("portal", "sample"),
            fmt=DocFormat(entry.get("format", "html")),
            amendment_date=entry.get("amendment_date"),
            law_number=entry.get("law_number"),
            relevance_score=_score(searchable, indicators),
            discovery_tag=DiscoveryTag(entry.get("discovery_tag", "KNOWN")),
            local_path=str(local),
        )
        docs.append(doc)
    # prioritise recently amended + relevant
    docs.sort(key=lambda d: (d.relevance_score, d.amendment_date or ""), reverse=True)
    return docs


# ─────────────────────────── live mode (config-driven adapters) ───────────────────────────
def load_sources() -> list[dict]:
    f = ROOT / "data" / "sources.yaml"
    if not f.exists():
        return []
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("sources", [])


def _headers() -> dict:
    return {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }


def _resolve_download(src: dict, abs_href: str) -> str:
    """Turn a result link into a fetchable body URL via the adapter's template."""
    import re as _re
    tmpl = src.get("download_url_template")
    if not tmpl:
        return abs_href
    doc_id = ""
    rx = src.get("id_regex")
    if rx:
        m = _re.search(rx, abs_href)
        doc_id = m.group(1) if m else ""
    return tmpl.replace("{href}", abs_href).replace("{id}", doc_id)


def _search_one(client, src: dict, query: str, economy: Economy, indicators, log) -> list[DiscoveredDoc]:
    """Fire one query at one portal, parse result links into candidate docs."""
    import httpx
    from bs4 import BeautifulSoup

    url = src["search_url_template"].replace("{query}", httpx.QueryParams({"q": query})["q"])
    out: list[DiscoveredDoc] = []
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 — bot blocks / network; report and move on
        log(f"[discover] {src.get('name','?')} query='{query}' failed ({type(e).__name__})")
        return out

    soup = BeautifulSoup(resp.text, "lxml")
    must = (src.get("link_must_contain") or "").lower()
    for a in soup.select(src.get("result_link_selector", "a")):
        href = a.get("href")
        if not href:
            continue
        abs_href = httpx.URL(url).join(href).human_repr()
        if must and must not in abs_href.lower():
            continue
        body_url = _resolve_download(src, abs_href)
        title = a.get_text(" ", strip=True) or abs_href
        fmt = DocFormat.PDF_TEXT if body_url.lower().endswith(".pdf") else DocFormat.HTML
        out.append(DiscoveredDoc(
            doc_id=_doc_id(economy.value, body_url),
            economy=economy,
            title=title[:200],
            source_url=body_url,
            portal=src.get("name", "live"),
            fmt=fmt,
            relevance_score=_score(title, indicators),
            discovery_tag=DiscoveryTag.NEW,
        ))
    return out


def _search_au_api(client, src: dict, query: str, economy: Economy, indicators, log) -> list[DiscoveredDoc]:
    """Australia: official OData JSON API. AU Acts are named by title not topic, so we
    run TWO queries per term and merge: contains(name,…) nails flagship Acts by name
    ('Privacy Act'→C2004A03712), while $search hits topic words in the full text to
    surface topically-relevant Acts that lack an obvious keyword title."""
    import re as _re
    tmpl = src.get("detail_url_template", "https://www.legislation.gov.au/{id}")
    qtok = {w for w in _re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    out: list[DiscoveredDoc] = []
    seen: set[str] = set()
    # `isInForce eq true` is the correct OData field on this API (the older `inForce`
    # returns HTTP 400 and `isPrincipal`/`status` are read-only, not filterable). The
    # filter alone excludes repealed/superseded compilations from the result set, so the
    # 1946–1971 Overseas Telecommunications Acts never reach extraction. Fall back to no
    # status filter only if the field is rejected, so a future API change can't blank the run.
    _base = f"contains(name,'{query}') and collection eq 'Act'"
    variants = [
        {"$filter": f"{_base} and isInForce eq true", "$top": "40"},
        {"$filter": _base, "$top": "40"},  # fallback: item-level isInForce check still filters
    ]
    items: list = []
    for params in variants:
        try:
            r = client.get(src["api_base"], params=params, headers={"Accept": "application/json"})
            r.raise_for_status()
            items = r.json().get("value", [])
            break  # success — don't try fallback
        except Exception as e:  # noqa: BLE001
            label = "retrying without isInForce" if "isInForce" in params.get("$filter", "") else "skipping"
            log(f"[discover] AU API query='{query}' filter='{params.get('$filter','')}' "
                f"failed ({type(e).__name__}) — {label}")
    for it in items:
        tid, name = it.get("id"), (it.get("name") or "")
        if not tid or tid in seen:
            continue
        seen.add(tid)

        # Defence-in-depth: even when `$filter=isInForce eq true` worked at the API level,
        # the no-filter fallback returns historical acts — drop anything the item itself
        # marks as not-in-force or repealed. Default to include when the field is absent.
        if it.get("isInForce") is False:
            continue
        if (it.get("status") or "").lower() in ("repealed", "ceased", "revoked", "expired"):
            continue

        # rank by how much of the search term appears in the TITLE — keeps flagship
        # name-matches (Privacy Act → 1.0) and drops $search content-only noise (1901
        # acts whose titles share no query word → 0.0, filtered out by the caller).
        ntok = {w for w in _re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2}
        score = round(len(qtok & ntok) / len(qtok), 3) if qtok else 0.0
        url = tmpl.replace("{id}", tid)

        # Recency for _pick_best: prefer an explicit modified/register date, else fall back
        # to makingDate / the numeric `year` field (always present on this API).
        last_mod = (it.get("lastModified") or it.get("asMadeRegisteredAt")
                    or it.get("makingDate") or "")
        amendment_date = last_mod[:10] if last_mod else (
            f"{it.get('year')}-01-01" if it.get("year") else None)

        out.append(DiscoveredDoc(
            doc_id=_doc_id(economy.value, url), economy=economy, title=name[:200],
            source_url=url, portal=src.get("name", "AU"), fmt=DocFormat.HTML,
            law_number=tid, relevance_score=score, discovery_tag=DiscoveryTag.NEW,
            amendment_date=amendment_date))
    return out


def _au_pdf_download_url(title_id: str) -> str | None:
    """AU: the authorised compilation PDF download URL for a title. legislation.gov.au is a
    JS SPA (the /latest/text page renders only a collapsed outline), but the Download button
    points at a static asset: /{id}/{date}/{date}/text/original/pdf, where {date} is the
    latest compilation's start date from the OData /v1/documents feed. Returns None if the
    API is unreachable so the caller falls back to the page (then the JS-shell guard)."""
    try:
        import httpx
        r = httpx.get("https://api.prod.legislation.gov.au/v1/documents",
                      params={"$filter": f"titleId eq '{title_id}' and format eq 'Pdf'",
                              "$orderby": "start desc", "$top": "5"},
                      headers={"Accept": "application/json"}, timeout=20)
        items = r.json().get("value", [])
    except Exception:  # noqa: BLE001
        return None
    items = [it for it in items if it.get("isAuthorised")] or items
    start = (items[0].get("start") or "")[:10] if items else ""
    if not start:
        return None
    return f"https://www.legislation.gov.au/{title_id}/{start}/{start}/text/original/pdf"


_AU_TITLE_ID_RE = re.compile(r"legislation\.gov\.au/([A-Za-z]\d{4}[A-Za-z]\d+)", re.I)


def _resolve_pdf_url(economy: Economy, url: str) -> tuple[str, DocFormat]:
    """Turn a law's landing URL into a fetchable full-text body URL + its format.
    SG SSO serves the whole Act as a PDF at ?ViewType=Pdf (verified); AU resolves the
    title to its authorised compilation PDF (the SPA page has no static text); MY links
    are already direct PDFs; others fall back to the page itself."""
    from urllib.parse import urlsplit, urlunsplit
    low = url.lower()
    if low.endswith(".pdf"):
        return url, DocFormat.PDF_TEXT
    if economy.value == "SG" and ("/act/" in low or "/sl/" in low or "/acts-supp/" in low):
        s = urlsplit(url)
        return urlunsplit((s.scheme, s.netloc, s.path, "ViewType=Pdf", "")), DocFormat.PDF_TEXT
    if economy.value == "AU":
        m = _AU_TITLE_ID_RE.search(url)
        if m:
            pdf = _au_pdf_download_url(m.group(1))
            if pdf:
                return pdf, DocFormat.PDF_TEXT
    return url, DocFormat.HTML


def _my_english_pdf_url(url: str) -> str | None:
    """MY: derive the English-sibling PDF URL from a Malay PDF URL.

    AGC convention: Malay act = ``akta_709.pdf``, English act = ``akta_709e.pdf``
    (trailing 'e' before the extension).  Returns None when the URL doesn't look
    like a Malay PDF (already English, or not a PDF at all).
    """
    low = url.lower()
    if not low.endswith(".pdf"):
        return None
    if low.endswith("e.pdf"):
        return None  # already English (or at least has the 'e' suffix)
    return url[:-4] + "e.pdf"


def discover_websearch(economy: Economy, pillar: int | None, max_docs: int) -> list[DiscoveredDoc]:
    """Discover laws via web search (slide A: 'search ... and the web') — portal-agnostic,
    generalises to any economy with an entry in websearch.OFFICIAL_PORTAL."""
    from . import websearch
    from ..rdtii.keywords import portal_search_queries
    websearch.reset_circuit()                      # fresh circuit-breaker state per run
    topics = portal_search_queries(economy.value, pillar)[:settings.discovery_max_queries]
    # One search per query → a per-query result bucket. A law-type query ("companies act")
    # returns few, niche hits that the old "fill the budget in query order" loop discarded
    # once abundant data-protection queries had filled it. We instead collect ROUND-ROBIN
    # below, so every query's TOP hit is taken before any query's 2nd.
    buckets: list[list[tuple[str, str, str]]] = []
    for topic in topics:
        res = websearch.find_law_urls(economy, topic, max_results=settings.discovery_per_query)
        if res:
            buckets.append(res)

    by_url: dict[str, DiscoveredDoc] = {}
    # search snippet(s) per cleaned source_url — accumulated across every query that surfaced
    # the law, so the content-relevance score below sees the fullest preview of what it's about.
    snippets: dict[str, str] = {}

    def _add(url: str, title: str, snippet: str) -> None:
        # source_url stays the human-facing LANDING page (judges prefer it); the PDF body
        # URL is resolved only at fetch time (see _resolve_pdf_url).
        su = _clean_source_url(economy, url)
        if snippet:
            snippets[su] = (snippets.get(su, "") + " " + snippet).strip()
        if url in by_url:
            return
        _, fmt = _resolve_pdf_url(economy, url)
        by_url[url] = DiscoveredDoc(
            doc_id=_doc_id(economy.value, url), economy=economy,
            title=(title or url)[:200], source_url=su,
            portal=websearch.OFFICIAL_PORTAL.get(economy.value, "web"),
            fmt=fmt, relevance_score=0.0, discovery_tag=DiscoveryTag.NEW)

    depth = max((len(b) for b in buckets), default=0)
    for rank in range(depth):                      # round-robin: rank-0 of every query first
        for b in buckets:
            if rank < len(b):
                it = b[rank]
                _add(it[0], it[1], it[2] if len(it) > 2 else "")
        if len(by_url) >= max_docs * 3:
            break
    # Collapse multiple URL variants of the same law into the most current/in-force version.
    docs = _dedup_by_law_title(list(by_url.values()))
    # For MY: prefer English-language documents over Bahasa Malaysia equivalents.
    if economy.value == "MY":
        docs = _prefer_english_my(docs)
    # SG consolidates amendments into the principal text → drop redundant Amendment files.
    if economy.value == "SG":
        docs = _drop_amendment_docs(docs)

    # Content-relevance gate. Round-robin gathered a BROAD candidate pool (every query's top
    # hits) — but taking them in arrival order let off-topic laws a tangential query surfaced
    # (Gambling/Active Mobility/Customs for a P6 cross-border-data run) fill the budget ahead
    # of on-topic ones. So score each candidate by indicator-term coverage over its title +
    # search snippet and keep the most relevant max_docs. This judges what a law is ABOUT, not
    # its name, so a law whose title hides the provision (Companies Act → accounting-record
    # storage) still ranks high: its snippet, from the on-topic query that found it, carries
    # the matched terms. No law names are hardcoded — only the generic indicator query terms.
    indicators = get_indicators(pillar)
    if any(snippets.values()):                     # only rank when we have real snippets (Serper);
        for d in docs:                             # keyless engines give none → keep round-robin order
            d.relevance_score = _snippet_relevance(
                (d.title or "") + " " + snippets.get(d.source_url, ""), indicators)
        docs.sort(key=lambda d: d.relevance_score, reverse=True)
    return docs[:max_docs]


def discover_live(economy: Economy, pillar: int | None = None, max_docs: int | None = None) -> list[DiscoveredDoc]:
    """Search the economy's official portal(s) with coarse pillar keywords and return
    ranked candidate documents (NEW). Returns [] if httpx/bs4 or the network are
    unavailable — callers fall back to sample mode. Bodies are fetched later (Zone 1b).
    """
    try:
        import httpx  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
    except Exception:
        return []

    from ..rdtii.keywords import portal_search_queries
    max_docs = max_docs or settings.discovery_max_docs
    indicators = get_indicators(pillar)
    queries = portal_search_queries(economy.value, pillar)
    sources = [s for s in load_sources() if s.get("economy") == economy.value
               and (s.get("search_url_template") or s.get("adapter"))]
    if not sources:
        return []

    by_url: dict[str, DiscoveredDoc] = {}

    # web-search adapters (SG/MY/…): portal-agnostic, finds laws the JS search hides
    if any(s.get("adapter") == "websearch" for s in sources):
        for d in discover_websearch(economy, pillar, max_docs):
            by_url[d.source_url] = d

    # API / scrape adapters (AU JSON API; server-rendered portals)
    api_sources = [s for s in sources if s.get("adapter") not in ("websearch",)]
    if api_sources:
        import httpx
        with httpx.Client(timeout=settings.crawl_timeout_seconds, headers=_headers(), follow_redirects=True) as client:
            for src in api_sources:
                searcher = _search_au_api if src.get("adapter") == "au_api" else _search_one
                for q in queries:
                    for d in searcher(client, src, q, economy, indicators, log=print):
                        prev = by_url.get(d.source_url)
                        if prev is None or d.relevance_score > prev.relevance_score:
                            by_url[d.source_url] = d
                    if len(by_url) >= max_docs * 3:
                        break

    # web-search docs carry score 0 (ranked later by CONTENT); keep them. Only drop
    # the API title-overlap zeros (content-only noise) when no web-search ran.
    docs = list(by_url.values())
    # Collapse multiple URL variants / year-compilations of the same law into one,
    # preferring the most current/consolidated/in-force version.
    docs = _dedup_by_law_title(docs)
    # For MY: prefer English-language documents over Bahasa Malaysia equivalents.
    if economy.value == "MY":
        docs = _prefer_english_my(docs)
    # SG & AU both serve CONSOLIDATED in-force texts (SSO; AU compilations resolve from the
    # principal title id), so standalone Amendment instruments are redundant — and on AU a broad
    # name token (e.g. "security intelligence") returns several "… Legislation Amendment Act"
    # hits that would otherwise crowd the principal Act out of the capped result set. Drop them.
    if economy.value in ("SG", "AU"):
        docs = _drop_amendment_docs(docs)
    docs.sort(key=lambda d: d.relevance_score, reverse=True)
    return docs[:max_docs]


def doc_from_file(economy: Economy, path: str) -> DiscoveredDoc:
    """Build a DiscoveredDoc from a local file (the `--pdf` bypass-crawler path)."""
    p = Path(path)
    ext = p.suffix.lower()
    fmt = (DocFormat.PDF_TEXT if ext == ".pdf"
           else DocFormat.HTML if ext in (".html", ".htm")
           else DocFormat.TEXT)
    return DiscoveredDoc(
        doc_id=_doc_id(economy.value, str(p.resolve())),
        economy=economy, title=p.stem, source_url=p.resolve().as_uri(),
        portal="local-file", fmt=fmt, relevance_score=1.0,
        discovery_tag=DiscoveryTag.NEW, local_path=str(p),
    )


def discover(economy: Economy, pillar: int | None = None, use_samples: bool = True) -> list[DiscoveredDoc]:
    if use_samples:
        return discover_from_samples(economy, pillar)
    # Live mode is the SCORED path: retrieve from live portals only. Do NOT fall back to
    # the bundled sample corpus — the rubric forbids pre-downloaded files. An empty result
    # surfaces a real discovery failure (e.g. search rate-limited) instead of masking it.
    return discover_live(economy, pillar)
