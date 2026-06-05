"""Scrapling escalation for Zone-1 fetching.

Scrapling is the bot-block ESCALATION, not a hard dependency: when httpx fails, the fetch
retries through Scrapling and stores the body in the same content-addressed cache; if
Scrapling is unavailable or also fails, the fetch degrades to None and the pipeline keeps
whatever httpx produced. These tests pin that contract without touching the network.
"""
from backend.pipeline import fetch as fetch_mod
from backend.pipeline import scrapling_fetch


def test_available_is_bool():
    assert isinstance(scrapling_fetch.available(), bool)


def test_escalation_stores_recovered_body(monkeypatch, tmp_path):
    monkeypatch.setattr(scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(
        scrapling_fetch, "fetch",
        lambda url, **kw: scrapling_fetch.ScrapeResult(
            body=b"<html>Personal Data Protection Act</html>",
            content_type="text/html", status=200, engine="scrapling-fetcher"),
    )
    idx = {}
    fr = fetch_mod._scrapling_escalate("https://portal.example/law", idx, lambda *_: None)
    assert fr is not None
    assert fr.fmt.value == "html"
    assert idx["https://portal.example/law"]["engine"] == "scrapling-fetcher"


def test_escalation_returns_none_when_scrapling_fails(monkeypatch):
    monkeypatch.setattr(scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(scrapling_fetch, "fetch", lambda url, **kw: None)
    assert fetch_mod._scrapling_escalate("https://portal.example/x", {}, lambda *_: None) is None


def test_escalation_respects_byte_cap(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(scrapling_fetch, "available", lambda: True)
    big = b"x" * (settings.fetch_max_bytes + 10)
    monkeypatch.setattr(
        scrapling_fetch, "fetch",
        lambda url, **kw: scrapling_fetch.ScrapeResult(big, "application/pdf", 200, "scrapling-fetcher"),
    )
    assert fetch_mod._scrapling_escalate("https://portal.example/huge.pdf", {}, lambda *_: None) is None
