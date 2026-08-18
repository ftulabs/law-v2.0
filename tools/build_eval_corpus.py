"""Fetch + extract + split the stratified evaluation corpus (see backend/eval/corpus_sample.py).

    python tools/build_eval_corpus.py --economy MY
    python tools/build_eval_corpus.py --economy SG --hard 60 --random 60

Reproducible: the sample is seeded, and the corpus store skips anything already built.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.corpus.build import build            # noqa: E402
from backend.eval.corpus_sample import select     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", required=True)
    ap.add_argument("--hard", type=int, default=60)
    ap.add_argument("--random", type=int, default=60)
    ap.add_argument("--targets-only", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    sel = select(a.economy.upper(), n_hard=a.hard, n_random=a.random)
    laws = sel["targets"] if a.targets_only else (sel["targets"] + sel["hard"] + sel["random"])
    seen, uniq = set(), []
    for law in laws:
        if law["law_id"] not in seen:
            seen.add(law["law_id"])
            uniq.append(law)
    print(f"[eval-corpus] {a.economy.upper()}: {len(uniq)} laws "
          f"(targets={len(sel['targets'])} hard={len(sel['hard'])} random={len(sel['random'])})")
    print(json.dumps(build(a.economy, laws=uniq, extract_workers=a.workers), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
