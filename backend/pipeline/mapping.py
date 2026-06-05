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
    "You are a meticulous legal-evidence grader for the UNESCAP RDTII 2.1 framework "
    "(Pillar 6 = cross-border data flows; Pillar 7 = domestic data protection). You decide "
    "whether ONE statutory provision satisfies ONE specific TARGET indicator. The pillar's "
    "indicators are deliberately close, so TWO opposite errors are equally serious:\n"
    "  • OVER-ASSIGN: mapping a provision that only MENTIONS the topic but whose operative "
    "rule does not actually satisfy the indicator's legal test.\n"
    "  • MISS: rejecting a provision whose operative rule DOES satisfy the target, merely "
    "because the provision also touches a neighbouring indicator.\n\n"
    "Work in this exact order:\n"
    "(1) OPERATIVE RULE — in one sentence, state what the snippet actually DOES (the binding "
    "rule it enacts), ignoring incidental or definitional wording. A provision may enact more "
    "than one rule (e.g. a default restriction AND an exception); note each.\n"
    "(2) TARGET TEST — check the operative rule(s) against the TARGET indicator's legal_test, "
    "OBEYING its 'Distinguish from …' notes. Set satisfies_target=true ONLY if a rule genuinely "
    "meets the test (operative effect, not topical overlap or a bare definition).\n"
    "(3) BETTER SIBLING — set better_sibling to a sibling id ONLY when the snippet contains NO "
    "rule that satisfies the target AND a sibling clearly fits instead (i.e. the target is a "
    "MISLABEL). If the snippet does satisfy the target — even partially, alongside other "
    "content — leave better_sibling null. A provision may legitimately map to several indicators.\n"
    "(4) relevant = satisfies_target AND (better_sibling is null).\n"
    "(5) legal_match (0..1), calibrated: 1.0 = the operative rule IS exactly this indicator's "
    "test; 0.7 = clearly satisfies with minor wording gaps; 0.5 = satisfies one element of a "
    "multi-part test; <=0.3 = topical mention only (then satisfies_target=false).\n"
    "(6) SCOPE — if the instrument is sector-specific (a financial / telecom / health notice or "
    "code) while the indicator is national, set scope_flag='SECTORAL_NOT_NATIONAL' and lower "
    "scope_alignment. RDTII excludes data-localisation/retention measures that apply ONLY to "
    "GOVERNMENT data — treat those as NOT satisfying.\n"
    "(7) Judge ONLY the snippet; never assert a conclusion it does not support.\n"
    "(8) rationale <=300 chars, EXACT format: 'This [section] [prohibits/requires/permits/"
    "establishes] [what]. Maps to [indicator] because [one-sentence legal logic].'\n\n"
    "Output ONLY this JSON object: {operative_rule:str, satisfies_target:bool, "
    "better_sibling:str|null, relevant:bool, legal_match:0..1, scope_alignment:0..1, "
    "scope_flag:str|null, rationale:str}."
)


def _siblings_block(ind) -> str:
    # Format kept mock-parseable (id :: title — desc :: terms :: legal_test): the offline
    # grader reads field [2] (terms); a real LLM also gets each sibling's legal_test [3] to
    # distinguish it from the target.
    lines = []
    for s in siblings(ind.indicator_id):
        terms = " | ".join(s.query_terms[:4])
        lines.append(f"{s.indicator_id} :: {s.title} — {s.description} :: {terms} :: {s.legal_test}")
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
        "Follow steps (1)-(8). Decide independently whether THIS provision satisfies the "
        "TARGET; only reject for a better sibling if the target is a genuine mislabel. "
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
    log=lambda *_: None,
) -> list[EvidenceMapping]:
    llm = llm or get_llm_provider()
    source_texts = source_texts or {}
    doc_tags = doc_tags or {}
    mappings: list[EvidenceMapping] = []
    failures = 0

    for ind in indicators:
        for r in retrieve(ind.indicator_id, provisions, top_k=top_k):
            if r.score < min_retrieval:
                continue
            prov = r.provision
            # Resilience: a single LLM failure (e.g. all free models rate-limited)
            # must NOT crash the whole run — log and skip this pairing.
            try:
                graded = llm.complete_json(SYSTEM, _user_prompt(ind, prov))
            except Exception as e:  # noqa: BLE001
                failures += 1
                if failures <= 3:
                    log(f"[warn] LLM call failed ({type(e).__name__}); skipping {ind.indicator_id}/{prov.provision_id}")
                continue

            # relevant = satisfies the target AND not a mislabel for a better sibling.
            # Prefer the model's explicit `relevant`; otherwise derive it from the
            # decoupled signals (real LLMs return satisfies_target/better_sibling; the
            # offline mock returns `relevant` directly).
            relevant = graded.get("relevant")
            if relevant is None:
                relevant = bool(graded.get("satisfies_target")) and not graded.get("better_sibling")
            if not relevant:
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
    if failures:
        log(f"[warn] {failures} LLM call(s) failed and were skipped "
            f"(free-tier rate limits? try a paid key or fewer pillars)")
    # most confident first
    mappings.sort(key=lambda m: m.confidence_score, reverse=True)
    return mappings
