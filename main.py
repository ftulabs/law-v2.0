#!/usr/bin/env python3
"""VeriTrade — top-level entry point.

    python main.py --economy Singapore --pillar 6
    python main.py --economy Malaysia --pillar all --format both
    python main.py --economy Singapore --pillar 6 --pdf path/to/law.pdf   # bypass crawler

Writes outputs/<Economy>_P<pillar>_<timestamp>.csv (+ .json). Thin wrapper over the
same pipeline used by the CLI, API and dashboard.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from backend.config import settings
from backend.export import export_csv, export_json
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy

# accept official UN names or 2-letter codes
ECONOMY_ALIASES = {
    "singapore": Economy.SG, "sg": Economy.SG,
    "australia": Economy.AU, "au": Economy.AU,
    "malaysia": Economy.MY, "my": Economy.MY,
}


def parse_economy(value: str) -> Economy:
    e = ECONOMY_ALIASES.get(value.strip().lower())
    if e is None:
        raise SystemExit(f"Unknown economy '{value}'. Supported: Singapore, Australia, Malaysia.")
    return e


def main() -> None:
    p = argparse.ArgumentParser(description="VeriTrade — RDTII evidence extraction")
    p.add_argument("--economy", required=True, help="Singapore | Australia | Malaysia (or SG/AU/MY)")
    p.add_argument("--pillar", default="all", help="6, 7, or all")
    p.add_argument("--output-dir", default=settings.output_dir)
    p.add_argument("--format", choices=["csv", "json", "both"], default="both")
    p.add_argument("--pdf", default=None, help="process a single local PDF (bypass crawler)")
    p.add_argument("--live", action="store_true", help="crawl official portals instead of the sample corpus")
    p.add_argument("--ocr", default=None, help="OCR engine: markitdown|tesseract|paddle|azure|mock")
    p.add_argument("--llm", default=None, help="LLM provider: openrouter|anthropic|openai|mock")
    p.add_argument("--llm-model", default=None, help="override LLM model name")
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    economy = parse_economy(args.economy)
    pillars = [6, 7] if str(args.pillar).lower() == "all" else [int(args.pillar)]
    from pathlib import Path
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_pipeline(
        economy, pillars, use_samples=not args.live, top_k=args.top_k,
        ocr_provider=args.ocr, llm_provider=args.llm, llm_model=args.llm_model,
        pdf_path=args.pdf, log=print,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = f"{economy.value}_P{''.join(map(str, pillars))}_{ts}"
    if args.format in ("csv", "both"):
        print("CSV ", export_csv(result.mappings, result.meta.run_id, out_dir, out_stem=stem))
    if args.format in ("json", "both"):
        print("JSON", export_json(result, out_dir, out_stem=stem))


if __name__ == "__main__":
    main()
