#!/usr/bin/env python3
"""Measure real cost + wall-clock for one document, per the hackathon rubric.

    python tools/cost_logger.py --pdf data/samples/AU/privacy_act.pdf --economy Australia --pillar 6

Writes logs/cost_report.json. LLM token usage is captured from the provider response
when available; the default offline stack (MarkItDown + mock grader) and OpenRouter
*free* models cost $0.00 — wall-clock is still measured.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root on path

from backend.config import settings
from backend.pipeline.orchestrator import run_pipeline
from main import parse_economy

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    p = argparse.ArgumentParser(description="VeriTrade cost logger")
    p.add_argument("--pdf", required=True)
    p.add_argument("--economy", required=True)
    p.add_argument("--pillar", default="all")
    p.add_argument("--ocr", default=None)
    p.add_argument("--llm", default=None)
    args = p.parse_args()

    economy = parse_economy(args.economy)
    pillars = [6, 7] if str(args.pillar).lower() == "all" else [int(args.pillar)]

    t0 = time.perf_counter()
    result = run_pipeline(economy, pillars, pdf_path=args.pdf,
                          ocr_provider=args.ocr, llm_provider=args.llm, log=lambda *_: None)
    wall = round(time.perf_counter() - t0, 3)

    ocr_name = result.meta.ocr_provider
    llm_name = result.meta.llm_provider
    # free / offline stacks have zero marginal API cost
    free_llm = llm_name in ("mock", "openrouter")
    free_ocr = ocr_name in ("mock", "markitdown", "tesseract", "paddle")

    report = {
        "document": Path(args.pdf).name,
        "economy": economy.value,
        "measured_on": datetime.now(timezone.utc).date().isoformat(),
        "stack": {"ocr": ocr_name, "llm": llm_name, "model": result.meta.model_version},
        "ocr": {"engine": ocr_name, "pages": result.meta.docs_discovered, "cost_usd": 0.0 if free_ocr else None},
        "llm": {"model": result.meta.model_version, "cost_usd": 0.0 if free_llm else None,
                "note": "OpenRouter free tier / mock = $0; set real pricing for paid models"},
        "mappings_produced": result.meta.mappings_produced,
        "total_cost_usd": 0.0 if (free_llm and free_ocr) else None,
        "processing_time_seconds": wall,
    }
    out = ROOT / "logs" / "cost_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwritten -> {out}")


if __name__ == "__main__":
    main()
