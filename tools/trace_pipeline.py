"""Trace every piece of judges-accepted evidence through the pipeline, stage by stage.

    python tools/trace_pipeline.py                     # all economies
    python tools/trace_pipeline.py --economy MY --budget 1.0

Prints the loss stage for every target and a per-stage summary. LLM spend is capped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from backend.eval import trace  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", nargs="*", default=["SG", "AU", "MY"])
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--out", default="logs/trace_pipeline.json")
    a = ap.parse_args()

    targets, rep = trace.run(tuple(e.upper() for e in a.economy), budget_usd=a.budget,
                             out_path=a.out)

    order = {s: i for i, s in enumerate(trace.STAGES)}
    print("\n=== per-target trace (grouped by loss stage) ===")
    for t in sorted(targets, key=lambda x: (order.get(x.lost_at, 9), x.economy, x.indicator_id)):
        sec = t.primary_section or (t.sections[0] if t.sections else "law-level")
        rank = f"rank {t.shortlist_rank}/{t.shortlist_size}" if t.shortlist_rank else "-"
        print(f"  [{t.lost_at:10}] {t.economy} {t.indicator_id} {sec:>10} | "
              f"{(t.law_label or '')[:40]:40} | prov={t.provisions_in_law:5} | {rank}")
        if t.note:
            print(f"               {t.note[:150]}")

    print("\n=== summary ===")
    print(json.dumps(rep, indent=1))
    print("written:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
