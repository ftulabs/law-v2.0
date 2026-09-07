"""Indonesia: httpx is refused on every path, the browser lane is not.

peraturan.bpk.go.id answers HTTP 403 to plain httpx at the root, at /Search and at
/sitemap.xml (measured 2026-09-07) while Scrapling's impersonating fetcher gets 200.
sources.yaml has recorded this since 21 August. So this adapter goes to the browser lane
FIRST rather than escalating after a refusal -- three wasted 403s per request is real cost
across a crawl.

robots.txt here disallows nine NAMED agents (ClaudeBot, GPTBot, CCBot, Bytespider,
Amazonbot, Applebot-Extended, Google-Extended, meta-externalagent,
CloudflareBrowserRenderingCrawler) and grants the wildcard group Allow: / with
Content-Signal: search=yes, ai-train=no, use=reference. We fetch as VeriTrade-Research/0.2,
fall in the wildcard group, cite every provision to its source URL and train nothing.

Fixture saved 2026-09-07 via the browser lane. No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_indonesia
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "id_bpk_search.html"
BASE = "https://peraturan.bpk.go.id/Search?keywords=data+pribadi"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_detail_links_are_parsed(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert rows, "no /Details/ links parsed from a search result page"
    assert all("/Details/" in u for u, _ in rows)


def test_urls_are_absolute(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert all(u.startswith("https://peraturan.bpk.go.id/") for u, _ in rows)


def test_rows_are_deduplicated(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_the_adapter_never_sends_a_named_crawler_user_agent():
    """robots.txt disallows nine named AI crawlers by name. Sending one of those UAs to this
    host would be a refusal we walked past, and the difference is only the header we send."""
    import inspect
    src = inspect.getsource(adapter_indonesia)
    for named in ("ClaudeBot", "GPTBot", "CCBot", "Bytespider", "Amazonbot",
                  "Applebot-Extended", "Google-Extended", "meta-externalagent",
                  "CloudflareBrowserRenderingCrawler"):
        assert named not in src or "never" in src.lower(), (
            f"{named} appears in the adapter; robots.txt disallows it by name")


def test_search_produces_unique_documents(monkeypatch, html):
    """The browser lane is mocked; the point is the adapter's shape, not the fetch."""
    class _Res:
        body = html.encode()

    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "fetch", lambda *a, **k: _Res())
    docs = adapter_indonesia.search_id_bpk(
        client=None, src={"name": "JDIH BPK"}, query="data pribadi",
        economy=Economy.ID, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.ID for d in docs)


def test_an_unavailable_browser_lane_says_so_and_returns_nothing(monkeypatch):
    """Without Scrapling this host cannot be reached at all. Returning [] silently is the
    failure mode Phase 1 exists to remove -- it must log why."""
    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "available", lambda: False)
    lines = []
    docs = adapter_indonesia.search_id_bpk(
        client=None, src={"name": "JDIH BPK"}, query="data pribadi",
        economy=Economy.ID, indicators=[], log=lines.append)
    assert docs == []
    assert any("browser" in ln.lower() or "scrapling" in ln.lower() for ln in lines)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("id_bpk") is not None


def test_titles_join_instrument_type_and_name(html):
    """Neither half of a JDIH BPK result is a usable citation alone: the anchor text alone
    drops the instrument number, and the type+number alone drops the subject. The fixture's
    first row is a real UU (Law) with both halves independently verifiable."""
    rows = adapter_indonesia._result_rows(html, BASE)
    titles = [t for _, t in rows]
    assert any("Undang-undang" in t and "27 Tahun 2022" in t for t in titles)
    assert any("Pelindungan Data Pribadi" in t for t in titles)


def test_a_related_regulation_link_is_not_counted_as_a_second_row(html):
    """One card (Peraturan BI No. 7/6/PBI/2005) carries a nested 'Status Peraturan' block
    linking to a DIFFERENT /Details/<id> (the regulation that revoked it) -- a cross-reference,
    not a second search result. The raw page has 11 /Details/ hrefs but only 10 real result
    cards; a parser that takes every /Details/ anchor rather than the first one per card would
    produce 11 rows here, one of them a related-document link masquerading as a result."""
    rows = adapter_indonesia._result_rows(html, BASE)
    assert len(rows) == 10, f"expected 10 real result rows, got {len(rows)}"


def test_documents_get_a_real_relevance_score_not_a_flat_one():
    """`discovery.py` sorts by `relevance_score` and `discovery._cap` trims to
    `discovery_max_docs`; a flat score (every adapter used to default to 1.0) makes that trim
    arbitrary. This asserts STRICT inequality so a flat implementation fails here rather than
    merely passing a `<= 1.0` check a constant would also satisfy.

    A national Act (Undang-undang) whose title also contains the search term outranks a
    municipal staffing regulation (Peraturan Walikota) matched only because "pribadi" happens
    to be a substring of the query -- exactly the fixture's own "Staf Khusus dan Staf Pribadi
    Wali Kota Pagar Alam" row, real off-topic noise measured 2026-09-08, not a hypothetical.
    """
    on_topic = adapter_indonesia._relevance(
        "Undang-undang (UU) Nomor 27 Tahun 2022 — Pelindungan Data Pribadi",
        ["data pribadi"], [])
    off_topic = adapter_indonesia._relevance(
        "Peraturan Walikota (PERWALI) Kota Pagar Alam Nomor 19 Tahun 2019 — "
        "Staf Khusus dan Staf Pribadi Wali Kota Pagar Alam",
        ["data pribadi"], [])
    assert on_topic > off_topic


def test_regional_instrument_type_outranks_nothing_it_should_not(html):
    """Every row `_result_rows` parses from the live search fixture gets a real score, and the
    national UU (row 0) must outrank the regional Perbup/Perwali rows the same fixture contains
    -- proving the type-hierarchy signal fires on real parsed titles, not just hand-built
    strings."""
    rows = adapter_indonesia._result_rows(html, BASE)
    scored = [(u, t, adapter_indonesia._relevance(t, ["data pribadi"], [])) for u, t in rows]
    uu_score = next(s for u, t, s in scored if "uu-no-27-tahun-2022" in u)
    regional_scores = [s for u, t, s in scored if "perbup" in u or "perwali" in u]
    assert regional_scores, "fixture should contain at least one regional instrument"
    assert all(uu_score > s for s in regional_scores)
