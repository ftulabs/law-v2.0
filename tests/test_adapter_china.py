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
BASE = "https://www.cac.gov.cn/"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


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
