"""Portal lanes run before web search, and reordering them changed no result.

Web search used to run first. That was right when it was the only lane most economies had;
since Phase 2 it is a fallback, and since every engine began answering 403/202 it is usually a
fallback that returns nothing — so it was spending 20-90s per run proving that before the lane
that works was asked at all (measured on live SG pillar-7 runs, 2026-09-14).

The reorder is only safe if PRECEDENCE is unchanged, so that is what these pin: a document
both lanes find must still come back with the portal's metadata, and a document only web
search finds must still be kept.
"""
from __future__ import annotations

import pytest

from backend.pipeline import discovery
from backend.schemas import DiscoveredDoc, DocFormat, Economy


def _doc(url: str, title: str, score: float) -> DiscoveredDoc:
    return DiscoveredDoc(
        doc_id=discovery._doc_id("SG", url), economy=Economy.SG, title=title,
        source_url=url, fmt=DocFormat.HTML, discovery_tag="NEW", relevance_score=score,
        portal="sso.agc.gov.sg")


SHARED = "https://sso.agc.gov.sg/Act/PDPA2012"
WEB_ONLY = "https://sso.agc.gov.sg/Act/FOUND-BY-SEARCH-ONLY"


@pytest.fixture
def _two_lanes(monkeypatch):
    """One web-search source and one portal source, both returning the shared document."""
    order: list[str] = []

    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "SG", "adapter": "websearch", "name": "web", "site": "sso.agc.gov.sg"},
        {"economy": "SG", "adapter": "sg_sso", "name": "portal",
         "search_url_template": "https://sso.agc.gov.sg/{q}"},
    ])

    def fake_websearch(*a, **kw):
        order.append("websearch")
        # web-search documents carry score 0 by design — they are ranked later, by content
        return [_doc(SHARED, "pdpa2012 - Singapore Statutes Online", 0.0),
                _doc(WEB_ONLY, "Something only search found", 0.0)]

    monkeypatch.setattr(discovery, "discover_websearch", fake_websearch)

    def fake_portal(client, src, query, economy, indicators, log=None):
        order.append("portal")
        return [_doc(SHARED, "Personal Data Protection Act 2012", 0.9035)]

    from backend.pipeline import portal
    monkeypatch.setattr(portal, "get_adapter", lambda name: fake_portal)
    monkeypatch.setattr(portal, "enumerates_portal", lambda name: True)
    return order


def test_portal_lane_runs_before_web_search(_two_lanes):
    discovery.discover_live(Economy.SG, pillar=7, max_docs=10, log=lambda *_: None)
    assert _two_lanes == ["portal", "websearch"], (
        "the portal lane must be asked first; web search is the fallback")


def test_the_portal_metadata_wins_for_a_document_both_lanes_find(_two_lanes):
    """Precedence unchanged: the portal's real title and score, not the search snippet's."""
    docs = discovery.discover_live(Economy.SG, pillar=7, max_docs=10, log=lambda *_: None)
    shared = [d for d in docs if d.source_url == SHARED]
    assert shared, "the shared document must survive"
    assert shared[0].title == "Personal Data Protection Act 2012"
    assert shared[0].relevance_score == pytest.approx(0.9035)


def test_a_document_only_web_search_finds_is_still_kept(_two_lanes):
    """Running the fallback last must not turn it into a lane whose results are discarded."""
    docs = discovery.discover_live(Economy.SG, pillar=7, max_docs=10, log=lambda *_: None)
    assert any(d.source_url == WEB_ONLY for d in docs)
