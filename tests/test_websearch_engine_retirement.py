"""A dead engine must be asked twice, not once per query.

`_diag["engine_failures"]` already recorded which engines had failed and why — and nothing read
it. `_engines()` returned the same full list for every query, so an engine that had answered
"HTTP 400 — Not enough credits" was asked again on the next query, and the next, for the whole
run.

That is free when the failure is fast and ruinous when it is not. Measured 2026-09-12 on an
India pillar-6 run with DuckDuckGo not answering at all: each attempt cost 21s x 3 retries x 2
endpoints, so ONE query spent about 110 seconds re-establishing what the previous query had
already established. India has four web-search sources and `reset_circuit()` runs per LANE, so
the empty counter restarted each time. The user's report was that the run "stopped" — the
technical log showed three lines and then nothing.

Neither kind of failure heals inside a run: a spend cap does not refill and a blocked endpoint
does not unblock in thirty seconds.
"""
from __future__ import annotations

import pytest

from backend.pipeline import websearch


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_diagnostics()
    websearch.reset_circuit()


def _engine(name, behaviour):
    behaviour.__name__ = name
    return behaviour


def test_an_engine_that_keeps_failing_is_dropped_for_the_run(monkeypatch):
    calls = []

    def dead(_c, _q, _n):
        calls.append(1)
        raise websearch.EngineUnavailable("dead", "HTTP 400 — Not enough credits")

    monkeypatch.setattr(websearch, "_engines", lambda: [
        e for e in [_engine("dead", dead)]
        if websearch._engine_strikes.get("dead", 0) < websearch._STRIKES])
    for i in range(6):
        websearch.search(f"query {i}", log=lambda *_: None)
    assert len(calls) == websearch._STRIKES, (
        f"a dead engine was asked {len(calls)} times across six queries")


def test_one_failure_is_not_enough_to_retire_it(monkeypatch):
    """A single blip must not retire an engine that still works — the run would lose it for
    nothing, and there are only five."""
    state = {"n": 0}

    def flaky(_c, _q, _n):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("blip")
        return [("https://example.gov/x", "An Act", "")]

    monkeypatch.setattr(websearch, "_engines", lambda: [_engine("flaky", flaky)])
    assert websearch.search("first", log=lambda *_: None) == []
    assert websearch._engine_strikes.get("flaky") == 1
    assert websearch.search("second", log=lambda *_: None)
    assert "flaky" not in websearch._engine_strikes, (
        "a success must clear the strikes, or a healthy run retires its engines by attrition")


def test_retirement_is_per_run_not_per_lane(monkeypatch):
    """`reset_circuit` runs once per web-search SOURCE and India has four of them, which is how
    the empty counter kept restarting. Retirement has to outlive that and be cleared only by
    `reset_diagnostics`, which runs once per run."""
    websearch._engine_strikes["dead"] = websearch._STRIKES
    websearch.reset_circuit()
    assert websearch._engine_strikes.get("dead") == websearch._STRIKES
    websearch.reset_diagnostics()
    assert not websearch._engine_strikes


def test_the_browser_lane_reports_its_failure_instead_of_returning_empty(monkeypatch):
    """`_scrapling_ddg` used to return [] when its fetch failed, which is indistinguishable
    from 'searched and found nothing' — so it never earned a strike and re-ran its own 3 x 21s
    retry on every query."""
    monkeypatch.setattr(websearch.scrapling_fetch if hasattr(websearch, "scrapling_fetch")
                        else websearch, "_noop", None, raising=False)
    from backend.pipeline import scrapling_fetch
    monkeypatch.setattr(scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(scrapling_fetch, "fetch", lambda *a, **k: None)
    with pytest.raises(websearch.EngineUnavailable):
        websearch._scrapling_ddg(None, "q", 5)


def test_a_missing_scrapling_is_also_a_retirable_failure(monkeypatch):
    from backend.pipeline import scrapling_fetch
    monkeypatch.setattr(scrapling_fetch, "available", lambda: False)
    with pytest.raises(websearch.EngineUnavailable):
        websearch._scrapling_ddg(None, "q", 5)
