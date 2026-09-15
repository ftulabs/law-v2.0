#!/usr/bin/env python3
"""Sub-stage profile of extraction — the largest COLD stage of a live run.

617.1s of a live SG pillar-7 run (2026-09-14), against 151.4s of LLM grading. Stage totals do
not say WHICH PART, and the parts have very different fixes: triage and text-layer extraction
sit OUTSIDE the pluggable OCR-engine boundary (they are what runs when NO OCR is needed), so
optimising them cannot affect engine swappability, which criterion C4b scores.

    python tools/profile_extraction.py --limit 12

Sequential by design: measuring 16-way here got the process OOM-killed, which is itself the
finding recorded on `settings.extraction_concurrency`.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings                                    # noqa: E402
from backend.pipeline import extraction, ocr, pdf_inspect              # noqa: E402
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics   # noqa: E402


def _doc(p: Path) -> DiscoveredDoc:
    fmt = {".pdf": DocFormat.PDF_TEXT, ".html": DocFormat.HTML,
           ".txt": DocFormat.TEXT}.get(p.suffix.lower(), DocFormat.PDF_TEXT)
    return DiscoveredDoc(doc_id=f"PROF-{p.stem}", economy=Economy.SG, title=p.name,
                         source_url=f"https://example.gov/{p.stem}", fmt=fmt,
                         discovery_tag="NEW", relevance_score=1.0,
                         portal="example.gov", local_path=str(p))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--kind", default="pdf", choices=("pdf", "html"))
    a = ap.parse_args()

    files = sorted(settings.cache_path.glob(f"*.{a.kind}"))[:a.limit]
    if not files:
        print(f"no cached .{a.kind} bodies")
        return 1
    print(f"{len(files)} cached .{a.kind} documents · pdf_inspector "
          f"{'installed' if pdf_inspect._profile_with_inspector.__module__ and _has_inspector() else 'ABSENT (density fallback)'}\n")

    tot = {"triage": 0.0, "textlayer": 0.0, "split": 0.0}
    print(f"{'document':20}{'MB':>6}{'pages':>7}{'triage':>9}{'textlayer':>11}"
          f"{'split':>8}{'prov':>7}")
    for f in files:
        d = _doc(f)
        mb = f.stat().st_size / 1e6
        pages = 0
        t = time.perf_counter()
        if a.kind == "pdf":
            prof = pdf_inspect.profile_pdf(str(f))
            pages = prof.page_count or 0
        dt_triage = time.perf_counter() - t

        t = time.perf_counter()
        raw, metrics = ocr._extract_document_text(d)
        dt_text = time.perf_counter() - t

        t = time.perf_counter()
        provs = extraction.extract_provisions(d, raw, metrics)
        dt_split = time.perf_counter() - t

        tot["triage"] += dt_triage
        tot["textlayer"] += dt_text
        tot["split"] += dt_split
        print(f"{f.stem[:18]:20}{mb:>6.1f}{pages:>7}{dt_triage:>9.2f}{dt_text:>11.2f}"
              f"{dt_split:>8.2f}{len(provs):>7}")

    grand = sum(tot.values())
    print(f"\n{'phase':14}{'seconds':>9}{'share':>8}")
    for k, v in tot.items():
        print(f"{k:14}{v:>9.1f}{v/grand*100:>7.1f}%")
    print(f"{'TOTAL':14}{grand:>9.1f}")
    print(f"\nNOTE: `_extract_document_text` runs triage AGAIN internally, so the true "
          f"per-document cost is the textlayer column; the triage column shows how much of it "
          f"is a SECOND parse of the same file.")
    return 0


def _has_inspector() -> bool:
    try:
        import pdf_inspector  # noqa: F401
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
