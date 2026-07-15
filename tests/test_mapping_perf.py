"""Mapping throughput safeguards: a large corpus must NOT explode into thousands of LLM
calls, and concurrent grading must produce the same mappings as sequential.
"""
import math

from backend.config import settings
from backend.pipeline import mapping
from backend.rdtii import get_indicators
from backend.schemas import Economy, OCRMetrics, Provision


class _CountingLLM:
    name = "count"
    model_version = "count-1"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return {"relevant": True, "legal_match": 0.8, "scope_alignment": 1.0, "rationale": "x"}


def _provs(n):
    return [Provision(provision_id=f"p{i}", doc_id="d", economy=Economy.AU,
                      law_name="Privacy Act 1988", article_section=f"Section {i}",
                      verbatim_snippet="transfer personal data overseas subject to consent " * 4,
                      source_url="u", ocr=OCRMetrics()) for i in range(n)]


def test_large_corpus_shortlist_is_bounded():
    """1200 provisions must grade at most retrieve_max_top_k PER INDICATOR — a hard cap, not
    a fraction of the corpus (old bug: 0.30*1200 ≈ 360/indicator → ~1400 calls / 30 min) and
    not the per-law/dense extras stacked on top (the ~60/indicator regression)."""
    inds = get_indicators(6)
    llm = _CountingLLM()
    mapping.map_provisions(run_id="t", provisions=_provs(1200), pillar=6, indicators=inds,
                           llm=llm, top_k=5, log=lambda *_: None)
    assert llm.calls <= settings.retrieve_max_top_k * len(inds)


def test_short_law_provision_not_crowded_out():
    """A short, on-point law must contribute candidates even when a verbose law dominates —
    the AU crowding-out bug (My Health Records s77 missed because Privacy Act filled top-k)."""
    big = [Provision(provision_id=f"b{i}", doc_id="big", economy=Economy.AU,
                     law_name="Privacy Act 1988", article_section=f"Section {i}",
                     verbatim_snippet="cross-border disclosure of personal information overseas "
                     "recipient adequacy consent " * 6, source_url="u", ocr=OCRMetrics())
           for i in range(400)]
    small = [Provision(provision_id="s1", doc_id="small", economy=Economy.AU,
                       law_name="My Health Records Act 2012", article_section="Section 77",
                       verbatim_snippet="Requirement not to hold or take records outside Australia. "
                       "The operator must not hold the records, or process them, outside Australia.",
                       source_url="u", ocr=OCRMetrics())]
    sl = mapping._diverse_shortlist("P6-I1", big + small, settings.retrieve_max_top_k,
                                    settings.retrieve_per_law_k, log=lambda *_: None)
    ids = {r.provision.provision_id for r in sl}
    assert "s1" in ids        # the small law's on-point provision is graded, not crowded out


def test_per_law_reserved_slot_survives_on_score_not_discovery_order(monkeypatch):
    """Regression for a live AU P6 bug: with enough discovered laws that per-law reservations
    (num_laws x per_law_k) exceed global_k, the round-robin ran out of budget PARTWAY through
    a rank pass. The old code spent that remaining budget in dict/declaration order (i.e.
    discovery order) — so a law's #2 pick lost its reserved slot to an earlier-enumerated
    law's #2 pick EVEN WHEN IT SCORED HIGHER, purely because of where it fell in the input
    list. Confirmed live: My Health Records s77 ranked #2 within its own law for P6-I1
    (score 0.455, clearly on-topic — beaten internally only by an unrelated s55) yet never
    reached the LLM. retrieve() is stubbed with FIXED scores here (real embeddings are too
    unpredictable to reliably reproduce "a weak decoy coincidentally outscores the real
    provision" in a fixture) so the shortlist algorithm's fairness is tested in isolation."""
    from backend.pipeline.retrieval import Retrieved

    provisions = []
    for i in range(20):
        provisions.append(Provision(
            provision_id=f"noise{i}-1", doc_id=f"noise{i}", economy=Economy.AU,
            law_name=f"Noise Act {i}", article_section="Section 1",
            verbatim_snippet="x", source_url="u", ocr=OCRMetrics()))
        provisions.append(Provision(
            provision_id=f"noise{i}-2", doc_id=f"noise{i}", economy=Economy.AU,
            law_name=f"Noise Act {i}", article_section="Section 2",
            verbatim_snippet="x", source_url="u", ocr=OCRMetrics()))
    # Enumerated LAST (21st law). Its rank-1 pick (target-2) outscores every OTHER law's
    # rank-1 pick (0.8 vs 0.5) — it must win one of the few rank-1 slots on merit.
    provisions += [
        Provision(provision_id="target-1", doc_id="target", economy=Economy.AU,
                 law_name="Target Act 2012", article_section="Section 1",
                 verbatim_snippet="x", source_url="u", ocr=OCRMetrics()),
        Provision(provision_id="target-2", doc_id="target", economy=Economy.AU,
                 law_name="Target Act 2012", article_section="Section 77",
                 verbatim_snippet="x", source_url="u", ocr=OCRMetrics()),
    ]
    scores = {f"noise{i}-1": 0.9 for i in range(20)}
    scores.update({f"noise{i}-2": 0.5 for i in range(20)})
    scores["target-1"] = 0.9
    scores["target-2"] = 0.8   # beats every noise law's rank-1 pick (0.5)

    def fake_retrieve(indicator_id, provs, top_k=5):
        ranked = sorted(provs, key=lambda p: scores.get(p.provision_id, 0.0), reverse=True)
        return [Retrieved(provision=p, score=scores.get(p.provision_id, 0.0),
                          raw_context=p.verbatim_snippet, log=[]) for p in ranked[:top_k]]

    monkeypatch.setattr(mapping, "retrieve", fake_retrieve)
    # 21 laws x per_law_k=2 = 42 reserved slots > global_k=25 — rank-0 alone (21 picks) leaves
    # only 4 slots for rank-1, where target-2 must out-compete 20 noise laws' rank-1 picks.
    sl = mapping._diverse_shortlist("P6-I1", provisions, global_k=25, per_law_k=2, log=lambda *_: None)
    ids = {r.provision.provision_id for r in sl}
    assert "target-2" in ids, "the real answer must survive the cutoff on score, not discovery order"


def test_empty_llm_response_counts_as_failure_not_silent_rejection():
    """Regression for the OTHER half of the AU missing-mappings bug: a reasoning model whose
    thinking overran the completion-token budget returned truncated/EMPTY JSON, and _grade
    misread the empty dict as 'satisfies_target=false' — the mapping vanished with zero
    warnings (live: Insurance Act 49Q → P6-I2 lost on ~2/3 of runs, varying run to run with
    the model's thinking length). An empty or _parse_error response must be COUNTED and
    SURFACED as a failed call, never silently treated as a considered rejection."""
    logs = []

    class _EmptyLLM:
        name = "empty"
        model_version = "empty-1"

        def complete_json(self, system, user):
            return {}                       # what a truncated reasoning response parses to

    inds = get_indicators(6)[:1]
    out = mapping.map_provisions(run_id="t", provisions=_provs(3), pillar=6, indicators=inds,
                                 llm=_EmptyLLM(), top_k=5, log=logs.append)
    assert out == []                        # nothing mappable — but NOT silently
    joined = " ".join(logs)
    assert "failed" in joined, "failed calls must be surfaced in the log, not swallowed"
    assert "truncat" in joined or "unparseable" in joined  # names the real cause


def test_concurrent_matches_sequential():
    inds = get_indicators(6)
    provs = _provs(120)
    orig = settings.mapping_concurrency
    try:
        settings.mapping_concurrency = 1
        seq = mapping.map_provisions(run_id="t", provisions=provs, pillar=6, indicators=inds,
                                     llm=_CountingLLM(), top_k=5, log=lambda *_: None)
        settings.mapping_concurrency = 8
        par = mapping.map_provisions(run_id="t", provisions=provs, pillar=6, indicators=inds,
                                     llm=_CountingLLM(), top_k=5, log=lambda *_: None)
    finally:
        settings.mapping_concurrency = orig
    # same set of (indicator, provision) mappings regardless of concurrency
    assert {(m.indicator_id, m.provision_id) for m in seq} == {(m.indicator_id, m.provision_id) for m in par}
