"""Select the evaluation corpus: every cited law, plus distractors.

Retrieval quality cannot be measured on the answer laws alone — with only targets in the
index every ranking looks perfect. It also cannot be measured on a purely RANDOM sample:
the full 6,529-law corpus contains hundreds of instruments that *talk about* records, access
and security without being the answer, and those are what a retriever actually has to beat.

So the sample is stratified:

  targets  — every law the judges cited that exists in our catalogue (the positives)
  hard     — the laws whose TITLE is closest to the pillar vocabulary (the near-misses that
             will genuinely compete for a top-k slot at full-corpus scale)
  random   — a seeded random draw (keeps the sample unbiased and measures whether obviously
             irrelevant law is correctly ignored)

Title-based hard selection is deliberate: it needs no fetch, so the sample can be chosen
before spending an hour of crawling.
"""
from __future__ import annotations

import random
import re
from collections import Counter

from ..corpus import store
from ..rdtii import get_indicators

_WORD = re.compile(r"[a-z][a-z-]{2,}")
_STOP = {"act", "the", "and", "for", "of", "amendment", "regulations", "code"}


def _pillar_vocab() -> set[str]:
    vocab: set[str] = set()
    for ind in get_indicators(None):
        for field in (ind.title, ind.description, " ".join(ind.query_terms)):
            vocab |= {w for w in _WORD.findall(field.lower()) if w not in _STOP}
    return vocab


def _title_affinity(title: str, vocab: set[str]) -> int:
    return len({w for w in _WORD.findall((title or "").lower())} & vocab)


def select(economy: str, n_hard: int = 60, n_random: int = 60, seed: int = 20260801,
           targets: set[str] | None = None) -> dict:
    """Return {"targets": [...], "hard": [...], "random": [...]} of catalogue rows."""
    from .linkage import target_law_ids
    catalogue = store.list_laws(economy)
    by_id = {r["law_id"]: r for r in catalogue}
    tgt_ids = (targets if targets is not None else target_law_ids().get(economy, set()))
    tgt_ids = {i for i in tgt_ids if i in by_id}

    vocab = _pillar_vocab()
    rest = [r for r in catalogue if r["law_id"] not in tgt_ids]
    ranked = sorted(rest, key=lambda r: _title_affinity(r["title"], vocab), reverse=True)
    hard = ranked[:n_hard]
    hard_ids = {r["law_id"] for r in hard}

    pool = [r for r in rest if r["law_id"] not in hard_ids]
    rnd = random.Random(f"{seed}:{economy}")
    rand = rnd.sample(pool, min(n_random, len(pool)))
    return {"targets": [by_id[i] for i in sorted(tgt_ids)], "hard": hard, "random": rand}


def plan(n_hard: int = 60, n_random: int = 60) -> dict[str, dict]:
    return {e: select(e, n_hard, n_random) for e in ("SG", "AU", "MY")}


if __name__ == "__main__":
    total = 0
    for econ, sel in plan().items():
        n = sum(len(v) for v in sel.values())
        total += n
        print(f"{econ}: targets={len(sel['targets'])} hard={len(sel['hard'])} "
              f"random={len(sel['random'])} -> {n}")
        print("   hard sample:", [r["title"][:44] for r in sel["hard"][:5]])
        print("   collections:", dict(Counter(r["collection"]
                                              for v in sel.values() for r in v)))
    print("TOTAL laws to build:", total)
