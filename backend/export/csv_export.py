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
from ..rdtii import codes, instrument
from ..schemas import ECONOMY_UN_NAME, SUBMISSION_COLUMNS, SUBMITTABLE_STATUSES, EvidenceMapping


def _row(m: EvidenceMapping) -> dict[str, str]:
    # "No provision found" placeholder rows follow the judges' Q&A exactly: Confidence and
    # Discovery Tag are "N/A" (neither NEW nor KNOWN applies, and 0.00 would read as a scored
    # mapping); Source URL stays the searched portal to prove Zone 1 ran.
    placeholder = m.law_name == "No provision found"
    # EXACT official 13-column template. Pillar/Coverage/OCR/CER — and the Zone-3 RDTII
    # raw_score — are deliberately NOT written here: the official template (Output Data sheet)
    # has NO score column, and per team decision (pending a judges' Q&A on where a Zone-3 score
    # belongs) we do NOT unilaterally inject it into the submission CSV — not even into Notes.
    # The score lives only in the supplementary *_scored.csv and the JSON. See NOTES_FOR_JUDGES.md.
    return {
        "Economy": ECONOMY_UN_NAME.get(m.economy.value, m.economy.value),
        "Law Name": m.law_name,
        "Law Number / Ref": m.law_number or "",
        "Last Amended": m.last_amended or "",
        # `6.4`, not our internal `P6-I4` — the template rejects the latter by name. Written
        # as a string so 12.10 cannot collapse to 12.1. See rdtii/codes.py.
        "Indicator ID": codes.to_rdtii_code(m.indicator_id),
        "Article / Section": m.article_section,
        "Discovery Tag": "N/A" if placeholder else m.discovery_tag.value,
        "Location Reference": m.location_ref or "",
        "Verbatim Snippet": m.verbatim_snippet,          # EXACT — never paraphrased
        "Mapping Rationale": m.mapping_rationale or "",
        "Source URL": m.source_url,
        "Confidence": "N/A" if placeholder else f"{m.confidence_score:.2f}",
        "Notes": _notes(m),
        "Language of Source": m.language_of_source or _language_of(m.economy.value),
    }


def _language_of(economy: str) -> str:
    """The authoritative statute language for an economy — the same registry the OCR and
    reranker decisions read, so the reported language cannot disagree with the language the
    pipeline actually assumed while processing the document."""
    from ..providers.ocr_languages import profile_for
    return profile_for(economy).language


def _notes(m: EvidenceMapping) -> str:
    """The row's own notes, plus an instrument warning when one applies.

    A draft, a repealed instrument or an amending act scores zero however well it reads, and
    all three retrieve and grade like the real thing. We do not silently drop the row — the
    finding is usually correct and only the citation is wrong — but the reviewer has to be
    told, in the row itself, because that is the only place they will be looking.
    """
    parts = [m.notes] if m.notes else []
    warn = instrument.note_for(instrument.classify(m.law_name))
    if warn and warn not in (m.notes or ""):
        parts.append(warn)
    return "  ".join(parts)


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


# custom columns must come AFTER the mandatory 13 (confirmed OK by the judges' Q&A), with
# unambiguous headers — the Q&A's own example is "RDTII_Raw_Score", so we match it exactly
MASTER_EXTRA_COLUMNS = ["Pillar", "RDTII_Raw_Score", "Coverage"]


def export_master_csv(mappings: list[EvidenceMapping], out_dir: Path | None = None,
                      out_stem: str = "VeriTrade_MASTER", submission_only: bool = True) -> Path:
    """Single consolidated sheet across all economies/pillars, sorted so related rows sit together."""
    out_dir = out_dir or settings.output_path
    rows = [m for m in mappings if (not submission_only or m.review_status.value in SUBMITTABLE_STATUSES)]
    rows.sort(key=lambda m: (m.economy.value, m.pillar, m.indicator_id, m.law_name or "~"))
    path = Path(out_dir) / f"{out_stem}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SUBMISSION_COLUMNS + MASTER_EXTRA_COLUMNS,
                                quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for m in rows:
            r = _row(m)
            r["Pillar"] = str(m.pillar)
            r["RDTII_Raw_Score"] = ("" if m.raw_score is None
                                    else f"{m.raw_score:g}")
            r["Coverage"] = m.coverage or ""
            writer.writerow(r)
    return path
