"""The cache had no lifecycle, so it grew to 1.3 GB and kept every engine version forever.

What must NOT be reclaimed matters more than what must: the panel requires the tool to
re-process already-downloaded documents without re-fetching, so extraction results are a
mechanism, not waste. Only SUPERSEDED versions of the same document may go.
"""
import json
import time
from pathlib import Path

from tools.cache_gc import Reclaim, plan_gc


def _write(p: Path, size: int, age_days: float = 0.0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        import os
        os.utime(p, (old, old))
    return p


def test_superseded_engine_output_is_reclaimed_and_the_newest_is_kept(tmp_path):
    ex = tmp_path / "_extracted"
    _write(ex / "abc123_rapidocr_v4.json", 100)
    _write(ex / "abc123_rapidocr_v5.json", 100)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0, keep_engines=False)
    paths = {r.path.name for r in plan}
    assert "abc123_rapidocr_v4.json" in paths
    assert "abc123_rapidocr_v5.json" not in paths, "the newest engine output must survive"


def test_a_document_with_only_one_engine_version_is_never_reclaimed(tmp_path):
    ex = tmp_path / "_extracted"
    _write(ex / "solo_rapidocr_v5.json", 100)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0, keep_engines=False)
    assert not [r for r in plan if r.path.name == "solo_rapidocr_v5.json"]


def test_lightrag_is_reclaimed_only_when_the_retriever_does_not_use_it(tmp_path, monkeypatch):
    _write(tmp_path / "lightrag" / "graph.graphml", 5000)
    from tools import cache_gc
    monkeypatch.setattr(cache_gc.settings, "retriever", "hybrid")
    assert any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))
    monkeypatch.setattr(cache_gc.settings, "retriever", "lightrag")
    assert not any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))


def test_old_document_bodies_are_reclaimed_by_age(tmp_path):
    _write(tmp_path / "old.pdf", 1000, age_days=90)
    _write(tmp_path / "new.pdf", 1000, age_days=1)
    names = {r.path.name for r in plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False)}
    assert "old.pdf" in names and "new.pdf" not in names


def test_embedding_caches_are_never_reclaimed_by_age(tmp_path):
    """Measured at 16x on repeat runs (CLAUDE.md, retrieval perf findings) and rebuilt only
    at real CPU cost. Age is the wrong axis for these."""
    _write(tmp_path / "_emb_model_2048.npz", 1000, age_days=365)
    _write(tmp_path / "_ce_baai-bge-reranker-v2-m3.npz", 1000, age_days=365)
    assert plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False) == []


def test_the_search_cache_is_never_reclaimed_by_this_tool(tmp_path):
    """It expires per entry (search_cache_max_age_days), which preserves the provenance
    a stale-vs-fresh decision needs. Deleting the file wholesale would hide that."""
    _write(tmp_path / "_search.json", 1000, age_days=365)
    assert plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False) == []


def test_size_cap_reclaims_oldest_first(tmp_path):
    _write(tmp_path / "a.pdf", 3_000_000, age_days=10)
    _write(tmp_path / "b.pdf", 3_000_000, age_days=5)
    _write(tmp_path / "c.pdf", 3_000_000, age_days=1)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0.006, keep_engines=False)
    assert [r.path.name for r in plan] == ["a.pdf"]


def test_every_reclaim_states_a_reason(tmp_path):
    _write(tmp_path / "old.pdf", 1000, age_days=90)
    plan = plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False)
    assert plan and all(isinstance(r, Reclaim) and r.reason for r in plan)
