"""A search engine that cannot answer must say so.

Measured 2026-09-07: Serper answered `HTTP 400 {"message":"Not enough credits"}` and
`_serper()` returned an empty list, so the run reported "no laws found" for Singapore —
whose only discovery lane is web search. A dead key and an economy with no relevant law
produced byte-identical output. These tests pin the difference.
"""
import json

import pytest

from backend.pipeline import websearch


class _Resp:
    """The parts of an httpx.Response the engines actually read."""

    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Client:
    def __init__(self, resp):
        self._resp = resp

    def post(self, *a, **kw):
        return self._resp

    def get(self, *a, **kw):
        return self._resp


def test_serper_out_of_credits_raises_engine_unavailable(monkeypatch):
    monkeypatch.setattr(websearch.settings, "serper_api_key", "deadbeef")
    client = _Client(_Resp(400, {"message": "Not enough credits", "statusCode": 400}))
    with pytest.raises(websearch.EngineUnavailable) as exc:
        websearch._serper(client, "pdpa singapore", 10)
    assert exc.value.engine == "serper"
    assert "400" in exc.value.detail
    assert "Not enough credits" in exc.value.detail


def test_serper_with_no_key_is_not_a_failure(monkeypatch):
    """No key configured is a choice, not a broken engine — it must not be reported."""
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    assert websearch._serper(_Client(_Resp(200, {"organic": []})), "q", 10) == []


def test_duckduckgo_challenge_page_raises(monkeypatch):
    """DuckDuckGo answers 202 with an anomaly/challenge page, not 200. Measured 2026-09-07."""
    client = _Client(_Resp(202, text="<html>anomaly ... challenge</html>"))
    with pytest.raises(websearch.EngineUnavailable) as exc:
        websearch._ddg_html(client, "pdpa singapore", 10)
    assert exc.value.engine == "ddg_html"
    assert "202" in exc.value.detail


def test_search_records_the_failure_and_keeps_going(monkeypatch, tmp_path):
    """One dead engine must not be fatal, but it must be REPORTED."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_circuit()

    def dead(client, q, n):
        raise websearch.EngineUnavailable("ddg_html", "HTTP 202 (challenge page)")

    def alive(client, q, n):
        return [("https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", "snippet")]

    monkeypatch.setattr(websearch, "_engines", lambda: [dead, alive])
    lines = []
    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lines.append)

    assert len(out) == 1, "a live engine after a dead one must still answer"
    diag = websearch.diagnostics()
    assert diag["engine_failures"]["ddg_html"] == "HTTP 202 (challenge page)"
    assert any("ddg_html" in ln and "unavailable" in ln for ln in lines)


def test_zero_results_is_not_an_engine_failure(monkeypatch, tmp_path):
    """An engine that answers with nothing is a different fact from an engine that is down."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_circuit()
    monkeypatch.setattr(websearch, "_engines", lambda: [lambda c, q, n: []])

    assert websearch.search("nothing matches this", log=lambda *_: None) == []
    diag = websearch.diagnostics()
    assert diag["engine_failures"] == {}
    assert diag["empty_queries"] == 1
