"""Extraction/OCR now runs concurrently across documents (was strictly sequential) — the
result must be identical regardless of how many workers process it, same contract already
pinned for mapping's concurrency in test_mapping_perf.py.
"""
from backend.config import settings
from backend.pipeline.orchestrator import run_pipeline
from backend.schemas import Economy


def _provision_keys(economy):
    orig = settings.extraction_concurrency
    try:
        settings.extraction_concurrency = 1
        seq = run_pipeline(economy, [6, 7], use_samples=True, ocr_provider="mock",
                           llm_provider="mock", log=lambda *_: None, use_result_cache=False)
        settings.extraction_concurrency = 8
        par = run_pipeline(economy, [6, 7], use_samples=True, ocr_provider="mock",
                           llm_provider="mock", log=lambda *_: None, use_result_cache=False)
    finally:
        settings.extraction_concurrency = orig
    return seq, par


def test_sequential_and_concurrent_extraction_match():
    seq, par = _provision_keys(Economy.SG)
    seq_keys = {(m.indicator_id, m.provision_id) for m in seq.mappings}
    par_keys = {(m.indicator_id, m.provision_id) for m in par.mappings}
    assert seq_keys == par_keys
    assert seq.meta.provisions_extracted == par.meta.provisions_extracted
