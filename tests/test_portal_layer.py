"""The mechanics every portal adapter shares, pinned once.

Six adapters are written against this. The alternative — each adapter carrying its own
robots check, its own backoff and its own DiscoveredDoc construction — is how the Malaysia
robots defect (robots.txt HTTP 500 read as "disallowed", costing every statute PDF on the
primary portal) would come to need six separate fixes, five of which would be found late.

Nothing here touches the network: portal_get is driven with a fake client.
"""
import pytest

from backend.pipeline import portal
from backend.schemas import DiscoveredDoc, DocFormat, Economy


class _Resp:
    def __init__(self, status, body=b"x", text=None):
        self.status_code = status
        self.content = body
        self.text = text if text is not None else body.decode("utf-8", "ignore")


class _Client:
    """Returns the queued responses in order, then repeats the last one."""

    def __init__(self, *responses):
        self._queue = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]


def test_portal_get_returns_the_first_good_response(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    c = _Client(_Resp(200, b"hello"))
    r = portal.portal_get(c, "https://example.gov/x", log=lambda *_: None)
    assert r is not None and r.content == b"hello"
    assert len(c.calls) == 1


def test_portal_get_treats_an_empty_202_as_a_throttle_and_retries(monkeypatch):
    """SSO answers a burst with 202 and an EMPTY body rather than 429 (verified 2026-08-01,
    backend/corpus/catalogue.py). A 202 with content is a real response and must not retry."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(portal.time, "sleep", lambda *_: None)
    c = _Client(_Resp(202, b""), _Resp(200, b"ok"))
    r = portal.portal_get(c, "https://sso.agc.gov.sg/Browse/Act", log=lambda *_: None)
    assert r is not None and r.content == b"ok"
    assert len(c.calls) == 2, "the empty 202 must have been retried"


def test_portal_get_gives_up_after_tries_and_returns_none(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(portal.time, "sleep", lambda *_: None)
    c = _Client(_Resp(500, b""))
    assert portal.portal_get(c, "https://x.gov/y", log=lambda *_: None, tries=3) is None
    assert len(c.calls) == 3


def test_portal_get_refuses_a_disallowed_url_without_fetching(monkeypatch):
    """A robots refusal is an answer, not an obstacle. It must cost zero requests."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: False)
    c = _Client(_Resp(200, b"should never be fetched"))
    lines = []
    assert portal.portal_get(c, "https://x.gov/forbidden", log=lines.append) is None
    assert c.calls == []
    assert any("robots" in ln.lower() for ln in lines)


def test_make_doc_infers_pdf_from_the_url():
    d = portal.make_doc(Economy.TL, "https://mj.gov.tl/jornal/files/Law-2002-01.pdf",
                        "Lei 1/2002", "Jornal da República")
    assert isinstance(d, DiscoveredDoc)
    assert d.fmt == DocFormat.PDF_TEXT
    assert d.economy == Economy.TL
    assert d.source_url.endswith("Law-2002-01.pdf")


def test_make_doc_defaults_to_html_for_a_page():
    d = portal.make_doc(Economy.CN, "https://www.cac.gov.cn/2024-03/22/c_1712.htm",
                        "个人信息保护法", "cac.gov.cn")
    assert d.fmt == DocFormat.HTML


def test_make_doc_honours_an_explicit_format():
    d = portal.make_doc(Economy.TH, "https://apig.law.go.th/law/1", "พ.ร.บ.", "law.go.th",
                        fmt=DocFormat.HTML)
    assert d.fmt == DocFormat.HTML


def test_doc_id_is_stable_and_economy_scoped():
    a = portal.doc_id("SG", "https://sso.agc.gov.sg/Act/PDPA2012")
    b = portal.doc_id("SG", "https://sso.agc.gov.sg/Act/PDPA2012")
    c = portal.doc_id("MY", "https://sso.agc.gov.sg/Act/PDPA2012")
    assert a == b and a != c
    assert a.startswith("SG-")


def test_doc_id_matches_the_id_discovery_already_uses():
    """live-mode dedup keys on doc_id, so a new id scheme would make every adapter's
    documents look distinct from the same document found by an existing lane."""
    from backend.pipeline.discovery import _doc_id
    url = "https://example.gov/act/1"
    assert portal.doc_id("AU", url) == _doc_id("AU", url)


def test_registry_round_trips_and_rejects_an_unknown_name():
    portal.register("unit_test_adapter", lambda *a, **k: [])
    assert portal.get_adapter("unit_test_adapter") is not None
    assert portal.get_adapter("no_such_adapter") is None
