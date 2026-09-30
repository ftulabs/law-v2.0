"""Discovery speed-ups measured 2026-09-30, pinned so they cannot quietly regress.

1. A two-pillar run calls discovery twice, and the portal-ENUMERATING lanes read the same
   query-independent index pages both times (Timor-Leste: 18 pages behind Crawl-delay: 10,
   ~185 s re-paid). `portal_get(..., memo=True)` answers the second read from memory.
2. With html.duckduckgo.com refusing TCP, one web-search query cost ~4.5 minutes inside
   `_scrapling_ddg` (4 outer x 3 inner connect timeouts) and the engine needed two failures to
   be retired. It now probes once and retires on the first failure; an engine that cannot even
   connect is retired on the spot.

Nothing here touches the network.
"""
import httpx
import pytest

from backend.pipeline import portal, websearch


class _Resp:
    def __init__(self, status=200, body=b"page"):
        self.status_code = status
        self.content = body
        self.text = body.decode()


class _Client:
    def __init__(self):
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return _Resp()


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    portal.clear_memo()
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    yield
    portal.clear_memo()


def test_a_memoised_index_page_is_read_once():
    c = _Client()
    a = portal.portal_get(c, "https://example.gov/index", log=lambda *_: None, memo=True)
    assert portal.memoized("https://example.gov/index")
    b = portal.portal_get(c, "https://example.gov/index", log=lambda *_: None, memo=True)
    assert a is b and c.calls == ["https://example.gov/index"]


def test_without_memo_every_call_goes_to_the_portal():
    c = _Client()
    for _ in range(2):
        portal.portal_get(c, "https://example.gov/q", log=lambda *_: None)
    assert len(c.calls) == 2 and not portal.memoized("https://example.gov/q")


def test_memo_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(portal.settings, "discovery_page_memo_seconds", 0)
    c = _Client()
    for _ in range(2):
        portal.portal_get(c, "https://example.gov/index", log=lambda *_: None, memo=True)
    assert len(c.calls) == 2


def test_a_forgotten_page_is_asked_again():
    """SSO's empty browse window is a refusal: it must be re-asked, not replayed."""
    c = _Client()
    portal.portal_get(c, "https://example.gov/w", log=lambda *_: None, memo=True)
    portal.forget("https://example.gov/w")
    portal.portal_get(c, "https://example.gov/w", log=lambda *_: None, memo=True)
    assert len(c.calls) == 2


def test_the_browser_search_engine_is_probed_once_and_retired_on_first_failure(monkeypatch):
    from backend.pipeline import scrapling_fetch
    seen = {}

    def fake_fetch(url, **kw):
        seen.update(kw)
        return None

    monkeypatch.setattr(scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(scrapling_fetch, "fetch", fake_fetch)
    with pytest.raises(websearch.EngineUnavailable):
        websearch._scrapling_ddg(None, "q", 5)
    assert seen.get("attempts") == 1 and seen.get("retries") == 1
    assert websearch._strikes_for("_scrapling_ddg") == 1


def test_an_engine_that_cannot_connect_is_retired_on_the_spot(monkeypatch):
    calls = []

    def unreachable(_c, _q, _n):
        calls.append(1)
        raise httpx.ConnectTimeout("no route")

    unreachable.__name__ = "unreachable"
    monkeypatch.setattr(websearch, "_engines", lambda: [
        e for e in [unreachable]
        if websearch._engine_strikes.get("unreachable", 0) < websearch._strikes_for("unreachable")])
    for i in range(4):
        websearch.search(f"query {i}", log=lambda *_: None)
    assert len(calls) == 1
