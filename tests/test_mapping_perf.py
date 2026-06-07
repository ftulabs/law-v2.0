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
    """1200 provisions must grade at most retrieve_max_top_k per indicator — not a big
    fraction of the corpus (the bug that made AU P6 ~1400 LLM calls / 30 min)."""
    inds = get_indicators(6)
    llm = _CountingLLM()
    mapping.map_provisions(run_id="t", provisions=_provs(1200), pillar=6, indicators=inds,
                           llm=llm, top_k=5, log=lambda *_: None)
    assert llm.calls <= settings.retrieve_max_top_k * len(inds)
    assert llm.calls <= 40 * len(inds)        # concrete ceiling with the shipped cap


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
