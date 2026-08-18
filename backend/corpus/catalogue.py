"""L0 — enumerate an economy's ENTIRE in-force legal corpus from the portal itself.

This is the precompute-first replacement for keyword discovery. It asks each portal for its
own index of what is in force — no search engine, no query terms, no law names — so the
result is "everything the government publishes as current law", not "whatever matched our
vocabulary". Nothing here is economy-specific beyond the adapter that speaks each portal's
own protocol; the RDTII indicators are not consulted at all at this layer.

Adapters (verified live 2026-08-01):
  AU  legislation.gov.au OData /v1/titles   — 4,747 in-force Acts, 24,335 instruments
  MY  lom.agc.gov.my DataTables JSON        — 887 principal + 406 amendment Acts
  MY  pdp.gov.my (sectoral Codes of Practice) — via the existing site-scoped web-search source
  SG  sso.agc.gov.sg /Browse pagination     — 524 current Acts, 5,843 subsidiary instruments
"""
from __future__ import annotations

import re
import time
from typing import Callable
from urllib.parse import urljoin

from ..config import settings
from . import store

Log = Callable[[str], None]

AU_API = "https://api.prod.legislation.gov.au/v1/titles"
MY_PORTAL = "https://lom.agc.gov.my/"
SG_BASE = "https://sso.agc.gov.sg"

_HEADERS = {
    "User-Agent": settings.crawl_user_agent,
    "Accept-Language": settings.crawl_accept_language,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


def _sleep(sec: float | None = None) -> None:
    time.sleep(settings.crawl_delay_seconds if sec is None else sec)


def _get(client, url: str, log: Log, tries: int = 4, **kw):
    """Portal-friendly GET: exponential backoff, and treats a 202-with-empty-body as a
    throttle (SSO's way of saying 'slow down' — it does not use 429)."""
    delay = settings.crawl_delay_seconds
    for attempt in range(tries):
        try:
            r = client.get(url, **kw)
            if r.status_code == 200 and r.content:
                return r
            log(f"[catalogue] {r.status_code} len={len(r.content)} (attempt {attempt+1}) {url[:90]}")
        except Exception as e:  # noqa: BLE001 — network flake; retry
            log(f"[catalogue] {type(e).__name__} (attempt {attempt+1}) {url[:90]}")
        delay *= 2.5
        time.sleep(delay)
    return None


# ─────────────────────────── Australia ───────────────────────────
def enumerate_au(log: Log = print, collections=("Act",), page: int = 100,
                 max_items: int | None = None) -> list[dict]:
    """Page the OData title index. `collections` may add 'LegislativeInstrument' (24k items,
    median 1 page — see docs/precompute-corpus.md §5 before turning it on)."""
    import httpx
    page = min(page, 100)          # the API rejects $top > 100 on /v1/titles (HTTP 400)
    rows: list[dict] = []
    with httpx.Client(timeout=90, headers={"Accept": "application/json"}) as c:
        for coll in collections:
            skip, seen_ids = 0, set()
            while True:
                params = {"$filter": f"collection eq '{coll}' and isInForce eq true",
                          "$top": str(page), "$skip": str(skip), "$orderby": "id"}
                r = _get(c, AU_API, log, params=params)
                if r is None:
                    log(f"[catalogue] AU {coll}: giving up at skip={skip}")
                    break
                items = r.json().get("value", [])
                if not items:
                    break
                for it in items:
                    tid = it.get("id")
                    if not tid or tid in seen_ids:
                        continue
                    seen_ids.add(tid)
                    if (it.get("status") or "").lower() in ("repealed", "ceased", "revoked", "expired"):
                        continue
                    url = f"https://www.legislation.gov.au/{tid}/latest"
                    rows.append({
                        "law_id": store.law_id("AU", url), "economy": "AU",
                        "portal": "legislation.gov.au", "title": (it.get("name") or "")[:400],
                        "law_number": tid, "source_url": url, "body_url": None,
                        "collection": "act" if coll == "Act" else "subsidiary",
                        "status": "active",
                        "catalogue_json": _json(it),
                    })
                skip += len(items)
                log(f"[catalogue] AU {coll}: {len(rows)} laws")
                if max_items and len(rows) >= max_items:
                    break
                _sleep(0.3)
            if max_items and len(rows) >= max_items:
                break
    return rows[:max_items] if max_items else rows


# ─────────────────────────── Malaysia ───────────────────────────
_MY_CATALOGUES = [
    ("act", "https://lom.agc.gov.my/json-updated-2024.php",
     "https://lom.agc.gov.my/principal.php?type=updated&lang=BI"),
    ("amendment", "https://lom.agc.gov.my/json-amendment-2024.php",
     "https://lom.agc.gov.my/principal.php?type=amendment&lang=BI"),
]


def enumerate_my(log: Log = print, include_codes: bool = True) -> list[dict]:
    """The AGC portal's own consolidated catalogues, plus the sectoral Codes of Practice that
    live on the regulator's site instead (pdp.gov.my) — the RDTII answer key leans on those
    heavily for Malaysia, and the AGC catalogue does not carry them."""
    import httpx
    from ..pipeline.discovery import _my_extract_names, _my_pdf_url
    rows: list[dict] = []
    with httpx.Client(timeout=120, headers=_HEADERS, follow_redirects=True) as c:
        for collection, url, referer in _MY_CATALOGUES:
            try:
                from ..pipeline.portal_crypto import fetch_catalogue
                records = fetch_catalogue(c, url, referer, length=5000, log=log)
            except Exception as e:  # noqa: BLE001
                log(f"[catalogue] MY {collection} failed ({type(e).__name__})")
                continue
            for rec in records:
                name, pdf, act_no = _my_record(rec, _my_extract_names, _my_pdf_url)
                if not (name and pdf):
                    continue
                landing = (f"https://lom.agc.gov.my/act-detail.php?act={act_no}&lang=BI"
                           if act_no else pdf)
                rows.append({
                    "law_id": store.law_id("MY", landing), "economy": "MY",
                    "portal": "lom.agc.gov.my", "title": name[:400], "law_number": act_no or None,
                    "source_url": landing, "body_url": pdf, "collection": collection,
                    "status": "active", "catalogue_json": _json(rec),
                })
            log(f"[catalogue] MY {collection}: {len(records)} records")
            _sleep()
    if include_codes:
        rows.extend(_enumerate_my_codes(log))
    return rows


def _my_record(rec: dict, extract_names, pdf_from_html) -> tuple[str, str | None, str]:
    """Normalise one MY catalogue record → (english_name, pdf_url, act_no).

    The two catalogues have DIFFERENT record shapes. The principal one carries a `title`
    field with the bilingual anchor pair and a direct `.pdf` href in `doc2download`; the
    amendment one uses `LEGISLATIONTITLEBI` and hides the file behind
    `processFile.php?token=<base64>`, but also exposes the raw path in `URLDOCBI`/`URLDOCBM`.
    Preferring URLDOC* is what recovers the 406 amendment Acts (A1727, the 2024 PDPA
    amendment among them) that a href-only parser silently drops.
    """
    name, _full = extract_names(rec.get("title") or rec.get("LEGISLATIONTITLEBI") or "")
    act_no = str(rec.get("lgt_act_no") or rec.get("ACTNO_LEGISLATION") or "").strip()
    pdf = None
    for field in ("URLDOCBI", "URLDOCBM"):          # English first
        raw = (rec.get(field) or "").strip()
        if raw.lower().endswith(".pdf"):
            pdf = urljoin(MY_PORTAL, raw.lstrip("/"))
            break
    if not pdf:
        pdf = pdf_from_html(rec.get("doc2download") or rec.get("DOC2DOWNLOADBI")
                            or rec.get("DOC2DOWNLOADBM") or "")
    return name, pdf, act_no


def _enumerate_my_codes(log: Log) -> list[dict]:
    """Sectoral Codes of Practice registered under the PDPA. They are not in any machine
    catalogue, so this reuses the site-scoped, PDF-only web-search source already declared in
    data/sources.yaml — still no hardcoded law names or URLs."""
    from ..pipeline.discovery import discover_websearch, load_sources
    from ..schemas import Economy
    out: list[dict] = []
    for src in load_sources():
        if src.get("economy") != "MY" or src.get("adapter") != "websearch":
            continue
        try:
            found = discover_websearch(Economy.MY, None, max_docs=60, site=src.get("site"),
                                       queries=src.get("queries"), pdf_only=bool(src.get("pdf_only")),
                                       per_query=src.get("per_query") or 10)
        except Exception as e:  # noqa: BLE001
            log(f"[catalogue] MY codes lookup failed ({type(e).__name__})")
            continue
        for d in found:
            out.append({
                "law_id": store.law_id("MY", d.source_url), "economy": "MY",
                "portal": src.get("site", "pdp.gov.my"), "title": d.title[:400],
                "law_number": None, "source_url": d.source_url, "body_url": d.source_url,
                "collection": "code_of_practice", "status": "active",
                "catalogue_json": _json({"discovered_via": "site-scoped web search",
                                         "site": src.get("site")}),
            })
        log(f"[catalogue] MY codes of practice: {len(out)}")
    return out


# ─────────────────────────── Singapore ───────────────────────────
# Result rows in the /Browse listing: <a class="non-ajax" href="/Act/PDPA2012">Title</a>.
# `non-ajax` is what separates a real result link from the nav pills and action menus.
_SG_ROW_RE = re.compile(r'<a\s+class="non-ajax"\s+href="(/(?:Act|SL|Acts-Supp)/[^"]+)"[^>]*>\s*([^<]{3,300}?)\s*</a>',
                        re.I)
_SG_COUNT_RE = re.compile(r'(\d[\d,]*)\s+results in\s+(\d+)\s+pages', re.I)


# SSO's browse listing IGNORES `CurrentPage` (verified 2026-08-01: pages 1, 2 and 3 return
# byte-identical HTML at every PageSize, with or without the AJAX header) — so the index
# cannot be walked page by page. What it DOES honour is the sort: asking for the same list
# ordered ASC and then DESC returns the first and last `PageSize` entries, and their union is
# the whole index whenever total <= 2 x PageSize. Two sort keys (Title, Number) give four
# windows, which covers SSO's 524 current Acts completely. It does NOT cover the 5,843
# subsidiary instruments — that shortfall is reported, never hidden.
_SG_SORTS = [("Title", "ASC"), ("Title", "DESC"), ("Number", "ASC"), ("Number", "DESC")]


def enumerate_sg(log: Log = print, kinds=("Act",), page_size: int = 500,
                 max_items: int | None = None) -> list[dict]:
    """Enumerate SSO's browse index via sort-window union (see note above).

    SSO throttles hard — it answers a burst with `202` and an EMPTY body rather than 429 —
    so this is deliberately slow and retries with backoff (see `_get`)."""
    import httpx
    rows: list[dict] = []
    with httpx.Client(timeout=120, headers=_HEADERS, follow_redirects=True) as c:
        for kind in kinds:
            seen: set[str] = set()
            total = None
            for sort_by, order in _SG_SORTS:
                url = (f"{SG_BASE}/Browse/{kind}/Current/All?PageSize={page_size}"
                       f"&SortBy={sort_by}&SortOrder={order}&CurrentPage=1")
                r = _get(c, url, log)
                if r is None:
                    log(f"[catalogue] SG {kind}: window {sort_by}/{order} unavailable")
                    continue
                if total is None:
                    m = _SG_COUNT_RE.search(re.sub(r"<[^>]+>", " ", r.text))
                    total = int(m.group(1).replace(",", "")) if m else None
                for href, title in _SG_ROW_RE.findall(r.text):
                    path = href.split("?")[0]
                    if path in seen:
                        continue
                    seen.add(path)
                    landing = SG_BASE + path
                    rows.append({
                        "law_id": store.law_id("SG", landing), "economy": "SG",
                        "portal": "sso.agc.gov.sg", "title": _unescape(title)[:400],
                        "law_number": path.rsplit("/", 1)[-1], "source_url": landing,
                        # SSO serves the whole instrument as PDF at ?ViewType=Pdf (verified)
                        "body_url": landing + "?ViewType=Pdf",
                        "collection": "act" if kind == "Act" else "subsidiary",
                        "status": "active",
                        "catalogue_json": _json({"browse_kind": kind,
                                                 "window": f"{sort_by}/{order}"}),
                    })
                log(f"[catalogue] SG {kind}: {sort_by}/{order} -> {len(seen)} unique so far")
                if max_items and len(rows) >= max_items:
                    break
                _sleep()
            if total and len(seen) < total:
                log(f"[catalogue] SG {kind}: INCOMPLETE — {len(seen)}/{total} enumerated "
                    f"(SSO ignores CurrentPage; raise PageSize or add sort windows)")
            elif total:
                log(f"[catalogue] SG {kind}: complete — {len(seen)}/{total}")
            if max_items and len(rows) >= max_items:
                break
    return rows[:max_items] if max_items else rows


# ─────────────────────────── driver ───────────────────────────
ADAPTERS = {"AU": enumerate_au, "MY": enumerate_my, "SG": enumerate_sg}


def _json(obj) -> str:
    import json
    try:
        return json.dumps(obj, default=str)[:20_000]
    except Exception:  # noqa: BLE001
        return "{}"


def _unescape(s: str) -> str:
    import html
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def sweep(economy: str, log: Log = print, include_regulators: bool = True, **kw) -> dict:
    """Enumerate one economy and upsert into `corpus_law`. Returns a small report; the
    check is logged to `corpus_check` so a judge can see when the index was last verified."""
    store.init()
    economy = economy.upper()
    fn = ADAPTERS[economy]
    before = {r["law_id"] for r in store.list_laws(economy)}
    rows = fn(log=log, **kw)
    if include_regulators:
        # Statute portals carry Acts and subsidiary legislation; codes of practice, standards,
        # guidelines and licence conditions are published by the REGULATOR instead, and the
        # answer key leans on them heavily. Enumerated from each regulator's own index.
        from .regulator import enumerate_regulators
        rows = rows + enumerate_regulators(economy, log=log)
    # dedupe within the sweep (a law can appear in two catalogues)
    uniq: dict[str, dict] = {}
    for r in rows:
        uniq.setdefault(r["law_id"], r)
    store.save_laws(list(uniq.values()))
    new = set(uniq) - before
    gone = before - set(uniq)
    store.log_check(economy.upper(), "catalogue_sweep", None, len(uniq), len(new),
                    {"new": len(new), "missing_from_portal": len(gone)})
    report = {"economy": economy.upper(), "enumerated": len(uniq),
              "new": len(new), "missing_from_portal": len(gone)}
    log(f"[catalogue] {economy.upper()}: {report}")
    return report
