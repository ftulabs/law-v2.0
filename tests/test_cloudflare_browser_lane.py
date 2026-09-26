"""A Cloudflare managed challenge escalates to the stealth browser, and a file the browser
would DOWNLOAD is fetched from inside a page of the same site (BPK, measured 2026-09-26)."""
import base64
import sys
import types

from backend.config import settings
from backend.pipeline import scrapling_fetch as sf


class _Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status, self.body, self.headers = status, body, headers or {}


def _install(monkeypatch, fetcher_get, stealthy_fetch):
    mod = types.ModuleType("scrapling.fetchers")
    mod.Fetcher = types.SimpleNamespace(get=fetcher_get)
    mod.StealthyFetcher = types.SimpleNamespace(fetch=stealthy_fetch)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", mod)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr("time.sleep", lambda *_: None)


def test_a_named_challenge_goes_to_the_browser_once(monkeypatch):
    calls = {"get": 0, "browser": []}

    def get(url, **kw):
        calls["get"] += 1
        return _Resp(403, b"<title>Just a moment...</title>", {"cf-mitigated": "challenge"})

    def browse(url, **kw):
        calls["browser"].append(kw.get("solve_cloudflare"))
        return _Resp(200, b"<title>Pencarian Peraturan</title><a href='/Details/1/x'>", {})

    _install(monkeypatch, get, browse)
    monkeypatch.setattr(settings, "fetch_browser_on_block", True)
    res = sf.fetch("https://peraturan.bpk.go.id/Search?keywords=pusat+data", log=lambda *_: None)
    assert res and res.engine == "scrapling-stealth" and b"Pencarian" in res.body
    assert calls["get"] == 1 and calls["browser"] == [False]


def test_the_challenge_page_itself_is_not_accepted_and_the_checkbox_is_tried(monkeypatch):
    seen = []

    def browse(url, **kw):
        seen.append(kw.get("solve_cloudflare"))
        if not kw.get("solve_cloudflare"):
            return _Resp(200, b"<title>Just a moment...</title>")
        return _Resp(200, b"<title>real</title>")

    _install(monkeypatch, None, browse)
    res = sf.browser_fetch("https://x.example/page", log=lambda *_: None)
    assert res.body == b"<title>real</title>" and seen == [False, True]


def test_no_browser_when_escalation_is_switched_off(monkeypatch):
    def get(url, **kw):
        return _Resp(403, b"", {"cf-mitigated": "challenge"})

    def browse(url, **kw):
        raise AssertionError("browser must not run")

    _install(monkeypatch, get, browse)
    monkeypatch.setattr(settings, "fetch_browser_on_block", False)
    monkeypatch.setattr(settings, "crawl_browser", False)
    assert sf.fetch("https://x.example/p", log=lambda *_: None) is None


def test_a_pdf_is_read_from_inside_the_site_root(monkeypatch):
    pdf = b"%PDF-1.4 body"
    opened = []

    class _Page:
        def evaluate(self, js, u):
            assert u.endswith(".pdf")
            return {"status": 200, "ct": "application/pdf", "b64": base64.b64encode(pdf).decode()}

    def browse(url, **kw):
        opened.append(url)
        kw["page_action"](_Page())
        return _Resp(200, b"<html>root</html>")

    _install(monkeypatch, None, browse)
    res = sf.browser_fetch("https://peraturan.bpk.go.id/Download/1/UU%20Nomor%2027.pdf",
                           log=lambda *_: None)
    assert opened == ["https://peraturan.bpk.go.id/"]
    assert res.body == pdf and res.content_type == "application/pdf"
