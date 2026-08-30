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
from ..rdtii.query_terms_i18n import native_terms
from ..schemas import Provision
from . import retrieval
from ..providers.llm_factory import SECTORAL_MARKERS

_CE: dict[str, object] = {}          # model name → loaded CrossEncoder
_CE_FAILED: set[str] = set()         # model names that could not be loaded


def _ce_model_for(economy: str | None) -> str | None:
    """The reranker for this economy's LANGUAGE, or None to run without one.

    Keyed on language, not script. The shipped cross-encoder is English-only, and it is no
    less out of its depth on Indonesian or Portuguese — both Latin-script — than on Chinese.
    Its score is fused into the ranking at the same weight as BM25, so an off-language
    reranker actively degrades the result rather than merely failing to help.
    """
    from ..providers.ocr_languages import is_english_text
    if is_english_text(economy):
        return settings.cross_encoder_model
    if not settings.cross_encoder_multilingual_enabled:
        return None            # see settings.cross_encoder_multilingual_enabled — 25x slower
    return settings.cross_encoder_model_multilingual


def _cross_encoder(economy: str | None = None):
    """Lazy cross-encoder for this economy's script; None if disabled or unavailable.

    A non-Latin economy gets the multilingual reranker or nothing at all — it never silently
    falls back to the English model, because an English cross-encoder on Chinese text scores
    worse than having no reranker in the fusion.
    """
    if (settings.cross_encoder or "auto").lower() == "off":
        return None
    name = _ce_model_for(economy)
    if name is None:
        return None
    if name in _CE:
        return _CE[name]
    if name in _CE_FAILED:
        return None
    try:
        from sentence_transformers import CrossEncoder
        _CE[name] = CrossEncoder(name)
    except Exception:
        _CE_FAILED.add(name)
        return None
    return _CE[name]


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
    # Zone 1 ranks laws by the same lexical+dense fusion as Zone 2, so it needs the same
    # native vocabulary: without it every Chinese law scores 0 on the keyword signal and the
    # whole ranking rests on the embeddings alone.
    econ = retrieval._economy_of(provisions)
    native = native_terms(indicator_id, econ)
    query = f"{ind.title}. {ind.legal_test} {' '.join(ind.query_terms)}"
    lexical_query = f"{query} {' '.join(native)}"

    # ── per-provision lexical (BM25) + semantic (bi-encoder) ──
    corpus = [retrieval._tok(p.verbatim_snippet + " " + p.article_section) for p in provisions]
    bm25 = retrieval._build_bm25(corpus)
    kw = list(bm25.get_scores(retrieval._tok(lexical_query)))
    kwmax = max(kw) if kw and max(kw) > 0 else 1.0
    kw = [s / kwmax for s in kw]
    sem = retrieval._dense_scores(query, provisions) or [0.0] * len(provisions)

    # ── phrase-presence bonus per provision ──
    phrases = retrieval._phrases(ind, native)
    phrase_bonus = [0.15 if any(ph in p.verbatim_snippet.lower() for ph in phrases) else 0.0
                    for p in provisions]

    # ── aggregate to the law: keep its single best-matching provision (the evidence) ──
    best: dict[str, tuple[int, float]] = {}
    for i, p in enumerate(provisions):
        combined = sem[i] + kw[i] + phrase_bonus[i]
        if p.doc_id not in best or combined > best[p.doc_id][1]:
            best[p.doc_id] = (i, combined)
    doc_kw = {d: kw[i] for d, (i, _) in best.items()}
    doc_sem = {d: sem[i] for d, (i, _) in best.items()}

    # ── cross-encoder precision rerank on each law's best provision ──
    doc_cross: dict[str, float] = {}
    ce = _cross_encoder(econ)
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
