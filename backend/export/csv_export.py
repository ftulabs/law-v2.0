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


_SCORE_LABEL = {0.0: "simplified", 0.5: "moderate", 1.0: "heavy"}


def _notes_with_score(m: EvidenceMapping) -> str:
    """Prepend the Zone-3 RDTII score to Notes so the policy judge sees it in the 13-col
    CSV without adding a new column. Format: 'RDTII score N (label): <impact>. <base notes>'"""
    base = m.notes or ""
    if m.raw_score is None:
        return base
    label = _SCORE_LABEL.get(float(m.raw_score), str(m.raw_score))
    score_str = str(int(m.raw_score)) if float(m.raw_score).is_integer() else f"{m.raw_score:g}"
    prefix = f"RDTII score {score_str} ({label})"
    if m.impact:
        prefix = f"{prefix}: {m.impact}."
    return f"{prefix} {base}".strip() if base else prefix


def _row(m: EvidenceMapping) -> dict[str, str]:
    # EXACT official 13-column template. Pillar/Coverage/Flag-for-review and OCR/CER
    # metrics are carried in the JSON export, never added to this CSV.
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
        "Notes": _notes_with_score(m),
    }


def export_csv(mappings: list[EvidenceMapping], run_id: str, out_dir: Path | None = None,
               submission_only: bool = True, out_stem: str | None = None) -> Path:
    out_dir = out_dir or settings.output_path
    rows = [m for m in mappings if (not submission_only or m.review_status.value in SUBMITTABLE_STATUSES)]
    path = Path(out_dir) / f"{out_stem or ('veritrade_' + run_id)}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SUBMISSION_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for m in rows:
            writer.writerow(_row(m))
    return path
