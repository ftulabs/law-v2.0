"""ZONE 2d — provision → RDTII indicator mapping (retrieval-grounded).

For each indicator we retrieve candidate provisions, then ask the LLM to grade
ONLY what it was given (verbatim snippet + the indicator's legal test), forbidding
any conclusion not supported by the snippet. The model returns structured signals;
we never let it invent law text, article numbers, or URLs — those are carried from
extraction, not generation. That separation is the core anti-hallucination control.
"""
from __future__ import annotations

import hashlib

from ..providers import get_llm_provider
from ..providers.llm_base import LLMProvider
from ..rdtii import get_indicator
from ..schemas import DiscoveryTag, EvidenceMapping, Provision
from . import confidence
from .retrieval import retrieve

SYSTEM = (
    "You are a legal evidence grader for the UNESCAP RDTII framework. You assess "
    "whether a single statutory provision satisfies a specific indicator's LEGAL "
    "TEST. Rules: (1) Judge ONLY the provided snippet — never rely on outside "
    "knowledge of the law. (2) Distinguish legal relevance (a binding rule of the "
    "right scope) from mere topical/semantic relevance. (3) If the snippet is "
    "sector-specific but the indicator is national in scope, set scope_flag to "
    "'SECTORAL_NOT_NATIONAL' and lower scope_alignment. (4) Never assert a legal "
    "conclusion the snippet does not support. Respond with a JSON object: "
    "{relevant:bool, legal_match:0..1, scope_alignment:0..1, scope_flag:str|null, "
    "rationale:str}."
)


def _user_prompt(ind, prov: Provision) -> str:
    return (
        f"<INDICATOR>{ind.indicator_id} — {ind.title}</INDICATOR>\n"
        f"<INDICATOR_SCOPE>{ind.scope}</INDICATOR_SCOPE>\n"
        f"<LEGAL_TEST>{ind.legal_test}</LEGAL_TEST>\n"
        f"<QUERY_TERMS>{' | '.join(ind.query_terms)}</QUERY_TERMS>\n"
        f"<LAW>{prov.law_name} — {prov.article_section}</LAW>\n"
        f"<SNIPPET>{prov.verbatim_snippet}</SNIPPET>\n"
        "Grade this provision against the indicator. Return the JSON object only."
    )


def _mapping_id(run_id: str, indicator_id: str, provision_id: str) -> str:
    h = hashlib.sha1(f"{run_id}|{indicator_id}|{provision_id}".encode()).hexdigest()[:12]
    return f"map-{h}"


def map_provisions(
    run_id: str,
    provisions: list[Provision],
    pillar: int | None,
    indicators,
    source_texts: dict[str, str] | None = None,
    doc_tags: dict[str, DiscoveryTag] | None = None,
    llm: LLMProvider | None = None,
    top_k: int = 5,
    min_retrieval: float = 0.05,
) -> list[EvidenceMapping]:
    llm = llm or get_llm_provider()
    source_texts = source_texts or {}
    doc_tags = doc_tags or {}
    mappings: list[EvidenceMapping] = []

    for ind in indicators:
        for r in retrieve(ind.indicator_id, provisions, top_k=top_k):
            if r.score < min_retrieval:
                continue
            prov = r.provision
            graded = llm.complete_json(SYSTEM, _user_prompt(ind, prov))

            legal_match = float(graded.get("legal_match", 0.0) or 0.0)
            scope_alignment = float(graded.get("scope_alignment", 0.0) or 0.0)
            scope_flag = graded.get("scope_flag") or None
            rationale = graded.get("rationale", "")

            grounding = confidence.snippet_grounding(
                prov.verbatim_snippet, source_texts.get(prov.doc_id, prov.verbatim_snippet)
            )
            breakdown = confidence.score(
                retrieval_score=r.score,
                legal_match=legal_match,
                grounding=grounding,
                scope_alignment=scope_alignment,
                scope_flag=scope_flag,
            )
            status = confidence.route(breakdown.final)

            mappings.append(EvidenceMapping(
                mapping_id=_mapping_id(run_id, ind.indicator_id, prov.provision_id),
                run_id=run_id,
                economy=prov.economy,
                pillar=ind.pillar,
                indicator_id=ind.indicator_id,
                law_name=prov.law_name,
                article_section=prov.article_section,
                verbatim_snippet=prov.verbatim_snippet,
                source_url=prov.source_url,
                mapping_rationale=rationale,
                confidence_score=breakdown.final,
                discovery_tag=doc_tags.get(prov.doc_id, DiscoveryTag.KNOWN),
                review_status=status,
                provision_id=prov.provision_id,
                raw_context=r.raw_context,
                confidence=breakdown,
                ocr=prov.ocr,
                model_version=llm.model_version,
                retrieval_log=r.log,
                scope_flag=scope_flag,
            ))
    # most confident first
    mappings.sort(key=lambda m: m.confidence_score, reverse=True)
    return mappings
