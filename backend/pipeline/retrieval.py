"""ZONE 2c — retrieval.

Indicator-grounded retrieval: for each RDTII indicator we build a query from its
title + query_terms and rank candidate provisions. This is the grounding layer —
the mapper only ever sees provisions surfaced here, never the whole corpus, which
is what keeps mappings citation-bound.

Default ranker is BM25 (rank_bm25) with a transparent pure-Python fallback so the
pipeline runs even if the dependency is missing. A dense FAISS/Chroma stage can be
added behind `retrieve()` without changing callers (see ARCHITECTURE.md).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from ..rdtii import get_indicator
from ..schemas import Provision

_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Retrieved:
    provision: Provision
    score: float            # normalised 0..1
    raw_context: str        # the window the mapper sees
    log: list[str]


class _FallbackBM25:
    """Minimal BM25 used only if rank_bm25 isn't installed."""
    def __init__(self, corpus: list[list[str]], k1=1.5, b=0.75):
        self.corpus, self.k1, self.b = corpus, k1, b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.N, 1)
        self.df = Counter()
        for d in corpus:
            for w in set(d):
                self.df[w] += 1
        self.tf = [Counter(d) for d in corpus]

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def get_scores(self, query: list[str]) -> list[float]:
        scores = []
        for i, d in enumerate(self.corpus):
            s = 0.0
            for term in query:
                if term not in self.tf[i]:
                    continue
                freq = self.tf[i][term]
                denom = freq + self.k1 * (1 - self.b + self.b * len(d) / max(self.avgdl, 1))
                s += self._idf(term) * (freq * (self.k1 + 1)) / denom
            scores.append(s)
        return scores


def _build_bm25(corpus: list[list[str]]):
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi(corpus)
    except Exception:
        return _FallbackBM25(corpus)


def retrieve(indicator_id: str, provisions: list[Provision], top_k: int = 5) -> list[Retrieved]:
    ind = get_indicator(indicator_id)
    if ind is None or not provisions:
        return []
    corpus = [_tok(p.law_name + " " + p.article_section + " " + p.verbatim_snippet) for p in provisions]
    bm25 = _build_bm25(corpus)
    query = _tok(ind.title + " " + " ".join(ind.query_terms))
    scores = list(bm25.get_scores(query))
    smax = max(scores) if scores and max(scores) > 0 else 1.0

    ranked = sorted(zip(provisions, scores), key=lambda x: x[1], reverse=True)[:top_k]
    out: list[Retrieved] = []
    for p, raw in ranked:
        norm = round(raw / smax, 3)
        if norm <= 0:
            continue
        log = [
            f"indicator={indicator_id} query='{' '.join(query[:8])}...'",
            f"bm25_raw={round(raw,3)} normalised={norm} provision={p.provision_id}",
        ]
        out.append(Retrieved(provision=p, score=norm, raw_context=p.verbatim_snippet, log=log))
    return out
