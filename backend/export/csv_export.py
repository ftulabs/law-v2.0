"""CSV export — the OFFICIAL hackathon submission format.

Column names and order match the UNESCAP RDTII template EXACTLY (judges validate
programmatically). Economy uses the official UN member-state name; verbatim snippets
are written unaltered; confidence is a 2-dp decimal. By default only submittable rows
are written (rejected/quarantined are excluded), keeping a sectoral mis-map out of a
national-indicator submission — pass `submission_only=False` to dump everything.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..config import settings
from ..schemas import ECONOMY_UN_NAME, SUBMISSION_COLUMNS, SUBMITTABLE_STATUSES, EvidenceMapping


def _row(m: EvidenceMapping) -> dict[str, str]:
    return {
        "Economy": ECONOMY_UN_NAME.get(m.economy.value, m.economy.value),
        "Law Name": m.law_name,
        "Law Number / Ref": m.law_number or "",
        "Last Amended": m.last_amended or "",
        "Indicator ID": m.indicator_id,
        "Article / Section": m.article_section,
        "Discovery Tag": m.discovery_tag.value,
        "Location Reference": m.location_ref or "",
        "Verbatim Snippet": m.verbatim_snippet,          # EXACT — never paraphrased
        "Mapping Rationale": m.mapping_rationale or "",
        "Source URL": m.source_url,
        "Confidence": f"{m.confidence_score:.2f}",
        "Notes": m.notes or "",
    }


def export_csv(mappings: list[EvidenceMapping], run_id: str, out_dir: Path | None = None,
               submission_only: bool = True) -> Path:
    out_dir = out_dir or settings.output_path
    rows = [m for m in mappings if (not submission_only or m.review_status.value in SUBMITTABLE_STATUSES)]
    path = Path(out_dir) / f"veritrade_{run_id}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SUBMISSION_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for m in rows:
            writer.writerow(_row(m))
    return path
