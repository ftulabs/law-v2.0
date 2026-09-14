"""A bot-check interstitial must never be read as a portal's answer.

Found live 2026-09-14: `sso.agc.gov.sg` sits behind AWS WAF and answers a burst with HTTP 202
and 2,432 bytes of challenge JavaScript. `portal_get`'s rule at the time — "202 with an empty
body is a throttle, 202 WITH content is a real response" — was written in August against the
empty-body shape and passed the challenge straight through to the adapter, which parsed it,
found no Acts, and returned a third of the corpus without a word in the log.

The body below is the real one, trimmed.
"""
from __future__ import annotations

import pytest

from backend.pipeline import portal

# Verbatim from the live 202 (keys truncated — the MARKERS are what matters).
AWS_WAF_202 = (
    '<html><head><style>body { font-family: "Arial"; }</style></head><body>'
    '<script>window.awsWafCookieDomainList = [];'
    'window.gokuProps = {"key":"AQIDAHjcYu_TRUNCATED","iv":"NC4kbQHEFQAAzq9f",'
    '"context":"XG9qtbBpzFQ1JEd5_TRUNCATED"};</script>'
    '<script src="https://de5282c3ca0c.edge.sdk.awswaf.com/challenge.js"></script>'
    '</body></html>'
)

REAL_PAGE = (
    '<html><body><table class="browse-list">'
    '<tr><td><a href="/Act/PDPA2012">Personal Data Protection Act 2012</a></td></tr>'
    '</table></body></html>'
)


class _Resp:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text
        self.content = text.encode()


class _Client:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


@pytest.fixture(autouse=True)
def _no_robots_no_sleep(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(portal.time, "sleep", lambda *_: None)


def test_aws_waf_challenge_is_a_throttle_not_a_result():
    """The exact shape that cost Singapore 15 of its 22 documents."""
    client = _Client(_Resp(202, AWS_WAF_202))
    lines: list[str] = []
    assert portal.portal_get(client, "https://sso.agc.gov.sg/Browse/Act/Current/All",
                             log=lines.append, tries=2) is None
    assert client.calls == 2, "a challenge must be retried, not accepted"
    assert any("BOT CHALLENGE" in l for l in lines), "the throttle must be reported"
    assert any("INCOMPLETE" in l for l in lines), "giving up must say coverage is incomplete"


def test_a_challenge_behind_http_200_is_also_refused():
    """Not every WAF uses 202; the body is the evidence, not the status code."""
    client = _Client(_Resp(200, AWS_WAF_202))
    assert portal.portal_get(client, "https://example.gov/x", log=lambda *_: None,
                             tries=1) is None


def test_a_real_page_still_comes_straight_back():
    """The guard must not cost a healthy portal anything."""
    client = _Client(_Resp(200, REAL_PAGE))
    r = portal.portal_get(client, "https://sso.agc.gov.sg/Browse/Act/Current/All",
                          log=lambda *_: None)
    assert r is not None and "Personal Data Protection Act" in r.text
    assert client.calls == 1


def test_a_202_with_a_real_body_is_still_a_result():
    """SSO's legitimate 202-with-content path must keep working — that was the 2026-08 fix."""
    client = _Client(_Resp(202, REAL_PAGE))
    r = portal.portal_get(client, "https://sso.agc.gov.sg/x", log=lambda *_: None)
    assert r is not None and "Personal Data Protection Act" in r.text


def test_recovers_when_the_challenge_clears():
    """A throttle that lifts mid-retry yields the real page, not None."""
    client = _Client(_Resp(202, AWS_WAF_202), _Resp(200, REAL_PAGE))
    r = portal.portal_get(client, "https://sso.agc.gov.sg/x", log=lambda *_: None, tries=3)
    assert r is not None and "Personal Data Protection Act" in r.text
    assert client.calls == 2


@pytest.mark.parametrize("marker", [
    "window.awsWafCookieDomainList = []",
    "cdn-cgi/challenge-platform/h/b/orchestrate",
    "_Incapsula_Resource?SWJIYLWA=",
])
def test_known_vendor_markers_are_recognised(marker):
    assert portal.looks_like_a_challenge(f"<html><body><script>{marker}</script></body></html>")


def test_ordinary_law_text_is_not_mistaken_for_a_challenge():
    """The guard must not fire on a statute that happens to mention scripts or cookies."""
    assert not portal.looks_like_a_challenge(
        "<html><body><h1>Computer Misuse Act</h1><p>Unauthorised access to computer "
        "material, including any cookie, script or challenge-response mechanism.</p></body></html>")
