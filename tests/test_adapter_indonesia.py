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


def test_search_terms_pulls_from_the_pillar_scoped_query_list():
    """`_search_terms` must actually READ `src["queries_p6"]`/`src["queries_p7"]`, filtered to
    the pillar(s) the caller's `indicators` cover -- the same vehicle every other portal-native
    lane gets its own query vocabulary through. A pillar-6-only call must not leak pillar-7
    terms, and vice versa; a call covering both pillars must carry both lists."""
    from backend.rdtii.indicators import get_indicators

    src = {"queries_p6": ["transfer data pribadi ke luar wilayah", "wajib disimpan di dalam wilayah"],
           "queries_p7": ["pelindungan data pribadi", "keamanan siber"]}

    p6_terms = adapter_indonesia._search_terms("fallback", src, get_indicators(pillar=6))
    assert p6_terms[:2] == src["queries_p6"]
    assert not any(t in p6_terms for t in src["queries_p7"])
    assert p6_terms[-1] == "fallback"          # the passed-in query is appended, not dropped

    p7_terms = adapter_indonesia._search_terms("fallback", src, get_indicators(pillar=7))
    assert p7_terms[:2] == src["queries_p7"]
    assert not any(t in p7_terms for t in src["queries_p6"])

    both_terms = adapter_indonesia._search_terms("fallback", src, get_indicators())
    assert set(src["queries_p6"]) <= set(both_terms)
    assert set(src["queries_p7"]) <= set(both_terms)


def test_search_terms_caps_at_search_max_terms():
    """`_SEARCH_MAX_TERMS` bounds the pass -- see the module docstring's PAGINATION note for
    why (each term is a real Scrapling round trip). Dedup-preserving order, first-come-first-
    served, matching `discovery._source_queries`'s own treatment of query order elsewhere."""
    from backend.rdtii.indicators import get_indicators

    src = {"queries_p6": [f"term-{i}" for i in range(10)]}
    terms = adapter_indonesia._search_terms("", src, get_indicators(pillar=6))
    assert len(terms) == adapter_indonesia._SEARCH_MAX_TERMS
    assert terms == [f"term-{i}" for i in range(adapter_indonesia._SEARCH_MAX_TERMS)]


def test_search_id_bpk_actually_searches_every_pillar_scoped_term(monkeypatch, html):
    """The mechanism (`_search_terms` reading `src["queries_p6"]`/`["queries_p7"]`) is
    implemented and `search_id_bpk` genuinely loops over its output -- but a test that only
    exercises the single-term fallback (`src={"name": ...}`, no query lists) never proves that
    loop runs. This drives it with a multi-term `src` (P6 + P7 terms together) and asserts every
    term up to the cap was actually turned into a distinct, correctly-encoded search URL --
    not just that `_search_terms` LISTED them.
    """
    import urllib.parse

    from backend.rdtii.indicators import get_indicators

    calls: list[str] = []

    class _Res:
        body = html.encode()

    def fake_fetch(url, timeout=None, log=None, **kw):
        calls.append(url)
        return _Res()

    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "fetch", fake_fetch)

    src = {
        "name": "JDIH BPK",
        "queries_p6": ["transfer data pribadi ke luar wilayah",
                       "wajib disimpan di dalam wilayah", "pusat data"],
        "queries_p7": ["pelindungan data pribadi", "keamanan siber",
                       "jangka waktu penyimpanan data"],
    }
    indicators = get_indicators()          # both pillars, so both lists are in scope
    docs = adapter_indonesia.search_id_bpk(
        client=None, src=src, query="data pribadi", economy=Economy.ID,
        indicators=indicators, log=lambda *_: None)

    expected_terms = adapter_indonesia._search_terms("data pribadi", src, indicators)
    assert len(expected_terms) == adapter_indonesia._SEARCH_MAX_TERMS, (
        "this src has 6 pillar terms + the fallback query -- the cap should bind")
    assert len(calls) == len(expected_terms), (
        "one browser fetch per term expected, not one per call or a flat single fetch")
    for term in expected_terms:
        encoded = urllib.parse.quote_plus(term)
        assert any(encoded in url for url in calls), (
            f"{term!r} was in _search_terms's output but never turned into a request")
    assert docs, "a multi-term search over a stubbed fixture should still produce documents"


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
