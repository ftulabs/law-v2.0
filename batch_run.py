#!/usr/bin/env python3
"""Run VeriTrade across multiple economies in one go.

    python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.export import export_csv, export_json, export_scored_csv
from backend.pipeline.orchestrator import run_pipeline
from main import parse_economy


def main() -> None:
    p = argparse.ArgumentParser(description="VeriTrade batch runner")
    p.add_argument("--economies", nargs="+", required=True)
    p.add_argument("--pillar", nargs="+", type=int, default=[6, 7])
    p.add_argument("--output-dir", default=settings.output_dir)
    p.add_argument("--live", action="store_true")
    p.add_argument("--ocr", default=None)
    p.add_argument("--llm", default=None)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in args.economies:
        economy = parse_economy(name)
        result = run_pipeline(economy, args.pillar, use_samples=not args.live,
                              ocr_provider=args.ocr, llm_provider=args.llm, log=print)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem = f"{economy.value}_P{''.join(map(str, args.pillar))}_{ts}"
        export_csv(result.mappings, result.meta.run_id, out_dir, out_stem=stem)
        export_json(result, out_dir, out_stem=stem)
        if any(m.raw_score is not None for m in result.mappings):
            export_scored_csv(result.mappings, result.meta.run_id, out_dir, out_stem=stem)
        print(f"[{economy.value}] {result.meta.mappings_produced} mappings -> {stem}.csv/.json\n")


if __name__ == "__main__":
    main()
