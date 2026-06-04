#!/usr/bin/env python3
"""Evaluate VeriTrade against the bundled sample corpus.

    python evaluate.py --economy Singapore

Runs the pipeline and reports how many KNOWN provisions were matched and how many
NEW provisions were discovered (NEW provisions are the largest scoring differentiator).
"""
from __future__ import annotations

import argparse
from collections import Counter

from backend.pipeline.orchestrator import run_pipeline
from main import parse_economy


def main() -> None:
    p = argparse.ArgumentParser(description="VeriTrade sample-corpus evaluation")
    p.add_argument("--economy", required=True)
    p.add_argument("--pillar", nargs="+", type=int, default=[6, 7])
    p.add_argument("--llm", default=None)
    args = p.parse_args()

    economy = parse_economy(args.economy)
    result = run_pipeline(economy, args.pillar, use_samples=True, llm_provider=args.llm, log=lambda *_: None)
    ms = result.mappings

    tags = Counter(m.discovery_tag.value for m in ms)
    by_status = Counter(m.review_status.value for m in ms)
    by_indicator = Counter(m.indicator_id for m in ms)

    print(f"== Evaluation: {economy.value} (pillars {args.pillar}) ==")
    print(f"documents discovered : {result.meta.docs_discovered}")
    print(f"provisions extracted : {result.meta.provisions_extracted}")
    print(f"mappings produced    : {len(ms)}")
    print(f"  KNOWN matched      : {tags.get('KNOWN', 0)}")
    print(f"  NEW discovered     : {tags.get('NEW', 0)}")
    print(f"routing              : {dict(by_status)}")
    print(f"indicators covered   : {sorted(by_indicator)}")


if __name__ == "__main__":
    main()
