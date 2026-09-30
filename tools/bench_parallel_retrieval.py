#!/usr/bin/env python3
"""Does running the per-indicator retrievals in PARALLEL help?

The cross-encoder is ~97% of retrieval time (`tools/profile_retrieval.py`) and it is torch on
CPU, which already spreads one forward pass across every core. So concurrent retrievals may
simply contend for the same cores and win nothing — that has to be measured, not assumed.

    python tools/bench_parallel_retrieval.py --economy SG --pillar 7

Runs each configuration with the cross-encoder caches CLEARED, otherwise the second
configuration reads the first one's answers and looks infinitely fast.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline import retrieval                                 # noqa: E402
from backend.rdtii import get_indicators                               # noqa: E402
from backend.schemas import resolve_economy                            # noqa: E402
from tools.bench_bm25_cache import load_provisions                     # noqa: E402


def _clear_caches():
    retrieval._CE_DISK.clear()
    retrieval._BM25_CACHE.clear()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", default="SG")
    ap.add_argument("--pillar", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=80)
    ap.add_argument("--workers", default="1,2,3,5")
    a = ap.parse_args()

    import torch
    econ = resolve_economy(a.economy)
    provs = load_provisions(econ, a.pillar)
    inds = get_indicators(a.pillar)
    print(f"corpus {len(provs)} provisions · {len(inds)} indicators · "
          f"torch threads {torch.get_num_threads()} · CE cache DISABLED for the bench\n")
    if not provs:
        return 1

    # warm the shared corpus/BM25 and the provision embeddings once, so the bench measures the
    # per-indicator work and not a one-off build that only the first configuration would pay.
    retrieval.retrieve(inds[0].indicator_id, provs, top_k=a.top_k)

    print(f"{'workers':>8} {'seconds':>9} {'speedup':>8}")
    base = None
    for w in [int(x) for x in a.workers.split(",")]:
        _clear_caches()
        retrieval._corpus_and_bm25(provs)          # shared, not part of what we compare
        t0 = time.perf_counter()
        if w == 1:
            out = [retrieval.retrieve(i.indicator_id, provs, top_k=a.top_k) for i in inds]
        else:
            with ThreadPoolExecutor(max_workers=w) as ex:
                out = list(ex.map(
                    lambda i: retrieval.retrieve(i.indicator_id, provs, top_k=a.top_k), inds))
        dt = time.perf_counter() - t0
        base = base or dt
        print(f"{w:>8} {dt:>9.2f} {base/dt:>7.2f}x   "
              f"({sum(len(o) for o in out)} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
