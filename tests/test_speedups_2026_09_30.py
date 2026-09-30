"""The 2026-09-30 speed-ups: each one must change the wall clock and nothing else."""
import numpy as np

from backend.config import settings
from backend.pipeline import retrieval
from backend.schemas import Economy, Provision


def _prov(i):
    return Provision(provision_id=f"d#p{i}", doc_id="d", economy=Economy.SG, law_name="Act",
                     article_section=f"Section {i}", verbatim_snippet=f"personal data text {i}",
                     source_url="u")


def _fake_embed(calls):
    def embed(texts):
        calls.append(list(texts))
        return np.asarray([[float(len(t)), 1.0] for t in texts], dtype="float32")
    return embed


def test_prewarmed_vectors_are_the_ones_retrieval_uses(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(retrieval, "_EMB_CACHE", {})
    monkeypatch.setattr(retrieval, "_PREWARM_FRESH", {})
    calls: list = []
    monkeypatch.setattr(retrieval, "_embed", _fake_embed(calls))
    provs = [_prov(i) for i in range(5)]
    assert retrieval.prewarm_embeddings(provs) == 5
    calls.clear()
    retrieval._dense_scores("query", provs)
    assert calls == [["query"]]              # only the query is embedded — provisions were ready
    retrieval.flush_prewarm()
    assert retrieval._disk_cache_path().exists()


def test_prewarm_stops_when_the_overlap_ends(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(retrieval, "_EMB_CACHE", {})
    calls: list = []
    monkeypatch.setattr(retrieval, "_embed", _fake_embed(calls))
    assert retrieval.prewarm_embeddings([_prov(i) for i in range(5)], still_open=lambda: False) == 0
    assert calls == []


def test_the_disk_cache_follows_the_cache_directory(monkeypatch, tmp_path):
    """A cache read from one folder must never be written over another folder's file."""
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setattr(settings, "cache_dir", str(a))
    monkeypatch.setattr(retrieval, "_DISK_CACHE", None)
    first = retrieval._load_disk_cache()
    first["x"] = np.zeros(2, dtype="float32")
    monkeypatch.setattr(settings, "cache_dir", str(b))
    assert "x" not in retrieval._load_disk_cache()


def test_only_openrouter_runs_48_way():
    from backend.providers.llm_openrouter import OpenRouterLLM
    assert settings.mapping_concurrency == 16          # every provider nobody measured
    assert OpenRouterLLM("k").suggested_concurrency() == settings.openrouter_concurrency == 48
