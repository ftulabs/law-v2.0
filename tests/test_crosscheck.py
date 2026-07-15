"""Cross-model second opinion on borderline rejections (the run-to-run flip-flop fix).

Design under test: when the PRIMARY grader rejects a provision while itself signalling legal
closeness (better_sibling set, or legal_match >= 0.3), a DIFFERENT model independently
re-grades the same prompt; a 1-1 split goes to a third model and the majority (2-1) decides.
Every call is context-free — no model ever sees another's answer — so this is voting over
independent judgments, not persuading one model (the user's bias concern). Conservative on
any doubt: clear misses are never re-asked, and a failover landing the "independent" vote on
the primary model voids that vote.
"""
import backend.pipeline.mapping as mapping
from backend.pipeline.retrieval import Retrieved
from backend.rdtii import get_indicators
from backend.schemas import Economy, OCRMetrics, Provision


def _prov():
    return Provision(provision_id="p1", doc_id="d", economy=Economy.AU,
                     law_name="Target Act 2012", article_section="Section 77",
                     verbatim_snippet="The operator must not hold or take the records, or "
                     "process information in the records, outside Australia.",
                     source_url="u", ocr=OCRMetrics())


class _LLM:
    name = "openrouter"

    def __init__(self, model, resp):
        self.model_version = model
        self._resp = resp
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return dict(self._resp)


REJECT_BORDERLINE = {"satisfies_target": False, "better_sibling": "P6-I1", "relevant": False,
                     "legal_match": 0.3, "scope_alignment": 1.0, "rationale": "reads as a ban"}
REJECT_CLEAR = {"satisfies_target": False, "better_sibling": None, "relevant": False,
                "legal_match": 0.0, "scope_alignment": 0.0, "rationale": "off topic"}
ACCEPT = {"satisfies_target": True, "better_sibling": None, "relevant": True,
          "legal_match": 0.9, "scope_alignment": 1.0, "rationale": "in-country storage duty"}


def _run(monkeypatch, primary, second, tiebreak, budget=10, logs=None):
    inds = [i for i in get_indicators(6) if i.indicator_id == "P6-I2"]
    monkeypatch.setattr(mapping, "retrieve", lambda ind_id, provs, top_k=5:
                        [Retrieved(provision=p, score=0.9, raw_context=p.verbatim_snippet,
                                   log=[]) for p in provs])
    monkeypatch.setattr(mapping, "_build_crosscheck", lambda llm, log:
                        (second, tiebreak, primary.model_version, mapping._CallBudget(budget)))
    return mapping.map_provisions(run_id="t", provisions=[_prov()], pillar=6, indicators=inds,
                                  llm=primary, top_k=5,
                                  log=(logs.append if logs is not None else (lambda *_: None)))


def test_borderline_rejection_overturned_by_two_independent_models(monkeypatch):
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_BORDERLINE)
    second = _LLM("google/gemini-2.5-flash", ACCEPT)
    tiebreak = _LLM("openai/gpt-4o-mini", ACCEPT)
    ms = _run(monkeypatch, primary, second, tiebreak)
    assert len(ms) == 1 and ms[0].indicator_id == "P6-I2"
    assert second.calls == 1 and tiebreak.calls == 1
    assert "cross-model majority" in (ms[0].notes or "")   # audit trail names the mechanism


def test_second_model_agreeing_reject_ends_it_two_zero(monkeypatch):
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_BORDERLINE)
    second = _LLM("google/gemini-2.5-flash", REJECT_CLEAR)
    tiebreak = _LLM("openai/gpt-4o-mini", ACCEPT)
    assert _run(monkeypatch, primary, second, tiebreak) == []
    assert tiebreak.calls == 0                     # 2-0 needs no third opinion


def test_tiebreak_rejecting_upholds_the_rejection_two_one(monkeypatch):
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_BORDERLINE)
    second = _LLM("google/gemini-2.5-flash", ACCEPT)
    tiebreak = _LLM("openai/gpt-4o-mini", REJECT_CLEAR)
    assert _run(monkeypatch, primary, second, tiebreak) == []


def test_clear_miss_is_never_re_asked(monkeypatch):
    """No sibling, ~0 legal_match → an obvious miss; spending opinion calls there would just
    re-litigate every rejection (cost) and invite over-assignment (accuracy)."""
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_CLEAR)
    second = _LLM("google/gemini-2.5-flash", ACCEPT)
    assert _run(monkeypatch, primary, second, None) == []
    assert second.calls == 0


def test_failover_onto_primary_model_voids_the_vote(monkeypatch):
    """OpenRouter failover can silently answer a 'gemini' call with the primary model — that
    vote is NOT independent and must not count (else the panel is one model voting twice)."""
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_BORDERLINE)
    second = _LLM("deepseek/deepseek-v4-flash", ACCEPT)   # same model answered
    tiebreak = _LLM("openai/gpt-4o-mini", ACCEPT)
    assert _run(monkeypatch, primary, second, tiebreak) == []
    assert tiebreak.calls == 0


def test_exhausted_budget_keeps_rejections_without_calls(monkeypatch):
    primary = _LLM("deepseek/deepseek-v4-flash", REJECT_BORDERLINE)
    second = _LLM("google/gemini-2.5-flash", ACCEPT)
    assert _run(monkeypatch, primary, second, None, budget=0) == []
    assert second.calls == 0
