#!/usr/bin/env python3
"""Run VeriTrade across multiple economies in one go.

    python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# On Windows, stdout defaults to the system codepage (cp1252) rather than UTF-8 — especially
# when redirected to a file (`> log.txt`), not just a live terminal. A single non-ASCII
# character in ANY log() line (log defaults to print) then raises UnicodeEncodeError and kills
# the whole multi-economy run, potentially losing an hour+ of already-completed live crawling
# with no master file written. Reconfigure to UTF-8 with a safe fallback instead of crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from backend.config import settings
from backend.export import export_csv, export_json, export_master_csv, export_scored_csv
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
    p.add_argument("--fresh", action="store_true", help="ignore the result cache")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_mappings, all_metas = [], []
    for name in args.economies:
        economy = parse_economy(name)
        result = run_pipeline(economy, args.pillar, use_samples=not args.live,
                              ocr_provider=args.ocr, llm_provider=args.llm, log=print,
                              use_result_cache=not args.fresh)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem = f"{economy.value}_P{''.join(map(str, args.pillar))}_{ts}"
        export_csv(result.mappings, result.meta.run_id, out_dir, out_stem=stem)
        export_json(result, out_dir, out_stem=stem)
        if any(m.raw_score is not None for m in result.mappings):
            export_scored_csv(result.mappings, result.meta.run_id, out_dir, out_stem=stem)
        all_mappings.extend(result.mappings)
        all_metas.append(result.meta)
        print(f"[{economy.value}] {result.meta.mappings_produced} mappings -> {stem}.csv/.json\n")

    # Final submission = ONE consolidated sheet across all economies + pillars.
    if all_mappings:
        import json
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        master = export_master_csv(all_mappings, out_dir, out_stem=f"VeriTrade_MASTER_{ts}")
        master_json = out_dir / f"VeriTrade_MASTER_{ts}.json"
        master_json.write_text(json.dumps({
            "runs": [m.model_dump(mode="json") for m in all_metas],
            "mappings": [m.model_dump(mode="json") for m in all_mappings],
        }, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[master] {master}")
        print(f"[master] {master_json}")


if __name__ == "__main__":
    main()
