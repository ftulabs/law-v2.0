"""CSV export for legal/policy reviewers.

Columns follow CSV_COLUMNS exactly. Verbatim snippets are written unaltered (only
CSV-quoted), so the exact statutory wording survives the round-trip — a hard
requirement for legal traceability.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..config import settings
from ..schemas import CSV_COLUMNS, EvidenceMapping


def export_csv(mappings: list[EvidenceMapping], run_id: str, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or settings.output_path
    path = Path(out_dir) / f"veritrade_{run_id}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for m in mappings:
            writer.writerow({
                "economy": m.economy.value,
                "pillar": m.pillar,
                "indicator_id": m.indicator_id,
                "law_name": m.law_name,
                "article_section": m.article_section,
                "verbatim_snippet": m.verbatim_snippet,   # exact wording, never paraphrased
                "source_url": m.source_url,
                "mapping_rationale": m.mapping_rationale,
                "confidence_score": m.confidence_score,
                "discovery_tag": m.discovery_tag.value,
                "review_status": m.review_status.value,
            })
    return path
