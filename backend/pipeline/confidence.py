"""Confidence scoring + human-in-the-loop routing.

Final confidence is a transparent weighted blend of four auditable signals, every
one of which is stored on the mapping so a reviewer can see *why* a score landed
where it did:

  retrieval_score   how strongly the provision was retrieved for the indicator
  legal_match       model judgement the provision satisfies the indicator's legal test
  snippet_grounding is the cited snippet actually present in the source text (anti-hallucination)
  scope_alignment   national vs sectoral fit (penalised on scope mismatch)

Routing (configurable in .env):
  final >= 0.85           → auto_accepted
  0.60 <= final < 0.85    → pending_review
  final < 0.60            → quarantined
A hard scope flag (SECTORAL_NOT_NATIONAL) caps the score so it can never auto-accept.
"""
from __future__ import annotations

from ..config import settings
from ..schemas import ConfidenceBreakdown, ReviewStatus

WEIGHTS = {
    "retrieval_score": 0.25,
    "legal_match": 0.40,
    "snippet_grounding": 0.20,
    "scope_alignment": 0.15,
}
SCOPE_FLAG_CAP = 0.55         # a scope-mismatched mapping can never auto-accept
TOPICAL_FAIL_CAP = 0.45       # snippet shares NO concept vocabulary with the pillar → likely
                              # a fabricated reading (e.g. a weak model mapping a "may make
                              # regulations" boilerplate clause to a cross-border indicator)

# Indicators whose legal test REQUIRES general / comprehensive scope, so a SECTORAL instrument
# genuinely does not satisfy them — only here should SECTORAL_NOT_NATIONAL cap the score. For
# every other indicator (esp. the P6 localisation mandates P6-I1..I4, and P7 retention/access),
# a sectoral law is a legitimate, scored answer — e.g. the health-sector My Health Records Act
# s77 ("must not hold records outside Australia") IS the RDTII answer for P6-I1. Capping it
# there wrongly quarantines a correct mapping, so the cap must NOT fire for these indicators.
SCOPE_SENSITIVE_INDICATORS = {"P7-I1"}

# Concept vocabulary per pillar. A provision the model maps to a pillar should contain at least
# one of these (substring match). It is NOT keyed to a specific law — only to the pillar's legal
# subject — so it catches hallucinated mappings of off-topic boilerplate without hardcoding any
# law name or suppressing a genuinely on-topic provision phrased in its own words.
_PILLAR_CONCEPT_TERMS = {
    6: ("outside", "overseas", "abroad", "foreign", "cross-border", "cross border", "border",
        "transfer", "transmit", "export", "another country", "other country", "third country",
        "within the country", "in-country", "locally", "local processing", "domestic", "territory",
        "jurisdiction", "server", "data centre", "data center", "datacentre", "infrastructure",
        "stored", "store", "storage", "located", "reside", "hosted", "premises", "process"),
    7: ("personal data", "personal information", "data protection", "privacy", "process", "collect",
        "disclos", "consent", "security", "secur", "cyber", "encrypt", "breach", "retain",
        "retention", "store", "storage", "period", "officer", "impact assessment", "assessment",
        "access", "law enforcement", "enforcement", "surveillance", "intercept", "warrant",
        "data", "information"),
}


def topical_grounded(snippet: str, pillar: int | None) -> bool:
    """True when the snippet contains at least one of the pillar's concept terms (or we have no
    concept set / no usable snippet to judge). Non-Latin-script snippets are exempt (the concept
    terms are English) so non-English provisions are never wrongly failed — a known Round-1-safe
    limitation; localise _PILLAR_CONCEPT_TERMS for non-English finals."""
    terms = _PILLAR_CONCEPT_TERMS.get(pillar)
    if not terms or not snippet:
        return True
    low = snippet.lower()
    if sum(c.isascii() for c in low) / max(len(low), 1) < 0.85:  # mostly non-Latin → don't judge
        return True
    return any(t in low for t in terms)


def snippet_grounding(snippet: str, source_text: str) -> float:
    """Fraction of the snippet verifiably present in the source — guards against
    fabricated quotes. 1.0 = exact substring; partial credit for token overlap."""
    if not snippet or not source_text:
        return 0.0
    if snippet.strip()[:200] in source_text:
        return 1.0
    s_tokens = set(snippet.lower().split())
    src_tokens = set(source_text.lower().split())
    if not s_tokens:
        return 0.0
    return round(len(s_tokens & src_tokens) / len(s_tokens), 3)


def score(
    retrieval_score: float,
    legal_match: float,
    grounding: float,
    scope_alignment: float,
    scope_flag: str | None,
    apply_scope_cap: bool = True,
    topical_ok: bool = True,
    explanation: str = "",
) -> ConfidenceBreakdown:
    final = (
        WEIGHTS["retrieval_score"] * retrieval_score
        + WEIGHTS["legal_match"] * legal_match
        + WEIGHTS["snippet_grounding"] * grounding
        + WEIGHTS["scope_alignment"] * scope_alignment
    )
    caps = []
    # Sectoral cap ONLY where the legal test requires general scope (see SCOPE_SENSITIVE_INDICATORS).
    if scope_flag and apply_scope_cap:
        final = min(final, SCOPE_FLAG_CAP)
        caps.append(f"capped at {SCOPE_FLAG_CAP} — {scope_flag}")
    # Topical guard: no concept vocabulary in the snippet → treat as a likely fabricated mapping.
    if not topical_ok:
        final = min(final, TOPICAL_FAIL_CAP)
        caps.append(f"capped at {TOPICAL_FAIL_CAP} — snippet has no pillar concept terms (likely off-topic)")
    final = round(max(0.0, min(1.0, final)), 3)
    note = explanation or (
        f"0.25·ret({retrieval_score}) + 0.40·legal({legal_match}) + "
        f"0.20·ground({grounding}) + 0.15·scope({scope_alignment})"
        + ("  [" + "; ".join(caps) + "]" if caps else "")
    )
    return ConfidenceBreakdown(
        retrieval_score=round(retrieval_score, 3),
        legal_match=round(legal_match, 3),
        snippet_grounding=round(grounding, 3),
        scope_alignment=round(scope_alignment, 3),
        final=final,
        explanation=note,
    )


def route(final: float) -> ReviewStatus:
    if final >= settings.conf_auto_accept:
        return ReviewStatus.AUTO_ACCEPTED
    if final >= settings.conf_review_floor:
        return ReviewStatus.PENDING_REVIEW
    return ReviewStatus.QUARANTINED
