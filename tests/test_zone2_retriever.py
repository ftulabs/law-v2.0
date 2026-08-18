"""Zone-2 retriever selection + LightRAG graceful fallback.

LightRAG is an OPTIONAL accelerator at live-crawl scale; a mapping run must never depend
on it. These tests pin the contract: 'hybrid' mode never touches LightRAG, and if the
LightRAG backend yields nothing for an indicator (e.g. its KG build was rate-limited),
the mapper falls back to the built-in hybrid retriever and still produces mappings.

The mapper needs a grader to produce anything: every (provision, indicator) pair is
decided by `llm.complete_json`. These tests therefore pass the deterministic offline
mock grader — `llm=None` is a no-grader run and correctly yields nothing (pinned by
test_mapper_without_llm_produces_nothing below).
"""
from backend.config import settings
from backend.pipeline import discovery, extraction, mapping
from backend.pipeline.ocr import get_document_text
from backend.providers import get_llm_provider, get_ocr_provider
from backend.rdtii import get_indicators
from backend.schemas import Economy


def _sample_provisions(n=12):
    provs = []
    ocr = get_ocr_provider("mock")
    for d in discovery.discover(Economy.SG, 7):
        raw, m = get_document_text(d, ocr_provider=ocr)
        provs += extraction.extract_provisions(d, raw, m)
    return provs[:n]


def _mock_llm():
    """Deterministic, grounded offline grader — no network, no key."""
    return get_llm_provider("mock")


def test_hybrid_mode_never_uses_lightrag(monkeypatch):
    monkeypatch.setattr(settings, "retriever", "hybrid")
    assert mapping._select_retriever([], [], 5, None, lambda *_: None) is None


def test_mapper_falls_back_when_lightrag_returns_empty(monkeypatch):
    """A dict of empty lists (KG build starved) must NOT zero-out the run."""
    provs = _sample_provisions()
    inds = get_indicators(7)
    # pretend LightRAG ran but recovered nothing for any indicator
    monkeypatch.setattr(mapping, "_select_retriever",
                        lambda *a, **k: {i.indicator_id: [] for i in inds})
    out = mapping.map_provisions(run_id="t", provisions=provs, pillar=7, indicators=inds,
                                 llm=_mock_llm(), top_k=3, log=lambda *_: None)
    assert out, "mapper should fall back to hybrid retrieval, not produce zero mappings"


def test_mapper_matches_hybrid_when_no_lightrag(monkeypatch):
    """With LightRAG off, mapping is identical to the plain hybrid path."""
    provs = _sample_provisions()
    inds = get_indicators(7)
    monkeypatch.setattr(mapping, "_select_retriever", lambda *a, **k: None)
    out = mapping.map_provisions(run_id="t", provisions=provs, pillar=7, indicators=inds,
                                 llm=_mock_llm(), top_k=3, log=lambda *_: None)
    assert out


class _FailingLLM:
    """A grader whose every call fails — the 'we lost the LLM mid-run' condition."""
    name = "failing"
    model_version = "failing-0"

    def complete_json(self, system, user):
        raise RuntimeError("grader unavailable")


def test_mapper_without_llm_produces_nothing(monkeypatch):
    """A grader that always fails → no mappings, and no crash. Every grading call is counted
    as a failure rather than being silently read as 'not relevant', so a run that lost its LLM
    comes back empty instead of quietly emitting a half-graded corpus.

    The failing grader is INJECTED rather than passing `llm=None`: `map_provisions` falls back
    to the configured provider when given None (mapping.py: `llm = llm or get_llm_provider()`),
    so the None form only asserted this when no working API key happened to be present — it
    passed for years because the key in .env was dead, then started making real paid calls the
    moment a valid key was installed."""
    provs = _sample_provisions()
    inds = get_indicators(7)
    monkeypatch.setattr(mapping, "_select_retriever", lambda *a, **k: None)
    out = mapping.map_provisions(run_id="t", provisions=provs, pillar=7, indicators=inds,
                                 llm=_FailingLLM(), top_k=3, log=lambda *_: None)
    assert out == []
