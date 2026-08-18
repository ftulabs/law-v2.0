"""Law version identity + freshness.

Two different questions, two different costs:

  `version_signal(law)`  — BUILD time. Must be cheap: it runs once per law in a 6,000-law
                           pass, so it only uses signals already in hand (the AU compilation
                           feed we call anyway to resolve the PDF; the reprint date the MY
                           catalogue record already carries). When no cheap signal exists
                           (SG), the content hash IS the version key — it never lies.

  `check_freshness(...)` — QUERY time. Portal-authoritative, and only ever run over the laws
                           a stored answer actually cites (10–30), so it can afford a request
                           per law. Reuses the three timeline parsers already in discovery.py.
"""
from __future__ import annotations

import re
from typing import Callable

from . import store

Log = Callable[[str], None]

# lom.agc.gov.my writes the reprint currency into the catalogue title: "… As At 01-07-2023".
_MY_AS_AT_RE = re.compile(r"as at\s*[:\-]?\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})", re.I)


def _my_reprint_date(law: dict) -> str | None:
    blob = f"{law.get('title') or ''} {law.get('catalogue_json') or ''}"
    m = _MY_AS_AT_RE.search(blob)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def version_signal(law: dict) -> tuple[str | None, str | None]:
    """(version_key, amendment_date) from cheap, build-time-available signals."""
    econ = (law.get("economy") or "").upper()
    if econ == "AU":
        from ..pipeline.discovery import _au_latest_compilation, _au_title_id
        tid = law.get("law_number") or _au_title_id(law.get("source_url") or "")
        if tid:
            _pdf, start, never_amended = _au_latest_compilation(tid)
            if never_amended:
                return (start or "original"), "Original"
            if start:
                return start, start
    elif econ == "MY":
        d = _my_reprint_date(law)
        if d:
            return d, d
    return None, None      # → store.version_id falls back to the content hash


# ─────────────────────────── query-time freshness ───────────────────────────
def portal_version(law: dict) -> tuple[str | None, str | None]:
    """Ask the PORTAL what the current version of this law is. One request per law."""
    econ = (law.get("economy") or "").upper()
    url = law.get("source_url") or ""
    try:
        if econ == "AU":
            from ..pipeline.discovery import _au_latest_compilation, _au_title_id
            tid = law.get("law_number") or _au_title_id(url)
            if tid:
                _pdf, start, never = _au_latest_compilation(tid)
                return ((start or "original"), "Original") if never else (start, start)
        if econ == "SG":
            from ..pipeline.discovery import _sg_amendment_date
            d = _sg_amendment_date(url)
            return d, d
        if econ == "MY":
            from ..pipeline.discovery import _my_amendment_date
            d = _my_amendment_date(law.get("law_number") or "")
            return d, d
    except Exception:  # noqa: BLE001 — unreachable portal ⇒ "unverified", never a crash
        return None, None
    return None, None


def check_freshness(economy: str, law_ids: list[str], log: Log = print) -> dict:
    """Compare each law's stored version_key against the portal's current one.

    Returns {"verified": [...], "stale": [...], "unverified": [...]} and writes a
    `corpus_check` row — the audit record that proves an answer was revalidated live.
    """
    economy = economy.upper()
    laws = {r["law_id"]: r for r in store.list_laws(economy) if r["law_id"] in set(law_ids)}
    known = store.versions_for(list(laws))
    verified, stale, unverified = [], [], []
    for lid, law in laws.items():
        portal_key, _date = portal_version(law)
        stored = (known.get(lid) or {}).get("version_key")
        if portal_key is None:
            unverified.append(lid)          # portal gave no signal (SG default, or an outage)
        elif stored and portal_key != stored:
            stale.append(lid)
        else:
            verified.append(lid)
    store.log_check(economy, "cited_laws", None, len(laws), len(stale),
                    {"verified": len(verified), "stale": len(stale),
                     "unverified": len(unverified), "stale_ids": stale[:50]})
    log(f"[freshness] {economy}: {len(verified)} verified, {len(stale)} stale, "
        f"{len(unverified)} unverified")
    return {"verified": verified, "stale": stale, "unverified": unverified}
