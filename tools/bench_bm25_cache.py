#!/usr/bin/env python3
"""Measure the corpus/BM25 memoisation in `retrieval._corpus_and_bm25`, and prove it is a
no-op on ranking.

`retrieve()` is called once per indicator over one provision list. Tokenising the corpus and
building the BM25 index depend only on the corpus, so before the memoisation they were redone
identically on every call — nine times on a both-pillar run.

    python tools/bench_bm25_cache.py --economy SG --pillar 7

Ranking equality is the point of the exercise: a cache that changes an order is not a
speed-up, it is a different system.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline import discovery, extraction, retrieval          # noqa: E402
from backend.pipeline.ocr import get_document_text                     # noqa: E402
from backend.rdtii import get_indicators                               # noqa: E402
from backend.schemas import Economy, resolve_economy                   # noqa: E402


def load_provisions(econ: Economy, pillar: int, log=print):
    """Same chain the orchestrator runs: discover → fetch (cache) → extract → split.

    The fetch is what gives a live-discovered document its `local_path`; discovery alone does
    not, so a warm fetch cache makes this near-instant and a cold one pays the crawl.
    """
    from backend.pipeline.discovery import _resolve_pdf_url
    from backend.pipeline.fetch import fetch_to_cache

    provs = []
    for d in discovery.discover(econ, pillar, use_samples=False, log=lambda *_: None):
        if not d.local_path:
            fr = fetch_to_cache(_resolve_pdf_url(d.economy, d.source_url)[0],
                                log=lambda *_: None)
            if not fr:
                continue
            d.local_path, d.fmt = fr.local_path, fr.fmt
        raw, ocr = get_document_text(d)
        provs += extraction.extract_provisions(d, raw, ocr)
    return provs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", default="SG")
    ap.add_argument("--pillar", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=80)
    a = ap.parse_args()

    econ = resolve_economy(a.economy)
    t = time.perf_counter()
    provs = load_provisions(econ, a.pillar)
    print(f"corpus: {len(provs)} provisions loaded in {time.perf_counter()-t:.1f}s")
    if not provs:
        print("no provisions — run needs a warm fetch/extract cache")
        return 1

    inds = get_indicators(a.pillar)

    def run(label: str) -> tuple[float, dict]:
        retrieval._BM25_CACHE.clear()
        t0 = time.perf_counter()
        order = {}
        for ind in inds:
            got = retrieval.retrieve(ind.indicator_id, provs, top_k=a.top_k)
            order[ind.indicator_id] = [r.provision.provision_id for r in got]
        dt = time.perf_counter() - t0
        print(f"  {label:28} {dt:7.2f}s")
        return dt, order

    # cold = cache cleared before EVERY indicator, i.e. the old behaviour
    retrieval._BM25_CACHE.clear()
    t0 = time.perf_counter()
    cold_order = {}
    for ind in inds:
        retrieval._BM25_CACHE.clear()          # force a rebuild, as the old code did
        got = retrieval.retrieve(ind.indicator_id, provs, top_k=a.top_k)
        cold_order[ind.indicator_id] = [r.provision.provision_id for r in got]
    cold = time.perf_counter() - t0
    print(f"  {'rebuild per indicator (old)':28} {cold:7.2f}s")

    warm, warm_order = run("memoised (new)")

    same = cold_order == warm_order
    print(f"\n{len(inds)} indicators x {len(provs)} provisions")
    print(f"  saved   {cold - warm:.2f}s ({(1 - warm/cold)*100:.0f}%)")
    print(f"  ranking identical: {same}")
    if not same:
        for k in cold_order:
            if cold_order[k] != warm_order[k]:
                print(f"    DIFFERS: {k}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
