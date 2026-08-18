"""Parameterised re-implementation of the retrieval stack, for sweeping.

Production `retrieval.retrieve()` reads its knobs from global settings and hard-codes the
fusion weights, so it cannot be swept. This module composes the SAME primitives
(`_build_bm25`, `_dense_scores`, `_phrase_bonus`, `_sibling_penalty`, `_cross_scores`) behind
an explicit config object, so every parameter can be varied and measured. The winning config
is then ported back into `retrieval.py` — nothing here ships in the request path.

Component scores are computed ONCE per (economy, indicator) and cached, because embedding and
cross-encoding dominate runtime and are independent of the fusion weights being swept. The
one approximation: cross-encoder scores are computed over the top `ce_pool` candidates ranked
by an equal-weight blend, then reused for every alpha. A candidate outside that pool could in
principle be promoted by an extreme alpha; `ce_pool` is set far wider than any shortlist under
test so that cannot bite.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..pipeline import retrieval as R
from ..rdtii import get_indicator
from ..schemas import Provision


@dataclass
class RankConfig:
    # ── fusion ──
    alpha: float = 0.5              # weight on BM25 vs dense in the base blend
    use_cross: bool = True
    cross_weight: float = 0.5       # final = (1-w)*blend + w*cross
    phrase_bonus: bool = True
    sibling_penalty: bool = True
    # ── recall guarantees ──
    dense_recall_extra: int = 0     # admit N strongest pure-dense matches the blend dropped
    dense_recall_floor: float = 0.55
    # ── shortlist shape ──
    k: int = 40                     # candidates handed to the grader per indicator
    per_law_k: int = 0              # reserved slots per law (0 = pure global ranking)
    law_prefilter: int = 0          # 0 = off; else keep provisions from the top-N laws only
    law_score: str = "max"          # how a law is scored from its provisions: max | mean_top3
    min_score: float = 0.0          # drop candidates below this fused score
    name: str = ""

    def label(self) -> str:
        return self.name or (
            f"k={self.k} perlaw={self.per_law_k} a={self.alpha} ce={self.cross_weight}"
            f"{' pre=' + str(self.law_prefilter) if self.law_prefilter else ''}")


@dataclass
class Components:
    """Alpha-independent score vectors for one (economy, indicator)."""
    bm: list[float]
    dense: list[float] | None
    bonus: list[float]
    penalty: list[float]
    cross: list[float] | None
    ids: list[str] = field(default_factory=list)


_cache: dict[tuple[str, str], Components] = {}
CE_POOL = 400


def components(economy: str, indicator_id: str, provisions: list[Provision]) -> Components:
    key = (economy, indicator_id)
    hit = _cache.get(key)
    if hit is not None and len(hit.bm) == len(provisions):
        return hit
    ind = get_indicator(indicator_id)
    corpus = [R._tok(p.law_name + " " + p.article_section + " "
                     + p.verbatim_snippet[:R._RETRIEVAL_SNIPPET_LEN]) for p in provisions]
    bm25 = R._build_bm25(corpus)
    query = R._tok(f"{ind.title} {ind.description} {ind.legal_test} {' '.join(ind.query_terms)}")
    bm = list(bm25.get_scores(query))
    bmax = max(bm) if bm and max(bm) > 0 else 1.0
    bm_norm = [s / bmax for s in bm]

    dense = R._dense_scores(f"{ind.description} {ind.legal_test}", provisions,
                            must_embed=set(range(len(provisions))))
    bonus = R._phrase_bonus(ind, provisions)
    penalty = R._sibling_penalty(ind, provisions)

    base = [0.5 * bm_norm[i] + 0.5 * (dense[i] if dense else 0.0) for i in range(len(provisions))]
    cross = R._cross_scores(f"{ind.title}. {ind.legal_test} Keywords: {' '.join(ind.query_terms)}",
                            provisions, base, max(1, CE_POOL // 3))
    comp = Components(bm=bm_norm, dense=dense, bonus=bonus, penalty=penalty, cross=cross,
                      ids=[p.provision_id for p in provisions])
    _cache[key] = comp
    return comp


def fuse(comp: Components, cfg: RankConfig) -> list[float]:
    n = len(comp.bm)
    a = cfg.alpha if comp.dense is not None else 1.0
    out = []
    for i in range(n):
        s = a * comp.bm[i] + (1 - a) * (comp.dense[i] if comp.dense else 0.0)
        if cfg.phrase_bonus:
            s += comp.bonus[i]
        if cfg.sibling_penalty:
            s = max(0.0, s - comp.penalty[i])
        if cfg.use_cross and comp.cross is not None:
            s = (1 - cfg.cross_weight) * s + cfg.cross_weight * comp.cross[i]
        out.append(s)
    return out


def _law_scores(provisions: list[Provision], scores: list[float], how: str) -> dict[str, float]:
    by_law: dict[str, list[float]] = {}
    for p, s in zip(provisions, scores):
        by_law.setdefault(p.doc_id, []).append(s)
    if how == "mean_top3":
        return {k: sum(sorted(v, reverse=True)[:3]) / min(3, len(v)) for k, v in by_law.items()}
    return {k: max(v) for k, v in by_law.items()}


def shortlist(indicator_id: str, provisions: list[Provision], cfg: RankConfig,
              economy: str) -> list[tuple[Provision, float]]:
    comp = components(economy, indicator_id, provisions)
    scores = fuse(comp, cfg)

    idxs = list(range(len(provisions)))
    if cfg.law_prefilter:
        laws = _law_scores(provisions, scores, cfg.law_score)
        keep_laws = {lid for lid, _ in sorted(laws.items(), key=lambda kv: kv[1],
                                              reverse=True)[:cfg.law_prefilter]}
        idxs = [i for i in idxs if provisions[i].doc_id in keep_laws]

    chosen: dict[int, float] = {}
    # 1. per-law reservation (round-robin by rank, score-ordered within a rank pass)
    if cfg.per_law_k > 0:
        by_law: dict[str, list[int]] = {}
        for i in idxs:
            by_law.setdefault(provisions[i].doc_id, []).append(i)
        ranked_per_law = {lid: sorted(v, key=lambda i: scores[i], reverse=True)[:cfg.per_law_k]
                          for lid, v in by_law.items()}
        depth = max((len(v) for v in ranked_per_law.values()), default=0)
        for rank in range(depth):
            at_rank = sorted((v[rank] for v in ranked_per_law.values() if rank < len(v)),
                             key=lambda i: scores[i], reverse=True)
            for i in at_rank:
                if len(chosen) >= cfg.k:
                    break
                chosen.setdefault(i, scores[i])
    # 2. fill with the globally best
    for i in sorted(idxs, key=lambda i: scores[i], reverse=True):
        if len(chosen) >= cfg.k:
            break
        chosen.setdefault(i, scores[i])
    # 3. semantic-recall guarantee
    if cfg.dense_recall_extra and comp.dense is not None:
        extra = cfg.dense_recall_extra
        for i in sorted(idxs, key=lambda i: comp.dense[i], reverse=True):
            if extra <= 0:
                break
            if i not in chosen and comp.dense[i] >= cfg.dense_recall_floor:
                chosen[i] = scores[i]
                extra -= 1

    out = [(provisions[i], s) for i, s in chosen.items() if s > cfg.min_score]
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def selector(cfg: RankConfig, economy: str):
    """Adapter for harness.evaluate — returns objects exposing `.provision`."""
    class _R:
        __slots__ = ("provision", "score")

        def __init__(self, p, s):
            self.provision, self.score = p, s

    def _sel(indicator_id: str, provisions: list[Provision]):
        return [_R(p, s) for p, s in shortlist(indicator_id, provisions, cfg, economy)]
    return _sel


def baseline_config(n_provisions: int) -> RankConfig:
    """Exactly what ships today: k = clamp(ceil(n*0.05), 20, 40), per-law reservation 3,
    alpha 0.5, 50/50 cross-encoder blend, dense recall extra = max(2, k//3)."""
    import math

    from ..config import settings
    k = min(n_provisions, settings.retrieve_max_top_k,
            max(5, settings.retrieve_top_k, math.ceil(n_provisions * settings.retrieve_fraction)))
    return RankConfig(k=k, per_law_k=settings.retrieve_per_law_k, alpha=settings.hybrid_alpha,
                      cross_weight=0.5, dense_recall_extra=max(2, k // 3),
                      dense_recall_floor=settings.dense_recall_floor, name="baseline(shipped)")
