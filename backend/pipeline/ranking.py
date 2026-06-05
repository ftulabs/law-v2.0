"""ZONE 1 ranking — multi-signal, CONTENT-grounded.

The ESCAP trial ranked by (semantic + keyword) over Act TITLES and flagged the failure
mode themselves: an Act ranks top merely for a word in its *name* (a Water-Supply-Fund
Act scoring high for a Public-Procurement pillar because its title says "financial /
accounting"). We defeat that by ranking on the law's actual PROVISION TEXT and fusing
four independent signals so no single title word can dominate:

    keyword   BM25 of the indicator's terms over the law's provisions   (lexical)
    semantic  best provision↔indicator cosine, bi-encoder               (dense meaning)
    cross     cross-encoder relevance of the best provision             (precision rerank)
    scope     ×penalty when a sectoral instrument meets a national indicator
    final     Reciprocal-Rank Fusion of {keyword, semantic, cross} × scope

RRF is rank-based, so a freakishly high keyword score on an irrelevant title cannot run
away with the result — it must also rank well on meaning AND survive the cross-encoder.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import settings
from ..rdtii import get_indicator
from ..schemas import Provision
from . import retrieval
from ..providers.llm_factory import SECTORAL_MARKERS

_CE = None
_CE_FAILED = False


def _cross_encoder():
    """Lazy cross-encoder; None if disabled/unavailable (→ fusion uses the other signals)."""
    global _CE, _CE_FAILED
    if (settings.cross_encoder or "auto").lower() == "off" or _CE_FAILED:
        return _CE
    if _CE is not None:
        return _CE
    try:
        from sentence_transformers import CrossEncoder
        _CE = CrossEncoder(settings.cross_encoder_model)
    except Exception:
        _CE_FAILED = True
    return _CE


@dataclass
class DocRank:
    doc_id: str
    law_name: str
    source_url: str
    keyword: float
    semantic: float
    cross: float
    scope: float
    final: float
    best_provision: Provision
    indicator_id: str = ""


def _rank_positions(values: dict[str, float]) -> dict[str, int]:
    order = sorted(values, key=lambda k: values[k], reverse=True)
    return {doc_id: i for i, doc_id in enumerate(order)}


def rank_documents(indicator_id: str, provisions: list[Provision]) -> list[DocRank]:
    """Rank candidate LAWS for one indicator, grounded in their provision text."""
    ind = get_indicator(indicator_id)
    if ind is None or not provisions:
        return []
    query = f"{ind.title}. {ind.legal_test} {' '.join(ind.query_terms)}"

    # ── per-provision lexical (BM25) + semantic (bi-encoder) ──
    corpus = [retrieval._tok(p.verbatim_snippet + " " + p.article_section) for p in provisions]
    bm25 = retrieval._build_bm25(corpus)
    kw = list(bm25.get_scores(retrieval._tok(query)))
    kwmax = max(kw) if kw and max(kw) > 0 else 1.0
    kw = [s / kwmax for s in kw]
    sem = retrieval._dense_scores(query, provisions) or [0.0] * len(provisions)

    # ── aggregate to the law: keep its single best-matching provision (the evidence) ──
    best: dict[str, tuple[int, float]] = {}
    for i, p in enumerate(provisions):
        combined = sem[i] + kw[i]
        if p.doc_id not in best or combined > best[p.doc_id][1]:
            best[p.doc_id] = (i, combined)
    doc_kw = {d: kw[i] for d, (i, _) in best.items()}
    doc_sem = {d: sem[i] for d, (i, _) in best.items()}

    # ── cross-encoder precision rerank on each law's best provision ──
    doc_cross: dict[str, float] = {}
    ce = _cross_encoder()
    if ce is not None:
        keys = list(best.keys())
        pairs = [(query, provisions[best[d][0]].verbatim_snippet[:512]) for d in keys]
        try:
            for d, s in zip(keys, ce.predict(pairs)):
                doc_cross[d] = 1.0 / (1.0 + math.exp(-float(s)))   # sigmoid → 0..1
        except Exception:
            doc_cross = {}

    # ── Reciprocal-Rank Fusion of the available signals ──
    rank_lists = [_rank_positions(doc_kw), _rank_positions(doc_sem)]
    if doc_cross:
        rank_lists.append(_rank_positions(doc_cross))
    k = settings.rrf_k
    rrf: dict[str, float] = {}
    for rl in rank_lists:
        for d, r in rl.items():
            rrf[d] = rrf.get(d, 0.0) + 1.0 / (k + r + 1)

    # ── scope penalty + assemble ──
    out: list[DocRank] = []
    for d, (i, _) in best.items():
        p = provisions[i]
        sectoral = any(m in (p.verbatim_snippet + " " + p.law_name).lower() for m in SECTORAL_MARKERS)
        scope = 0.6 if (ind.scope == "national" and sectoral) else 1.0
        out.append(DocRank(
            doc_id=d, law_name=p.law_name, source_url=p.source_url,
            keyword=round(doc_kw[d], 4), semantic=round(doc_sem[d], 4),
            cross=round(doc_cross.get(d, 0.0), 4), scope=scope,
            final=round(rrf[d] * scope, 5), best_provision=p, indicator_id=indicator_id))
    out.sort(key=lambda x: x.final, reverse=True)
    return out
