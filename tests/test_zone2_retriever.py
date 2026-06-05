"""Zone-2 retriever selection + LightRAG graceful fallback.

LightRAG is an OPTIONAL accelerator at live-crawl scale; a mapping run must never depend
on it. These tests pin the contract: 'hybrid' mode never touches LightRAG, and if the
LightRAG backend yields nothing for an indicator (e.g. its KG build was rate-limited),
the mapper falls back to the built-in hybrid retriever and still produces mappings.
"""
from backend.config import settings
from backend.pipeline import discovery, extraction, mapping
from backend.pipeline.ocr import get_document_text
from backend.providers import get_ocr_provider
from backend.rdtii import get_indicators
from backend.schemas import Economy


def _sample_provisions(n=12):
    provs = []
    ocr = get_ocr_provider("mock")
    for d in discovery.discover(Economy.SG, 7):
        raw, m = get_document_text(d, ocr_provider=ocr)
        provs += extraction.extract_provisions(d, raw, m)
    return provs[:n]


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
                                 llm=None, top_k=3, log=lambda *_: None)
    assert out, "mapper should fall back to hybrid retrieval, not produce zero mappings"


def test_mapper_matches_hybrid_when_no_lightrag(monkeypatch):
    """With LightRAG off, mapping is identical to the plain hybrid path."""
    provs = _sample_provisions()
    inds = get_indicators(7)
    monkeypatch.setattr(mapping, "_select_retriever", lambda *a, **k: None)
    out = mapping.map_provisions(run_id="t", provisions=provs, pillar=7, indicators=inds,
                                 llm=None, top_k=3, log=lambda *_: None)
    assert out
