"""The cache had no lifecycle, so it grew to 1.3 GB and kept every engine version forever.

What must NOT be reclaimed matters more than what must: the panel requires the tool to
re-process already-downloaded documents without re-fetching, so extraction results are a
mechanism, not waste. Only SUPERSEDED versions of the same document may go.
"""
import json
import sys
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


def test_lightrag_is_reclaimed_only_when_the_retriever_cannot_read_it(tmp_path, monkeypatch):
    _write(tmp_path / "lightrag" / "graph.graphml", 5000)
    from tools import cache_gc
    monkeypatch.setattr(cache_gc.settings, "retriever", "hybrid")
    assert any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))
    monkeypatch.setattr(cache_gc.settings, "retriever", "lightrag")
    assert not any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))


def test_lightrag_is_not_reclaimed_under_retriever_auto(tmp_path, monkeypatch):
    """RETRIEVER=auto DOES build and read LightRAG once a corpus crosses
    lightrag_min_provisions (backend/pipeline/mapping.py:36) — reclaiming it here would delete
    an artefact the retriever rebuilds on the very next run, under a message claiming auto
    never reads it. Empty string must default to "auto" too, matching mapping.py."""
    _write(tmp_path / "lightrag" / "graph.graphml", 5000)
    from tools import cache_gc
    monkeypatch.setattr(cache_gc.settings, "retriever", "auto")
    assert not any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))
    monkeypatch.setattr(cache_gc.settings, "retriever", "")
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
    """`plan_gc` never touches `_search.json` wholesale — deleting it would lose provenance a
    stale-vs-fresh decision needs. Its per-ENTRY lifecycle is handled elsewhere: on every
    successful query, `websearch.search()` drops already-expired entries when it rewrites the
    file (see tests/test_websearch_diagnostics.py)."""
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


def test_main_without_apply_leaves_every_file_on_disk(tmp_path, monkeypatch):
    """The `--apply` gate is the single most important property in this tool — a dry run
    (the default) must never delete."""
    old = _write(tmp_path / "old.pdf", 1000, age_days=90)
    from tools import cache_gc
    monkeypatch.setattr(sys, "argv",
                        ["cache_gc.py", "--root", str(tmp_path), "--max-age-days", "30"])
    assert cache_gc.main() == 0
    assert old.exists()


def test_main_with_apply_deletes(tmp_path, monkeypatch):
    old = _write(tmp_path / "old.pdf", 1000, age_days=90)
    from tools import cache_gc
    monkeypatch.setattr(sys, "argv",
                        ["cache_gc.py", "--root", str(tmp_path), "--max-age-days", "30", "--apply"])
    assert cache_gc.main() == 0
    assert not old.exists()
