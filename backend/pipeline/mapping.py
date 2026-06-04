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
from ..rdtii import get_indicator, siblings
from ..schemas import DiscoveryTag, EvidenceMapping, Provision
from . import confidence
from .retrieval import retrieve

SYSTEM = (
    "You are a legal evidence grader for the UNESCAP RDTII 2.1 framework. You decide "
    "whether ONE statutory provision satisfies a SPECIFIC target indicator's legal "
    "test — and, crucially, whether a SIBLING indicator in the same pillar fits "
    "BETTER. These indicators are deliberately close (e.g. a default cross-border "
    "RESTRICTION vs the consent/adequacy/contract EXCEPTIONS; a basis-to-process duty "
    "vs a purpose-limitation duty vs individual rights), so misclassification is the "
    "main risk.\n\n"
    "Rules:\n"
    "(1) Judge ONLY the provided snippet — never rely on outside knowledge of the law.\n"
    "(2) Identify the provision's OPERATIVE legal rule (what it actually does), then "
    "match that rule to the indicator whose legal_test it best satisfies.\n"
    "(3) Compare the TARGET indicator against every sibling listed. Set "
    "best_fit_indicator to the single indicator id that fits best. If that is NOT the "
    "target, set relevant=false (the provision will be mapped under the better sibling "
    "on its own pass).\n"
    "(4) 'legal_match' (0..1) = how strongly the OPERATIVE rule satisfies the TARGET "
    "indicator's legal_test, not mere topical overlap.\n"
    "(5) If the instrument is sector-specific (e.g. a financial-sector notice) while "
    "the indicator is national in scope, set scope_flag='SECTORAL_NOT_NATIONAL' and "
    "lower scope_alignment.\n"
    "(6) Never assert a legal conclusion the snippet does not support.\n"
    "(7) Write 'rationale' in EXACTLY this format, max 300 chars: 'This "
    "[article/section] [prohibits/requires/permits/establishes] [what]. Maps to "
    "[indicator] because [one-sentence legal logic].' Name the legal mechanism; do not "
    "paraphrase the snippet.\n\n"
    "Respond with ONLY a JSON object: {relevant:bool, best_fit_indicator:str, "
    "legal_match:0..1, scope_alignment:0..1, scope_flag:str|null, rationale:str}."
)


def _siblings_block(ind) -> str:
    lines = []
    for s in siblings(ind.indicator_id):
        terms = " | ".join(s.query_terms[:4])
        lines.append(f"{s.indicator_id} :: {s.title} — {s.description} :: {terms}")
    return "\n".join(lines)


def _user_prompt(ind, prov: Provision) -> str:
    return (
        f"<TARGET_INDICATOR>{ind.indicator_id} — {ind.title}</TARGET_INDICATOR>\n"
        f"<INDICATOR_QUESTION>{ind.description}</INDICATOR_QUESTION>\n"
        f"<INDICATOR_SCOPE>{ind.scope}</INDICATOR_SCOPE>\n"
        f"<LEGAL_TEST>{ind.legal_test}</LEGAL_TEST>\n"
        f"<QUERY_TERMS>{' | '.join(ind.query_terms)}</QUERY_TERMS>\n"
        f"<SIBLINGS>\n{_siblings_block(ind)}\n</SIBLINGS>\n"
        f"<LAW>{prov.law_name} — {prov.article_section}</LAW>\n"
        f"<SNIPPET>{prov.verbatim_snippet}</SNIPPET>\n"
        "Pick the best-fitting indicator, then grade the provision against the TARGET. "
        "Return the JSON object only."
    )


def _build_notes(prov: Provision, scope_flag: str | None) -> str | None:
    """Template 'Notes' — flag unusual cases: scope, OCR quality, etc."""
    parts = []
    if scope_flag:
        parts.append(f"{scope_flag}: sectoral instrument — verify before treating as national.")
    if prov.ocr.used:
        mc = prov.ocr.mean_confidence
        if prov.ocr.provider == "markitdown":
            parts.append("Text extracted from PDF via MarkItDown; verify wording vs source.")
        else:
            parts.append(f"OCR-extracted via {prov.ocr.provider}"
                         + (f" (mean conf {mc:.2f})" if mc is not None else "") + "; verify wording vs source.")
    return " ".join(parts) or None


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

            # disambiguation: drop the pairing if the model judged a sibling a better
            # fit (it will be mapped under that sibling on its own pass)
            if not graded.get("relevant", True):
                continue

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
                law_number=prov.law_number,
                last_amended=(prov.amendment_date or "")[:4] or None,
                article_section=prov.article_section,
                location_ref=prov.location_ref,
                verbatim_snippet=prov.verbatim_snippet,
                source_url=prov.source_url,
                mapping_rationale=(rationale or "")[:300],
                confidence_score=breakdown.final,
                discovery_tag=doc_tags.get(prov.doc_id, DiscoveryTag.KNOWN),
                notes=_build_notes(prov, scope_flag),
                review_status=status,
                provision_id=prov.provision_id,
                source_pdf_path=prov.source_pdf_path,
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
