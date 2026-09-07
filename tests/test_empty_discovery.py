"""A run that discovers nothing must say why.

Zero documents is currently indistinguishable from an economy with no relevant law: the
run completes, exports an empty CSV and exits 0. On 2026-09-07 every search engine was
down and that is exactly what Thailand, Laos and Timor-Leste produced.

`frontend/runview.py` already renders `[error]` lines as a (what happened, what to do)
pair. These tests pin that discovery emits them in that shape.
"""
from backend.pipeline import discovery, websearch
from backend.schemas import Economy


def _reset():
    websearch.reset_circuit()


def test_a_dead_search_engine_is_named_as_the_cause(monkeypatch):
    _reset()
    websearch._diag["engine_failures"]["serper"] = "HTTP 400 — Not enough credits"
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)

    assert all(ln.startswith("[error] ") for ln in lines)
    assert any("serper" in ln and "Not enough credits" in ln for ln in lines)
    assert lines[-1].startswith("[error] what to do:")


def test_an_economy_with_no_portal_lane_says_so(monkeypatch):
    """Singapore's only lane is websearch, so a dead engine costs it the whole economy."""
    _reset()
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "SG", "name": "Singapore Statutes Online", "adapter": "websearch"}])
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)
    joined = " ".join(lines)
    assert "no portal-native lane" in joined
    assert "SG" in joined


def test_an_economy_with_a_portal_lane_does_not_blame_the_search_engine(monkeypatch):
    _reset()
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "MY", "name": "Laws of Malaysia (AGC)", "adapter": "my_catalogue"}])
    lines = discovery.explain_empty_discovery(Economy.MY, log=lambda *_: None)
    assert "no portal-native lane" not in " ".join(lines)
    assert any("my_catalogue" in ln or "Laws of Malaysia" in ln for ln in lines)


def test_the_provenance_counts_are_reported(monkeypatch):
    _reset()
    websearch._diag["cache_hits"] = 12
    websearch._diag["network_queries"] = 3
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "TH", "name": "x", "adapter": "websearch"}])
    joined = " ".join(discovery.explain_empty_discovery(Economy.TH, log=lambda *_: None))
    assert "12" in joined and "3" in joined


def test_the_lines_are_logged_not_just_returned():
    _reset()
    out = []
    discovery.explain_empty_discovery(Economy.LA, log=out.append)
    assert out and out == discovery.explain_empty_discovery(Economy.LA, log=lambda *_: None)
