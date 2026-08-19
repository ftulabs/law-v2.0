"""E4: is the cross-encoder POOL the thing suppressing the missed provisions?

`retrieval._cross_scores` only cross-encodes the top `3 x top_k` candidates by the base blend.
Everything outside that pool keeps `cross = 0.0`, and the final score is
`0.5 * blend + 0.5 * cross` — so a provision outside the pool has its score **halved**. That is
a hard cliff, not a soft preference, and it is a plausible reason the panel's provisions were
found at ranks 6,000-13,000: not judged irrelevant, just never cross-encoded.

Precompute changes what is affordable. Measured on this machine the cross-encoder runs 123
pairs/s, so scoring EVERY provision against all 9 indicators costs ~1 hour for all three
economies — once, offline.

Method: compute the cross-encoder over the FULL corpus exactly once per (economy, indicator),
then simulate any pool size by zeroing the scores outside the top-P of the base blend. One
expensive pass, every pool size for free, all measured on identical inputs.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from backend.eval import harness, rank_lab, trace                      # noqa: E402
from backend.pipeline import ranking, retrieval as R                   # noqa: E402
from backend.rdtii import get_indicator, get_indicators                # noqa: E402

ECON = ("SG", "AU", "MY")


def full_cross(economy: str, indicator_id: str, provisions, batch: int = 64):
    """Cross-encoder score for EVERY provision (not just a pool). Sigmoid to 0..1."""
    import math
    ce = ranking._cross_encoder()
    if ce is None:
        return None
    ind = get_indicator(indicator_id)
    query = f"{ind.title}. {ind.legal_test} Keywords: {' '.join(ind.query_terms)}"
    pairs = [(query, p.verbatim_snippet[:512]) for p in provisions]
    raw = ce.predict(pairs, batch_size=batch, show_progress_bar=False)
    return [1.0 / (1.0 + math.exp(-float(s))) for s in raw]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", nargs="*", default=list(ECON))
    ap.add_argument("--pools", nargs="*", type=int, default=[400, 1350, 4000, 12000, 0])
    ap.add_argument("--k", nargs="*", type=int, default=[300, 450])
    ap.add_argument("--out", default="logs/sweep_ce_pool.json")
    a = ap.parse_args()
    econs = tuple(e.upper() for e in a.economy)

    targets = trace.build_targets()
    trace.trace_corpus(targets)
    live = [t for t in targets if not t.lost_at and t.economy in econs]
    acts = [t for t in live if trace.is_statute(t.collection)]
    print(f"[e4] targets reaching retrieval: {len(live)} ({len(acts)} statute)")

    # hit[(pool, k)] -> set of target ids found;  rank[pool][target] -> absolute rank
    hits = defaultdict(set)
    ranks = defaultdict(dict)
    t0 = time.perf_counter()
    for econ in econs:
        provs = harness.load_provisions(econ)
        pid_index = {p.provision_id: i for i, p in enumerate(provs)}
        v2l = harness.version_law_map(econ)
        for ind in get_indicators(None):
            comp = rank_lab.components(econ, ind.indicator_id, provs)   # bm/dense/bonus/penalty
            cross = full_cross(econ, ind.indicator_id, provs)
            base = [0.65 * comp.bm[i] + 0.35 * (comp.dense[i] if comp.dense else 0.0)
                    + comp.bonus[i] - comp.penalty[i] for i in range(len(provs))]
            order_base = sorted(range(len(provs)), key=lambda i: base[i], reverse=True)
            group = [t for t in live if t.economy == econ and t.indicator_id == ind.indicator_id]
            for pool in a.pools:
                inpool = set(order_base if pool == 0 else order_base[:pool])
                fused = [0.5 * max(0.0, base[i]) + 0.5 * (cross[i] if i in inpool else 0.0)
                         for i in range(len(provs))]
                order = sorted(range(len(provs)), key=lambda i: fused[i], reverse=True)
                pos = {idx: r + 1 for r, idx in enumerate(order)}
                for t in group:
                    idx = pid_index.get(t.matched_provision_id)
                    if idx is None:
                        continue
                    ranks[pool][id(t)] = pos[idx]
                    for k in a.k:
                        if pos[idx] <= k:
                            hits[(pool, k)].add(id(t))
                        elif not t.sections and any(
                                v2l.get(provs[i].doc_id) == t.law_id for i in order[:k]):
                            hits[(pool, k)].add(id(t))
            print(f"[e4] {econ} {ind.indicator_id} done ({time.perf_counter()-t0:.0f}s)")

    print("\n=== E4: cross-encoder pool vs recall ===")
    print(f"{'CE pool':>10} {'K':>5} {'ACT recall':>14} {'ALL recall':>14}")
    rows = []
    for pool in a.pools:
        for k in a.k:
            na = sum(1 for t in acts if id(t) in hits[(pool, k)])
            nl = sum(1 for t in live if id(t) in hits[(pool, k)])
            label = "ALL" if pool == 0 else str(pool)
            print(f"{label:>10} {k:5} {na/max(len(acts),1):6.3f} {f'{na}/{len(acts)}':>7} "
                  f"{nl/max(len(live),1):6.3f} {f'{nl}/{len(live)}':>7}")
            rows.append({"ce_pool": label, "k": k, "act": f"{na}/{len(acts)}",
                         "all": f"{nl}/{len(live)}"})

    print("\n=== rank of each statute target, by CE pool ===")
    hdr = "  " + " ".join(f"{('ALL' if p==0 else p):>7}" for p in a.pools)
    print(f"{'target':44}{hdr}")
    for t in sorted(acts, key=lambda t: ranks[a.pools[0]].get(id(t), 10**9)):
        cells = " ".join(f"{ranks[p].get(id(t), -1):>7}" for p in a.pools)
        print(f"{t.economy+' '+t.indicator_id+' '+t.law_label[:28]:44}  {cells}")
    med = {("ALL" if p == 0 else p): statistics.median(list(ranks[p].values()) or [0])
           for p in a.pools}
    print("\nmedian rank of a statute target by pool:", med)
    Path(a.out).write_text(json.dumps({"table": rows, "median_rank": med}, indent=1),
                           encoding="utf-8")
    print("written:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
