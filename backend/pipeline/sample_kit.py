"""Sample-kit KNOWN/NEW tagging.

The judges' sample kit (the RDTII Round-1 Database) lists, per economy and pillar, the
Acts/practices already identified by their human researchers — but it does NOT pin them
to a specific article or to our P6-I*/P7-I* codes (it uses the 6.1/7.2 methodology
numbering and is loosely formatted). So we can only establish KNOWN at the LAW level:

    a produced mapping is KNOWN if its LAW (matched by source URL or by title) appears in
    the sample kit for the SAME economy + pillar; otherwise it is NEW.

NEW is the high-value tag (20/40 substantive points), so we tag conservatively: only an
actual law-level match becomes KNOWN, everything the tool found on its own stays NEW.

The loader is tolerant of the messy file: columns are detected by header keywords, and it
auto-discovers the kit if no path is given.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from ..config import ROOT

_ECON = {"singapore": "SG", "australia": "AU", "malaysia": "MY",
         "sg": "SG", "au": "AU", "my": "MY"}
_STOP = {"act", "the", "of", "and", "for", "to", "on", "no", "law", "1", "2",
         "practice", "amendment", "bill", "code"}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in _STOP and len(w) > 2}


def _url_key(u: str) -> str:
    if not u:
        return ""
    p = urlparse(u.strip())
    path = re.sub(r"\.(pdf|html?|aspx)$", "", p.path.rstrip("/").lower())
    return (p.netloc.lower().replace("www.", "") + path) if p.netloc else ""


def _autodiscover() -> Path | None:
    for pat in ("*Round 1 Database*Consolidated*.csv", "*Round 1 Database*.csv",
                "data/sample_kit/*.csv", "data/sample_kit/*Consolidated*.csv"):
        hits = sorted(ROOT.glob(pat))
        if hits:
            return hits[0]
    return None


def _find_col(cols: list[str], *keys: str) -> str | None:
    for c in cols:
        cl = c.lower()
        if any(k in cl for k in keys):
            return c
    return None


def load_known(path: str | None = None):
    """Return {(economy, pillar): [ {law_tokens, url_key, name}, ... ]} or None if no kit."""
    import pandas as pd
    p = Path(path) if path else _autodiscover()
    if not p or not p.exists():
        return None
    df = pd.read_csv(p, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    c_country = _find_col(list(df.columns), "country", "economy")
    c_pillar = _find_col(list(df.columns), "pillar")
    c_law = _find_col(list(df.columns), "act", "law", "practice", "title", "name")
    c_url = _find_col(list(df.columns), "reference", "url", "source", "link")
    if not (c_country and c_pillar and (c_law or c_url)):
        return None

    index: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for _, row in df.iterrows():
        econ = _ECON.get(str(row[c_country]).strip().lower())
        pm = re.search(r"\d+", str(row[c_pillar]))
        if not econ or not pm:
            continue
        pillar = int(pm.group())
        if pillar not in (6, 7):
            continue
        law = re.sub(r"\s+", " ", str(row.get(c_law, "")).replace("\\n", " ")).strip() if c_law else ""
        url = str(row.get(c_url, "")).strip() if c_url else ""
        if not law and not url:
            continue
        index[(econ, pillar)].append({"law": _tokens(law), "url": _url_key(url), "name": law})
    return dict(index)


def is_known(economy: str, pillar: int, law_name: str, source_url: str, kit) -> bool:
    if not kit:
        return False
    entries = kit.get((economy, pillar), [])
    lk, uk = _tokens(law_name), _url_key(source_url)
    for e in entries:
        if uk and e["url"] and (uk in e["url"] or e["url"] in uk):
            return True
        if lk and e["law"] and len(lk & e["law"]) / max(len(e["law"]), 1) >= 0.6:
            return True
    return False
