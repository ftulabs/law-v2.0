"""Experiments E0/E1: can we recover the "right law, wrong section" losses without waste?

The failure being attacked: for 14 pieces of panel evidence the containing law IS in the
shortlist (median best rank 24) but the cited section is not, because a flat global top-K
spends its budget on breadth across laws instead of depth inside the few that matter.

The open question — raised as an objection to the proposal and treated here as the main
experimental axis — is HOW to decide that a law deserves depth. Ranking laws by their single
best provision (`max`) is exactly the case where one lucky provision drags in a law that is
otherwise irrelevant, and we then pay to grade dozens of its sections. So the law score is
swept over four definitions, from "one good hit is enough" to "prove sustained relevance":

    max         best provision's global score          (the naive, objected-to version)
    mean_top3   mean of the law's three best           (needs more than one good provision)
    sum_top5    sum of the law's five best             (rewards concentration of relevance)
    count_topk  how many of the law's provisions are   (purely density-based)
                already inside the global top-K

and a `waste` metric is reported alongside recall: the share of pass-2 candidates drawn from
laws that contribute no panel evidence at all. That is the cost the objection is about.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from ..schemas import Provision
from . import rank_lab
from .rank_lab import RankConfig


@dataclass
class DepthConfig:
    """Pass 1 (global top-K) + pass 2 (depth inside laws already in contention)."""
    k: int = 300                    # pass-1 global budget
    law_score: str = "mean_top3"    # max | mean_top3 | sum_top5 | count_topk
    n_laws: int = 0                 # 0 = pass 2 disabled (flat top-K baseline)
    m_per_law: int = 0              # provisions taken from each law in contention
    adaptive: bool = False          # scale m with law size (candidate C)
    neighbours: int = 0             # candidate D: admit +/-N adjacent sections of a hit
    name: str = ""

    def label(self) -> str:
        if self.name:
            return self.name
        if not self.n_laws:
            return f"flat K={self.k}"
        return (f"K={self.k} N={self.n_laws} m={self.m_per_law} score={self.law_score}"
                + (" adaptive" if self.adaptive else "")
                + (f" nb={self.neighbours}" if self.neighbours else ""))


def _law_scores(provisions, scores, idxs, how: str, topk_set: set[int]) -> dict[str, float]:
    by_law: dict[str, list[float]] = {}
    hits: dict[str, int] = {}
    for i in idxs:
        lid = provisions[i].doc_id
        by_law.setdefault(lid, []).append(scores[i])
        if i in topk_set:
            hits[lid] = hits.get(lid, 0) + 1
    out = {}
    for lid, v in by_law.items():
        v = sorted(v, reverse=True)
        if how == "max":
            out[lid] = v[0]
        elif how == "mean_top3":
            out[lid] = statistics.mean(v[:3])
        elif how == "sum_top5":
            out[lid] = sum(v[:5])
        elif how == "count_topk":
            out[lid] = float(hits.get(lid, 0))
        else:
            out[lid] = v[0]
    return out


def _adaptive_m(base: int, n_provisions: int) -> int:
    import math
    return max(3, min(40, round(base * math.log2(max(n_provisions, 2)) / 6)))


def shortlist(indicator_id: str, provisions: list[Provision], cfg: DepthConfig,
              economy: str) -> tuple[list[int], set[int]]:
    """Returns (ordered candidate indices, indices contributed only by pass 2)."""
    comp = rank_lab.components(economy, indicator_id, provisions)
    base = RankConfig(alpha=0.65, cross_weight=0.5, dense_recall_extra=0)
    scores = rank_lab.fuse(comp, base)
    order = sorted(range(len(provisions)), key=lambda i: scores[i], reverse=True)

    pass1 = order[:cfg.k]
    chosen = list(pass1)
    seen = set(pass1)
    added: set[int] = set()

    if cfg.n_laws and cfg.m_per_law:
        topk_set = set(pass1)
        laws = _law_scores(provisions, scores, order[:max(cfg.k, 1000)], cfg.law_score, topk_set)
        # only laws that actually appear in pass 1 can be "in contention"
        in_play = {provisions[i].doc_id for i in pass1}
        ranked_laws = [lid for lid, _ in sorted(laws.items(), key=lambda kv: kv[1], reverse=True)
                       if lid in in_play][:cfg.n_laws]
        by_law: dict[str, list[int]] = {}
        for i in order:
            by_law.setdefault(provisions[i].doc_id, []).append(i)
        for lid in ranked_laws:
            m = cfg.m_per_law
            if cfg.adaptive:
                m = _adaptive_m(cfg.m_per_law, len(by_law.get(lid, [])))
            for i in by_law.get(lid, [])[:m]:
                if i not in seen:
                    seen.add(i)
                    chosen.append(i)
                    added.add(i)

    if cfg.neighbours:
        import re
        num = re.compile(r"(\d{1,4})")
        by_law_sec: dict[str, dict[int, int]] = {}
        for i, p in enumerate(provisions):
            m = num.search(p.article_section or "")
            if m:
                by_law_sec.setdefault(p.doc_id, {})[int(m.group(1))] = i
        for i in list(chosen):
            p = provisions[i]
            m = num.search(p.article_section or "")
            if not m:
                continue
            n = int(m.group(1))
            for d in range(1, cfg.neighbours + 1):
                for cand in (by_law_sec.get(p.doc_id, {}).get(n - d),
                             by_law_sec.get(p.doc_id, {}).get(n + d)):
                    if cand is not None and cand not in seen:
                        seen.add(cand)
                        chosen.append(cand)
                        added.add(cand)
    return chosen, added
