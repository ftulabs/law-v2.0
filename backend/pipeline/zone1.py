"""ZONE 1 deliverable — Provision Retrieval.

The competition defines Zone 1 as: given (indicator + country) → a RANKED LIST of
relevant legal provisions, sourced by searching the national portals (not a baked
corpus). This module ties the Zone-1 stages together WITHOUT the (hard, deferred)
Zone-2 LLM indicator-mapping:

    discover → fetch bodies → extract provisions → hybrid retrieve (rank)

Output is exactly the Zone-1 contract: per indicator, the top-k provisions with a
relevance score and an audit log of how they were retrieved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings
from ..providers import get_ocr_provider
from ..rdtii import get_indicators
from ..schemas import DiscoveredDoc, Economy, Provision
from . import discovery, extraction, retrieval
from .ocr import get_document_text


@dataclass
class RankedProvision:
    indicator_id: str
    score: float
    provision: Provision
    log: list[str] = field(default_factory=list)


@dataclass
class Zone1Result:
    economy: Economy
    docs: list[DiscoveredDoc]
    provisions: list[Provision]
    ranked: list[RankedProvision]      # flattened, per (indicator, provision)


def find_provisions(
    economy: Economy,
    pillar: int | None = None,
    use_samples: bool = True,
    top_k: int = 5,
    ocr_provider: str | None = None,
    log=print,
) -> Zone1Result:
    pillars = [6, 7] if pillar is None else [pillar]

    # ① discover candidate documents across the requested pillar(s)
    seen, docs = set(), []
    for p in pillars:
        for d in discovery.discover(economy, p, use_samples=use_samples):
            if d.doc_id not in seen:
                seen.add(d.doc_id)
                docs.append(d)
    log(f"[zone1] {len(docs)} candidate documents (live={not use_samples})")

    # ② fetch bodies for live-discovered docs (sample docs already have local_path)
    if not use_samples:
        from .fetch import fetch_to_cache
        for d in docs:
            if d.local_path:
                continue
            fr = fetch_to_cache(d.source_url, log=log)
            if fr:
                d.local_path, d.fmt = fr.local_path, fr.fmt

    # ③ extract provisions (verbatim, section-keyed)
    ocr = get_ocr_provider(ocr_provider) if ocr_provider else get_ocr_provider()
    provisions: list[Provision] = []
    for d in docs:
        raw, metrics = get_document_text(d, ocr_provider=ocr)
        provs = extraction.extract_provisions(d, raw, metrics)
        provisions.extend(provs)
        log(f"[zone1] {d.title[:48]} → {len(provs)} provisions")

    # ④ rank provisions per indicator (hybrid dense+BM25)
    ranked: list[RankedProvision] = []
    for ind in get_indicators(pillar):
        for r in retrieval.retrieve(ind.indicator_id, provisions, top_k=top_k):
            ranked.append(RankedProvision(ind.indicator_id, r.score, r.provision, r.log))
    ranked.sort(key=lambda x: x.score, reverse=True)
    log(f"[zone1] {len(ranked)} ranked (indicator, provision) pairs "
        f"(dense={settings.dense_retrieval})")

    return Zone1Result(economy=economy, docs=docs, provisions=provisions, ranked=ranked)


def rank_laws(economy: Economy, pillar: int, use_samples: bool = True,
              ocr_provider: str | None = None, top_n: int = 5, log=print) -> dict:
    """Zone-1 DOCUMENT ranking per indicator (the judges' output shape): for each
    indicator, the top laws with component scores (keyword/semantic/cross/final) + URL,
    ranked on PROVISION CONTENT (not title) so an irrelevant Act can't win on its name."""
    from . import ranking
    res = find_provisions(economy, pillar, use_samples=use_samples, top_k=8,
                          ocr_provider=ocr_provider, log=log)
    out: dict[str, list] = {}
    for ind in get_indicators(pillar):
        out[ind.indicator_id] = ranking.rank_documents(ind.indicator_id, res.provisions)[:top_n]
    log(f"[zone1] document ranking ready for {len(out)} indicators "
        f"(cross_encoder={settings.cross_encoder})")
    return {"result": res, "by_indicator": out}
