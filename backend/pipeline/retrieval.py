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
_RETRIEVAL_SNIPPET_LEN = 2048   # chars fed to embedding model (MiniLM ~512 tokens ≈ 2k chars)


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


def _dense_scores(dense_query: str, provisions: list[Provision]):
    """Cosine similarity (0..1) of each provision to the query, or None if disabled.

    Provision text: article_section + first 2 k chars of snippet (no law_name — the law name
    dominates embeddings and makes every PDPA section look like a P7-I1 hit regardless of
    what the section actually says). The embedding model max sequence is ~512 tokens ≈ 2k chars
    so longer snippets are silently truncated anyway; being explicit avoids wasted encoding.
    """
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
            to_embed.append(f"{p.article_section}: {p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN]}")
    if to_embed:
        embs = _embed(to_embed)
        if embs is None:
            return None                 # model unavailable → signal BM25-only
        for j, i in enumerate(idx_map):
            cached[i] = embs[j].tolist()
            _EMB_CACHE[provisions[i].provision_id] = cached[i]
    qv = _embed([dense_query])
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


def _phrase_bonus(ind, provisions: list[Provision]) -> list[float]:
    """Bonus for multi-word query terms appearing literally in the provision text.
    Multiple phrase hits accumulate (capped at 0.30) so a provision matching several of
    the indicator's own phrases ranks clearly above one with just one incidental match."""
    bonuses = [0.0] * len(provisions)
    phrases = [qt.lower() for qt in (ind.query_terms or []) if len(qt.split()) >= 2]
    if not phrases:
        return bonuses
    for i, p in enumerate(provisions):
        text_lower = p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN].lower()
        count = sum(1 for ph in phrases if ph in text_lower)
        bonuses[i] = min(0.30, count * 0.10)
    return bonuses


def _sibling_penalty(ind, provisions: list[Provision]) -> list[float]:
    """Down-score provisions whose text is dominated by a sibling indicator's phrases.

    P6-I1↔P6-I4 (ban vs conditional) and P7-I1↔P7-I2 (data-protection vs cybersecurity)
    are the most commonly confused pairs. If a provision contains more sibling multi-word
    phrases than target phrases, it is likely a mislabel at retrieval time — penalise it so
    the expensive LLM grading call is spent elsewhere.
    """
    from ..rdtii import siblings as _get_siblings
    sibs = _get_siblings(ind.indicator_id)
    if not sibs:
        return [0.0] * len(provisions)

    target_phrases = [qt.lower() for qt in (ind.query_terms or []) if len(qt.split()) >= 2]
    penalties = [0.0] * len(provisions)

    for sib in sibs:
        sib_phrases = [qt.lower() for qt in (sib.query_terms or []) if len(qt.split()) >= 2]
        if not sib_phrases:
            continue
        for i, p in enumerate(provisions):
            text_lower = p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN].lower()
            sib_hits = sum(1 for ph in sib_phrases if ph in text_lower)
            target_hits = sum(1 for ph in target_phrases if ph in text_lower)
            if sib_hits > 0 and sib_hits > target_hits:
                excess = sib_hits - target_hits
                penalties[i] = max(penalties[i], min(0.20, excess * 0.07))

    return penalties


def retrieve(indicator_id: str, provisions: list[Provision], top_k: int = 5) -> list[Retrieved]:
    ind = get_indicator(indicator_id)
    if ind is None or not provisions:
        return []

    # BM25 corpus: law_name kept for document-level discrimination (IDF handles it naturally);
    # snippet capped at _RETRIEVAL_SNIPPET_LEN to avoid long boilerplate dominating scores.
    corpus = [_tok(p.law_name + " " + p.article_section + " "
                   + p.verbatim_snippet[:_RETRIEVAL_SNIPPET_LEN]) for p in provisions]
    bm25 = _build_bm25(corpus)

    # BM25 query: title + description + legal_test gives a much richer vocabulary than
    # query_terms alone. The legal_test includes "Distinguish from X" notes whose key terms
    # (e.g. "consent", "ban", "cybersecurity") discriminate confusable indicator pairs at the
    # BM25 stage — before the expensive cross-encoder rerank.
    bm25_query_text = (
        f"{ind.title} {ind.description} {ind.legal_test} {' '.join(ind.query_terms)}"
    )
    query = _tok(bm25_query_text)
    bm = list(bm25.get_scores(query))
    bmax = max(bm) if bm and max(bm) > 0 else 1.0
    bm_norm = [s / bmax for s in bm]

    # Dense query: ind.description is already a natural-language question which fits the
    # sentence-embedding model better than a keyword list. Adding legal_test provides the
    # full operative context so the model can distinguish e.g. "consent" (P6-I4) from
    # "retention" (P7-I3) at the semantic level.
    dense_query_text = f"{ind.description} {ind.legal_test}"
    dense = _dense_scores(dense_query_text, provisions)   # None → BM25 only
    alpha = settings.hybrid_alpha if dense is not None else 1.0
    combined = [alpha * bm_norm[i] + (1 - alpha) * (dense[i] if dense else 0.0)
                for i in range(len(provisions))]

    # Phrase-presence bonus: provisions matching multiple indicator phrases rank higher.
    bonus = _phrase_bonus(ind, provisions)
    combined = [combined[i] + bonus[i] for i in range(len(provisions))]

    # Sibling-aware penalty: push down provisions whose text is dominated by a sibling
    # indicator's phrases. Catches P6-I1↔P6-I4 and P7-I1↔P7-I2 confusion before LLM grading.
    penalty = _sibling_penalty(ind, provisions)
    combined = [max(0.0, combined[i] - penalty[i]) for i in range(len(provisions))]

    # Cross-encoder precision rerank over a shortlist: bi-encoder/BM25 get RECALL, the
    # cross-encoder reads (indicator, provision) jointly for PRECISION. Use legal_test
    # (which contains "Distinguish from X" notes) as the cross-encoder query so it can
    # discriminate between indicators with overlapping surface vocabulary.
    ce_query = f"{ind.title}. {ind.legal_test} Keywords: {' '.join(ind.query_terms)}"
    cross = _cross_scores(ce_query, provisions, combined, top_k)
    if cross is not None:
        combined = [0.5 * combined[i] + 0.5 * cross[i] for i in range(len(provisions))]

    ranked = sorted(zip(range(len(provisions)), combined), key=lambda x: x[1], reverse=True)[:top_k]
    out: list[Retrieved] = []
    for i, score in ranked:
        norm = round(score, 3)
        if norm <= 0:
            continue
        p = provisions[i]
        phrase_hit = bonus[i] > 0
        log = [
            f"indicator={indicator_id} bm25_tokens={len(set(query))}",
            (f"hybrid={norm} (bm25={round(bm_norm[i],3)} dense={round(dense[i],3)} "
             f"alpha={alpha} phrase_bonus={bonus[i]:.2f} sibling_penalty={penalty[i]:.2f})"
             if dense is not None else
             f"bm25={norm} (dense off) phrase_bonus={bonus[i]:.2f} "
             f"sibling_penalty={penalty[i]:.2f} provision={p.provision_id}"),
            f"provision={p.provision_id}" + (" [phrase_match]" if phrase_hit else ""),
        ]
        out.append(Retrieved(provision=p, score=norm, raw_context=p.verbatim_snippet, log=log))
    return out
