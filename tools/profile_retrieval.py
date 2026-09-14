#!/usr/bin/env python3
"""Sub-stage profile of `retrieval.retrieve()` on a real corpus.

Stage totals say retrieval is expensive; they do not say WHICH PART. This times each phase
separately, per indicator, so an optimisation targets the phase that actually costs.

    python tools/profile_retrieval.py --economy SG --pillar 7
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings                                    # noqa: E402
from backend.pipeline import retrieval                                 # noqa: E402
from backend.rdtii import get_indicator, get_indicators                # noqa: E402
from backend.rdtii.query_terms_i18n import native_terms                # noqa: E402
from backend.schemas import resolve_economy                            # noqa: E402
from tools.bench_bm25_cache import load_provisions                     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", default="SG")
    ap.add_argument("--pillar", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=80)
    a = ap.parse_args()

    econ = resolve_economy(a.economy)
    provs = load_provisions(econ, a.pillar)
    print(f"corpus: {len(provs)} provisions · dense={retrieval._dense_enabled()} "
          f"· model={'loaded' if retrieval._get_model() else 'UNAVAILABLE'}\n")
    if not provs:
        return 1

    t = defaultdict(float)
    retrieval._BM25_CACHE.clear()

    for ind in get_indicators(a.pillar):
        t0 = time.perf_counter(); corpus, bm25 = retrieval._corpus_and_bm25(provs)
        t["1 corpus+bm25 build"] += time.perf_counter() - t0

        econ_code = retrieval._economy_of(provs)
        native = native_terms(ind.indicator_id, econ_code)
        q = retrieval._tok(f"{ind.title} {ind.description} {ind.legal_test} "
                           f"{' '.join(ind.query_terms)} {' '.join(native)}")
        t0 = time.perf_counter(); bm = list(bm25.get_scores(q))
        t["2 bm25 scoring"] += time.perf_counter() - t0

        keep = set(sorted(range(len(provs)), key=lambda i: bm[i], reverse=True)[:max(80, a.top_k*3)])
        t0 = time.perf_counter()
        dense = retrieval._dense_scores(f"{ind.description} {ind.legal_test}", provs, must_embed=keep)
        t["3 dense embed+score"] += time.perf_counter() - t0

        t0 = time.perf_counter(); retrieval._phrase_bonus(ind, provs, native)
        t["4 phrase bonus"] += time.perf_counter() - t0

        t0 = time.perf_counter(); retrieval._sibling_penalty(ind, provs)
        t["5 sibling penalty"] += time.perf_counter() - t0

        bmax = max(bm) if bm and max(bm) > 0 else 1.0
        alpha = settings.hybrid_alpha if dense is not None else 1.0
        comb = [alpha*(bm[i]/bmax) + (1-alpha)*(dense[i] if dense else 0.0)
                for i in range(len(provs))]
        ce_q = f"{ind.title}. {ind.legal_test} Keywords: {' '.join(ind.query_terms)}"
        t0 = time.perf_counter()
        retrieval._cross_scores(ce_q, provs, comb, a.top_k, econ_code)
        t["6 cross-encoder"] += time.perf_counter() - t0

    total = sum(t.values())
    print(f"{'phase':26} {'seconds':>9} {'share':>7}")
    for k in sorted(t):
        print(f"{k:26} {t[k]:>9.2f} {t[k]/total*100:>6.1f}%")
    print(f"{'TOTAL':26} {total:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
