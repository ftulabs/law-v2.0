"""China: both lanes were a web search, and every engine now answers 403.

cac.gov.cn is server-rendered and enumerable -- 200, 59,987 bytes, 356 links, not a JS shell
(probed 2026-09-07). Having two real portal lanes also closes the standing item that CN's
principal statutes (PIPL, CSL, DSL) must survive cac.gov.cn being unreachable.

flk.npc.gov.cn is deliberately NOT a lane: its API's permission block returns "download": 0,
which is the operator saying the documents are not to be downloaded.

Fixture saved 2026-09-07 from https://www.cac.gov.cn/. No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_china
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "cn_cac_index.html"
SEARCH_FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "cn_cac_search.html"
BASE = "https://www.cac.gov.cn/"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def search_html():
    return SEARCH_FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_article_links_are_found(html):
    rows = adapter_china._article_links(html, BASE)
    assert len(rows) >= 40, f"only {len(rows)} article links parsed from the front page"


def test_protocol_relative_hrefs_are_resolved(html):
    """cac.gov.cn writes //www.cac.gov.cn/... A parser that leaves those alone produces URLs
    that cannot be fetched, and the economy silently yields nothing."""
    rows = adapter_china._article_links(html, BASE)
    assert all(u.startswith("https://") for u, _ in rows)
    assert not any(u.startswith("//") for u, _ in rows)


def test_only_article_pages_are_kept(html):
    """Section indexes (A<N>index_<N>.htm) are navigation, not instruments."""
    rows = adapter_china._article_links(html, BASE)
    assert all("/c_" in u for u, _ in rows)
    assert not any("index_" in u for u, _ in rows)


def test_rows_are_deduplicated(html):
    rows = adapter_china._article_links(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_titles_carry_chinese_text(html):
    rows = adapter_china._article_links(html, BASE)
    chinese = [t for _, t in rows if any("一" <= ch <= "鿿" for ch in t)]
    assert chinese, "no article title contained a Chinese character"


def test_shipped_source_entry_fetches_cac_gov_cn_not_gov_cn(html, monkeypatch):
    """Finding 2, 2026-09-07 final review: `data/sources.yaml`'s `cn_portal` entry carried
    `base_url: https://www.gov.cn`, left over from when this entry was `adapter: websearch`.
    `search_cn_portals` reads `cac_base = src.get("base_url") or _CAC_BASE` as its cac.gov.cn
    "front" host, so production was fetching www.gov.cn there while every measured
    byte/link/article-URL count in this module's own docstring (dated 2026-09-07/08) describes
    www.cac.gov.cn -- a different host.

    No fixture-driven test in this file caught it: every other test here passes a bare
    `src={"name": ...}` dict with no `base_url`, which always falls through to the correct
    `_CAC_BASE` default and never exercises the shipped value. This test reads the REAL
    `data/sources.yaml` entry instead -- a local file, not the network.
    """
    from backend.pipeline import discovery

    cn_sources = [s for s in discovery.load_sources()
                  if s.get("economy") == "CN" and s.get("adapter") == "cn_portal"]
    assert cn_sources, "data/sources.yaml must still carry a cn_portal entry for CN"
    src = cn_sources[0]

    fetched_urls: list[str] = []

    def _portal_get(client, url, log):
        fetched_urls.append(url)

        class _R:
            status_code = 200
            text = html

        return _R()

    monkeypatch.setattr(adapter_china.portal, "portal_get", _portal_get)
    adapter_china.search_cn_portals(
        client=None, src=src, query="", economy=Economy.CN, indicators=[],
        log=lambda *_: None)

    assert fetched_urls, "search_cn_portals made no portal_get calls at all"
    front_url = fetched_urls[0]
    assert front_url.startswith("https://www.cac.gov.cn"), (
        f"shipped cn_portal base_url produced a front-page fetch against {front_url!r}, not "
        "cac.gov.cn -- every measured count in adapter_china.py's own docstring is against "
        "cac.gov.cn, not gov.cn")


def test_the_npc_database_is_not_a_fetch_target():
    """flk.npc.gov.cn's API returns "download": 0 -- the operator refusing. That decision
    stands, and this test is what stops a future edit quietly reversing it.

    The check is narrow on purpose: the host may be NAMED in a comment (explaining why it is
    excluded is worth more than silence), but it must never appear in a string the adapter
    could fetch. So: no line that both mentions the host and looks like a URL.
    """
    import inspect
    for line in inspect.getsource(adapter_china).splitlines():
        if "flk.npc.gov.cn" not in line:
            continue
        stripped = line.strip()
        assert stripped.startswith("#") or stripped.startswith("*") or '"""' in stripped or (
            "http" not in line), (
            f"flk.npc.gov.cn appears in a fetchable string, not a comment: {stripped[:90]}")


def test_search_produces_unique_documents(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_china.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_china.search_cn_portals(
        client=None, src={"name": "Cyberspace Administration"}, query="",
        economy=Economy.CN, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.CN for d in docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("cn_portal") is not None


def test_article_links_parses_the_search_results_page_too(search_html):
    """The search pass (`_search_pass`, added fix round 1) reuses `_article_links` for the SAME
    /c_<id>.htm row shape `search.cac.gov.cn` returns. Fixture captured live 2026-09-08 from a
    real `sort=0` query for PIPL's own title, cleared through the Scrapling browser lane --
    search.cac.gov.cn is Jiasule-WAF-gated and plain httpx/curl could not reach it directly.
    """
    rows = adapter_china._article_links(search_html, BASE)
    titles = [t for _, t in rows]
    # Not an exact match: the search page wraps matched query terms in <font color=red>, which
    # BeautifulSoup's get_text(" ", ...) renders as a space at that text-node boundary (measured:
    # "中华人民共和国 个人信息保护法", not "中华人民共和国个人信息保护法"). The leading "» " bullet
    # IS stripped by `_article_links` (see its own comment) -- this checks the substring that
    # matters for `_relevance`'s topic-fit scoring, not byte-for-byte equality with the statute's
    # own name.
    assert any("个人信息保护法" in t for t in titles), (
        "PIPL's own title did not survive parsing the saved search-result fixture")
    assert not any(t.startswith("»") for t in titles), "decorative bullet prefix was not stripped"


def test_search_pass_adds_documents_when_scrapling_is_available(monkeypatch, search_html):
    """No network: `portal.portal_get` is stubbed to return None (isolating the search pass from
    the front/section pass), `scrapling_fetch.fetch` is stubbed to return the saved fixture, and
    `robots.allowed` is stubbed so no real robots.txt fetch happens either. This exercises the
    actual wiring -- `_search_terms` -> `_search_pass` -> `_article_links` -> `portal.make_doc`
    -- without ever touching search.cac.gov.cn."""
    class _SR:
        status = 200
        body = search_html.encode()
        content_type = "text/html;charset=UTF-8"
        engine = "scrapling-fetcher"

    monkeypatch.setattr(adapter_china.portal, "portal_get", lambda *a, **k: None)
    monkeypatch.setattr(adapter_china.scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(adapter_china.scrapling_fetch, "fetch", lambda *a, **k: _SR())
    monkeypatch.setattr(adapter_china.robots, "allowed", lambda *a, **k: (True, ""))

    docs = adapter_china.search_cn_portals(
        client=None, src={"name": "Cyberspace Administration"},
        query="中华人民共和国个人信息保护法", economy=Economy.CN, indicators=[],
        log=lambda *_: None)
    assert docs, "search pass produced no documents even with scrapling_fetch stubbed to succeed"
    assert any("个人信息保护法" in d.title for d in docs)


def test_documents_get_a_real_relevance_score_not_a_flat_one():
    """`discovery.py` sorts by `relevance_score` and `discovery._cap` trims to
    `discovery_max_docs`; a flat score (every adapter used to default to 1.0) makes that trim
    arbitrary. This asserts STRICT inequality between two rows so a flat implementation fails
    here rather than merely passing a `<= 1.0` check that a constant would also satisfy.

    The two titles are real phrasing from `query_terms_i18n.NATIVE_QUERY_TERMS["zh"]` (quoted
    PIPL/CSL article language) versus a generic, off-topic news headline, from the section most
    directly on-topic for P6 (cross-border data-export security) versus the generic front page.
    """
    on_topic = adapter_china._relevance(
        "data_export_security", "国家互联网信息办公室关于《数据出境安全评估办法》的通知", [])
    off_topic = adapter_china._relevance(
        "front", "中央网信办举办职工趣味运动会", [])
    assert on_topic > off_topic
