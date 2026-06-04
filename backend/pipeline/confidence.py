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
SCOPE_FLAG_CAP = 0.55   # a scope-mismatched mapping can never auto-accept


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
    explanation: str = "",
) -> ConfidenceBreakdown:
    final = (
        WEIGHTS["retrieval_score"] * retrieval_score
        + WEIGHTS["legal_match"] * legal_match
        + WEIGHTS["snippet_grounding"] * grounding
        + WEIGHTS["scope_alignment"] * scope_alignment
    )
    if scope_flag:
        final = min(final, SCOPE_FLAG_CAP)
    final = round(max(0.0, min(1.0, final)), 3)
    note = explanation or (
        f"0.25·ret({retrieval_score}) + 0.40·legal({legal_match}) + "
        f"0.20·ground({grounding}) + 0.15·scope({scope_alignment})"
        + (f"  [capped at {SCOPE_FLAG_CAP} — {scope_flag}]" if scope_flag else "")
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
