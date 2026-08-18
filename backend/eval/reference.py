"""Curated label source: the panel's Database re-expressed in our own output format.

`data/ground_truth/rdtii_reference_p67.csv` is a hand-curated rendering of the RDTII Round-1
Database into the 13-column submission shape, one row per (economy, indicator, instrument),
with the operative Article/Section filled in. It is a better label source than
`ground_truth.py`'s regex pass over the panel's prose, which returns EVERY provision the
justification mentions — including incidental cross-references (Companies Act s 4 merely
*defines* "accounting records") that then look like retrieval or grading failures.

Both sources are kept: this one supplies the operative section per instrument, the regex pass
supplies the fallback when a row has no section and the absence/label metadata.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ROOT

REFERENCE_CSV = ROOT / "data" / "ground_truth" / "rdtii_reference_p67.csv"
ECONOMY = {"Australia": "AU", "Malaysia": "MY", "Singapore": "SG"}
ROUND1 = ("SG", "AU", "MY")


@dataclass
class RefRow:
    economy: str
    indicator_id: str
    law_name: str
    law_number: str
    sections: list[str] = field(default_factory=list)
    raw_score: float | None = None
    coverage: str = ""
    source_urls: list[str] = field(default_factory=list)
    rationale: str = ""


def _sections(cell: str) -> list[str]:
    """'Section 187C; Section 187AA' / 'APP 1.2; Section 33D(1)' -> ['187C','187AA'] etc."""
    out = []
    for part in re.split(r"[;,]", cell or ""):
        part = part.strip()
        if not part:
            continue
        m = re.search(r"\bapp\s*(\d+(?:\.\d+)?)", part, re.I)
        if m:
            out.append(f"APP {m.group(1)}")
            continue
        m = re.search(r"(\d{1,4}[A-Za-z]{0,2}(?:\([^)]{1,8}\))*(?:\.\d+){0,3})", part)
        if m:
            out.append(m.group(1))
    return out


def load(economies=ROUND1, path: Path | None = None) -> list[RefRow]:
    p = Path(path) if path else REFERENCE_CSV
    rows: list[RefRow] = []
    for r in csv.DictReader(p.open(encoding="utf-8-sig")):
        econ = ECONOMY.get((r.get("Economy") or "").strip())
        if not econ or econ not in economies:
            continue
        try:
            score = float(r.get("RDTII_Raw_Score") or "")
        except ValueError:
            score = None
        rows.append(RefRow(
            economy=econ, indicator_id=(r.get("Indicator ID") or "").strip(),
            law_name=(r.get("Law Name") or "").strip(),
            law_number=(r.get("Law Number / Ref") or "").strip(),
            sections=_sections(r.get("Article / Section") or ""),
            raw_score=score, coverage=(r.get("Coverage") or "").strip(),
            source_urls=[u.strip() for u in re.split(r"[;\s]+", r.get("Source URL") or "")
                         if u.startswith("http")],
            rationale=(r.get("Mapping Rationale") or "").strip(),
        ))
    return rows


def sections_by_law(economies=ROUND1) -> dict[tuple[str, str, str], list[str]]:
    """{(economy, indicator_id, law_name): [operative sections]} — the curated override."""
    out: dict[tuple[str, str, str], list[str]] = {}
    for r in load(economies):
        if r.sections:
            out.setdefault((r.economy, r.indicator_id, r.law_name), []).extend(r.sections)
    return out


if __name__ == "__main__":
    rows = load()
    from collections import Counter
    print(f"rows: {len(rows)}")
    print("by economy:", dict(Counter(r.economy for r in rows)))
    print("with sections:", sum(1 for r in rows if r.sections))
    print("distinct instruments:", len({(r.economy, r.law_name) for r in rows}))
