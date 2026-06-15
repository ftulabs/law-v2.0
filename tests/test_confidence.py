"""Confidence-scoring guards: indicator-aware sectoral cap + pillar topical-grounding gate.

Regression for run-10292544 (AU P6): the correct My Health Records s77 -> P6-I1 mapping was
quarantined by an over-broad sectoral cap, while a boilerplate Privacy Act s100 ("Governor-General
may make regulations") was recorded under P6-I4 because nothing checked the snippet was topically
about cross-border data.
"""
from backend.pipeline import confidence as C
from backend.schemas import ReviewStatus


# ─────────────────── sectoral cap is indicator-aware ───────────────────
def test_sectoral_cap_not_applied_to_p6_localisation():
    """A sectoral data-localisation law (health-sector) is a valid P6-I1 answer — the
    SECTORAL_NOT_NATIONAL cap must NOT fire for it, so it can clear the quarantine floor."""
    assert "P6-I1" not in C.SCOPE_SENSITIVE_INDICATORS
    apply_cap = "P6-I1" in C.SCOPE_SENSITIVE_INDICATORS
    b = C.score(retrieval_score=0.444, legal_match=0.95, grounding=1.0, scope_alignment=0.5,
                scope_flag="SECTORAL_NOT_NATIONAL", apply_scope_cap=apply_cap, topical_ok=True)
    assert b.final > C.SCOPE_FLAG_CAP                      # not capped
    assert C.route(b.final) != ReviewStatus.QUARANTINED   # surfaces (was wrongly quarantined)


def test_sectoral_cap_still_applies_to_comprehensive_framework():
    """For P7-I1 (comprehensive framework), a sectoral instrument genuinely does not satisfy —
    the cap must still fire there."""
    assert "P7-I1" in C.SCOPE_SENSITIVE_INDICATORS
    apply_cap = "P7-I1" in C.SCOPE_SENSITIVE_INDICATORS
    b = C.score(retrieval_score=0.6, legal_match=0.95, grounding=1.0, scope_alignment=0.5,
                scope_flag="SECTORAL_NOT_NATIONAL", apply_scope_cap=apply_cap, topical_ok=True)
    assert b.final <= C.SCOPE_FLAG_CAP


# ─────────────────── topical-grounding gate ───────────────────
def test_topical_gate_flags_offtopic_boilerplate():
    """A 'may make regulations' boilerplate snippet has no P6 concept vocabulary -> the gate
    fails -> the mapping is capped into quarantine even when the (weak) model claimed a match."""
    boilerplate = ("Regulations. The Governor-General may make regulations, not inconsistent with "
                   "this Act, prescribing matters required or permitted to be prescribed.")
    assert C.topical_grounded(boilerplate, 6) is False
    b = C.score(retrieval_score=0.411, legal_match=0.9, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=False)
    assert b.final <= C.TOPICAL_FAIL_CAP
    assert C.route(b.final) == ReviewStatus.QUARANTINED


def test_topical_gate_keeps_real_localisation_snippet():
    """A genuine localisation snippet ('must not ... outside Australia') passes the gate even
    though it uses 'outside' rather than the word 'transfer'."""
    snip = ("must not hold the records, or take the records, outside Australia; or process or "
            "handle the information relating to the records outside Australia")
    assert C.topical_grounded(snip, 6) is True
    snip_app8 = "Australian Privacy Principle 8 — cross-border disclosure of personal information"
    assert C.topical_grounded(snip_app8, 6) is True


def test_topical_gate_exempts_non_latin_script():
    """Concept terms are English; a non-Latin snippet must not be wrongly failed (Round-1-safe)."""
    assert C.topical_grounded("个人信息不得出境，应当在中华人民共和国境内存储。", 6) is True
