"""Zone-3 scored CSV — the RDTII *Database* shape (one row per scored measure).

This is SEPARATE from the mandatory 14-column submission CSV (csv_export.py), which must
stay byte-for-byte on the official OUTPUT_TEMPLATE. Here we mirror the columns of the
official answer-key Database's per-economy sheets so the scored output is directly
comparable to how the judges record their own scores:

    Pillar_ID | Indicator_ID | Raw Score | Act and/or practice | Coverage |
    Impact or comments on Acts or practices | Timeframe | References | Note

A trailing block lists the INDICATOR-level roll-up (most-restrictive measure per indicator)
so a reviewer sees the one score-per-indicator RDTII ultimately reports for the economy.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..config import settings
from ..pipeline.scoring import aggregate_indicator_scores
from ..schemas import ECONOMY_UN_NAME, SUBMITTABLE_STATUSES, EvidenceMapping

SCORED_COLUMNS = [
    "Pillar_ID",
    "Indicator_ID",
    "Raw Score",
    "Act and/or practice",
    "Coverage",
    "Impact or comments on Acts or practices",
    "Timeframe",
    "References",
    "Note",
]


def _fmt_score(s: float | None) -> str:
    if s is None:
        return ""
    return str(int(s)) if float(s).is_integer() else f"{s:g}"


def _indicator_num(indicator_id: str) -> str:
    # "P6-I1" -> "6.1" to match the Database's Indicator_ID column
    try:
        pillar, ind = indicator_id.replace("P", "").split("-I")
        return f"{pillar}.{ind}"
    except ValueError:
        return indicator_id


def _row(m: EvidenceMapping) -> dict[str, str]:
    return {
        "Pillar_ID": str(m.pillar),
        "Indicator_ID": _indicator_num(m.indicator_id),
        "Raw Score": _fmt_score(m.raw_score),
        "Act and/or practice": m.law_name,
        "Coverage": m.coverage or "",
        "Impact or comments on Acts or practices": m.impact or m.mapping_rationale or "",
        "Timeframe": (f"Last amended {m.last_amended}" if m.last_amended else ""),
        "References": m.source_url,
        "Note": m.notes or "",
    }


def export_scored_csv(mappings: list[EvidenceMapping], run_id: str, out_dir: Path | None = None,
                      submission_only: bool = True, out_stem: str | None = None) -> Path:
    """Write the Database-shaped scored CSV. Only rows that carry a raw_score are emitted
    (scoring may be disabled). Sorted by (pillar, indicator, score desc) for readability."""
    out_dir = out_dir or settings.output_path
    rows = [m for m in mappings
            if m.raw_score is not None
            and (not submission_only or m.review_status.value in SUBMITTABLE_STATUSES)]
    rows.sort(key=lambda m: (m.pillar, _indicator_num(m.indicator_id), -(m.raw_score or 0)))

    path = Path(out_dir) / f"{out_stem or ('veritrade_' + run_id)}_scored.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SCORED_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for m in rows:
            writer.writerow(_row(m))
    return path
