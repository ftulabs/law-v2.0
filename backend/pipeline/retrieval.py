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

from ..config import settings
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


# ── dense (semantic) stage — optional, lazy, cached ──────────────────────────
_MODEL = None            # SentenceTransformer instance (loaded once per process)
_MODEL_FAILED = False
_EMB_CACHE: dict[str, "list[float]"] = {}   # provision_id → embedding (stable within a run)


def _dense_enabled() -> bool:
    mode = (settings.dense_retrieval or "auto").lower()
    return mode in ("on", "auto")


def _get_model():
    """Load the embedding model once. Returns None if unavailable (→ BM25-only)."""
    global _MODEL, _MODEL_FAILED
    if _MODEL is not None or _MODEL_FAILED:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(settings.embed_model)
    except Exception:
        _MODEL_FAILED = True            # not installed / model not downloadable → fall back silently
        _MODEL = None
    return _MODEL


def _embed(texts: list[str]):
    model = _get_model()
    if model is None:
        return None
    import numpy as np
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype="float32")


def _dense_scores(query_text: str, provisions: list[Provision]):
    """Cosine similarity (0..1) of each provision to the query, or None if disabled."""
    if not _dense_enabled():
        return None
    import numpy as np
    to_embed, idx_map = [], []
    cached = [None] * len(provisions)
    for i, p in enumerate(provisions):
        if p.provision_id in _EMB_CACHE:
            cached[i] = _EMB_CACHE[p.provision_id]
        else:
            idx_map.append(i)
            to_embed.append(f"{p.law_name} {p.article_section} {p.verbatim_snippet}")
    if to_embed:
        embs = _embed(to_embed)
        if embs is None:
            return None                 # model unavailable → signal BM25-only
        for j, i in enumerate(idx_map):
            cached[i] = embs[j].tolist()
            _EMB_CACHE[provisions[i].provision_id] = cached[i]
    qv = _embed([query_text])
    if qv is None:
        return None
    mat = np.asarray(cached, dtype="float32")
    sims = (mat @ qv[0])                 # vectors are L2-normalised → dot == cosine
    return [(float(s) + 1.0) / 2.0 for s in sims]   # map [-1,1] → [0,1]


def _cross_scores(query_text: str, provisions: list[Provision], combined: list[float],
                  top_k: int) -> list[float] | None:
    """Cross-encoder relevance (0..1) for the hybrid shortlist; None if the model/setting
    is off. Only the top ~3·top_k hybrid candidates are scored (the rest can't win), so
    the rerank stays cheap. Non-shortlisted provisions keep score 0."""
    from . import ranking
    ce = ranking._cross_encoder()
    if ce is None:
        return None
    import math
    n = min(len(provisions), max(top_k * 3, 8))
    shortlist = sorted(range(len(provisions)), key=lambda i: combined[i], reverse=True)[:n]
    pairs = [(query_text, provisions[i].verbatim_snippet[:512]) for i in shortlist]
    try:
        raw = ce.predict(pairs)
    except Exception:
        return None
    scores = [0.0] * len(provisions)
    for i, s in zip(shortlist, raw):
        scores[i] = 1.0 / (1.0 + math.exp(-float(s)))   # sigmoid → 0..1
    return scores


def retrieve(indicator_id: str, provisions: list[Provision], top_k: int = 5) -> list[Retrieved]:
    ind = get_indicator(indicator_id)
    if ind is None or not provisions:
        return []
    corpus = [_tok(p.law_name + " " + p.article_section + " " + p.verbatim_snippet) for p in provisions]
    bm25 = _build_bm25(corpus)
    query_text = ind.title + " " + " ".join(ind.query_terms)
    query = _tok(query_text)
    bm = list(bm25.get_scores(query))
    bmax = max(bm) if bm and max(bm) > 0 else 1.0
    bm_norm = [s / bmax for s in bm]

    dense = _dense_scores(query_text, provisions)   # None → BM25 only
    alpha = settings.hybrid_alpha if dense is not None else 1.0
    combined = [alpha * bm_norm[i] + (1 - alpha) * (dense[i] if dense else 0.0)
                for i in range(len(provisions))]

    # cross-encoder precision rerank over a shortlist: bi-encoder/BM25 get RECALL, the
    # cross-encoder reads (indicator, provision) jointly for PRECISION, pushing a merely
    # keyword-overlapping provision below one that truly answers the indicator.
    cross = _cross_scores(query_text, provisions, combined, top_k)
    if cross is not None:
        combined = [0.5 * combined[i] + 0.5 * cross[i] for i in range(len(provisions))]

    ranked = sorted(zip(range(len(provisions)), combined), key=lambda x: x[1], reverse=True)[:top_k]
    out: list[Retrieved] = []
    for i, score in ranked:
        norm = round(score, 3)
        if norm <= 0:
            continue
        p = provisions[i]
        log = [
            f"indicator={indicator_id} query='{' '.join(query[:8])}...'",
            (f"hybrid={norm} (bm25={round(bm_norm[i],3)} dense={round(dense[i],3)} alpha={alpha})"
             if dense is not None else
             f"bm25={norm} (dense off) provision={p.provision_id}"),
            f"provision={p.provision_id}",
        ]
        out.append(Retrieved(provision=p, score=norm, raw_context=p.verbatim_snippet, log=log))
    return out
