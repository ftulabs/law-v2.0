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
    websearch.reset_diagnostics()

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
    websearch.reset_diagnostics()
    monkeypatch.setattr(websearch, "_engines", lambda: [lambda c, q, n: []])

    assert websearch.search("nothing matches this", log=lambda *_: None) == []
    diag = websearch.diagnostics()
    assert diag["engine_failures"] == {}
    assert diag["empty_queries"] == 1


import datetime as _dt


def _iso(days_ago: float) -> str:
    return (_dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(days=days_ago)).isoformat()


def test_fresh_cache_entry_is_served_without_touching_the_network(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_diagnostics()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data site:sso.agc.gov.sg": {
            "results": [["https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", ""]],
            "fetched_at": _iso(1), "engine": "serper"}}), encoding="utf-8")

    def explode(client, q, n):
        raise AssertionError("a fresh cache hit must not reach the network")

    monkeypatch.setattr(websearch, "_engines", lambda: [explode])
    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lambda *_: None)
    assert out == [("https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", "")]
    assert websearch.diagnostics()["cache_hits"] == 1


def test_stale_cache_entry_is_a_miss(monkeypatch, tmp_path):
    """The entry that made Singapore look alive was eight days old."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_diagnostics()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data site:sso.agc.gov.sg": {
            "results": [["https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", ""]],
            "fetched_at": _iso(8), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://fresh", "Fresh", "")]])

    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lambda *_: None)
    assert out == [("https://fresh", "Fresh", "")], "stale entry must not be served"
    assert websearch.diagnostics()["network_queries"] == 1


def test_legacy_bare_list_entry_is_treated_as_expired(monkeypatch, tmp_path):
    """Every one of the 890 entries written before this change is a bare list with no
    timestamp. It cannot be shown to be fresh, so it must never be served as live."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_diagnostics()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data": [["https://old", "Old", ""]]}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://fresh", "Fresh", "")]])

    assert websearch.search("personal data", log=lambda *_: None) == \
        [("https://fresh", "Fresh", "")]


def test_ttl_of_zero_disables_the_cache_entirely(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 0.0)
    websearch.reset_diagnostics()
    (tmp_path / "_search.json").write_text(json.dumps({
        "q": {"results": [["https://cached", "C", ""]],
              "fetched_at": _iso(0), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, qq, n: [("https://fresh", "Fresh", "")]])

    assert websearch.search("q", log=lambda *_: None) == [("https://fresh", "Fresh", "")]


def test_a_successful_search_prunes_expired_entries_from_the_cache_file(monkeypatch, tmp_path):
    """Nothing else prunes `_search.json` — `_entry_results()` only declines to SERVE a stale
    entry, so the 890 dead 2026-08-31 entries were being re-serialised on every successful
    query. A successful write must drop already-expired keys, leaving fresh ones alone."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_diagnostics()
    cache_file = tmp_path / "_search.json"
    cache_file.write_text(json.dumps({
        "stale query": {"results": [["https://old", "Old", ""]],
                        "fetched_at": _iso(30), "engine": "serper"},
        "fresh query": {"results": [["https://still-good", "Still good", ""]],
                        "fetched_at": _iso(1), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, qq, n: [("https://new", "New", "")]])

    websearch.search("brand new query", log=lambda *_: None)

    on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "stale query" not in on_disk
    assert "fresh query" in on_disk
    assert "brand new query" in on_disk


def test_ttl_disabled_does_not_empty_the_cache_file_on_write(monkeypatch, tmp_path):
    """max_age_days<=0 makes `_entry_results` treat every entry (including the one just
    written) as expired — the prune must be guarded so a disabled TTL doesn't wipe the file
    on the very next successful search."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 0.0)
    websearch.reset_diagnostics()
    cache_file = tmp_path / "_search.json"
    cache_file.write_text(json.dumps({
        "existing query": {"results": [["https://kept", "Kept", ""]],
                           "fetched_at": _iso(1), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, qq, n: [("https://new", "New", "")]])

    websearch.search("another query", log=lambda *_: None)

    on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "existing query" in on_disk
    assert "another query" in on_disk


def test_a_written_entry_carries_its_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_diagnostics()

    def named(client, q, n):
        return [("https://x", "X", "")]

    named.__name__ = "_serper"
    monkeypatch.setattr(websearch, "_engines", lambda: [named])
    websearch.search("q", log=lambda *_: None)

    entry = json.loads((tmp_path / "_search.json").read_text(encoding="utf-8"))["q"]
    assert entry["engine"] == "_serper"
    assert entry["fetched_at"].startswith(str(_dt.datetime.now(_dt.timezone.utc).year))


def test_a_timezone_naive_stamp_is_read_as_utc(monkeypatch, tmp_path):
    """fromisoformat on a stamp with no offset yields a NAIVE datetime, and .timestamp()
    then reads it in the host's local zone — skewing the age by the UTC offset. On a
    UTC+7 machine a 7-hour-old entry would read as fresh-or-stale depending on the host,
    which is not a property of the cache."""
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 1.0)
    naive = (_dt.datetime.now(_dt.timezone.utc)
             - _dt.timedelta(days=3)).replace(tzinfo=None).isoformat()
    assert websearch._entry_results(
        {"results": [["https://x", "X", ""]], "fetched_at": naive, "engine": "serper"}) is None

    fresh_naive = (_dt.datetime.now(_dt.timezone.utc)
                   - _dt.timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert websearch._entry_results(
        {"results": [["https://x", "X", ""]], "fetched_at": fresh_naive, "engine": "serper"}) \
        == [("https://x", "X", "")]


def test_a_corrupted_cache_row_is_a_miss_not_an_exception(monkeypatch):
    """The comprehension that builds the result tuples sat OUTSIDE the try, so a row that is
    a string, or shorter than two elements, raised instead of being declined.

    Phase 1 widened this from a nuisance to a stopper: _entry_results used to run only when
    its own key was queried, and since the expiry-prune landed it runs across the whole cache
    on every successful write. One corrupted row broke every search.
    """
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    fresh = _iso(1)
    for rows in (["not-a-list"], [[]], [["only-one-element"]], [None], "not-a-list-at-all"):
        entry = {"results": rows, "fetched_at": fresh, "engine": "serper"}
        assert websearch._entry_results(entry) is None, f"{rows!r} should be a miss"


def test_a_good_row_still_survives_the_hardening(monkeypatch):
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    entry = {"results": [["https://x", "X", "snip"]], "fetched_at": _iso(1), "engine": "serper"}
    assert websearch._entry_results(entry) == [("https://x", "X", "snip")]


def test_one_corrupted_row_does_not_discard_a_whole_good_cache(monkeypatch, tmp_path):
    """The prune walks every entry. A single bad neighbour must not take the good ones with it."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_diagnostics(); websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "good": {"results": [["https://good", "G", ""]], "fetched_at": _iso(1), "engine": "s"},
        "bad": {"results": ["corrupt"], "fetched_at": _iso(1), "engine": "s"},
    }), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://new", "N", "")]])

    websearch.search("something new", log=lambda *_: None)
    after = json.loads((tmp_path / "_search.json").read_text(encoding="utf-8"))
    assert "good" in after, "a corrupted neighbour must not evict a healthy entry"
