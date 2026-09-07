"""Singapore's only discovery lane was a web search, and every engine now answers 403.

SG is mandatory in every round of this hackathon. On 2026-09-07 its runs were not discovering
anything — they were replaying an eight-day-old search cache, which the Phase-1 TTL now
correctly refuses to serve. Without a portal lane, SG produces zero documents.

The technique is inherited, not invented: SSO IGNORES CurrentPage (verified 2026-08-01 —
pages 1, 2 and 3 return byte-identical HTML at every PageSize), so the index is enumerated by
sort-window union. Two sort keys x two directions.

Fixture saved 2026-09-07 from
https://sso.agc.gov.sg/Browse/Act/Current/All?PageSize=500&SortBy=Title&SortOrder=ASC
No test here touches the network.

The saved fixture is TRUNCATED to its first 150 of 500 rows (fix round 1, 2026-09-08) — see
the comment at the top of tests/fixtures/portals/sg_browse_act.html for the full-file byte
count and the exact cut point. 150 rows comfortably clears the >=100 assertion below while
keeping this fixture from being 74% of the repository's portal-fixture download size.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_singapore
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "sg_browse_act.html"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_browse_rows_are_parsed(html):
    rows = adapter_singapore._browse_rows(html)
    assert len(rows) >= 100, f"only {len(rows)} rows parsed from a PageSize=500 window"


def test_rows_carry_a_path_and_a_title(html):
    rows = adapter_singapore._browse_rows(html)
    assert all(p.startswith("/") for p, _ in rows)
    assert all(t.strip() for _, t in rows)


def test_titles_are_html_unescaped(html):
    """SSO writes &amp; and &#39; in Act titles. A Law Name column reading
    "Companies (Amendment &amp; Consequential) Act" is a wrong citation, not a cosmetic bug.

    This is a smoke test only: not one of the 500 rows in the committed fixture window
    actually contains an entity, so this passes whether or not `_clean_title` unescapes
    anything. `test_clean_title_decodes_html_entities` below is the test that can fail.
    """
    rows = adapter_singapore._browse_rows(html)
    assert not any("&amp;" in t or "&#" in t for _, t in rows)


def test_clean_title_decodes_html_entities():
    """The test that can actually fail against a missing `html.unescape` call. SSO writes
    entities in some titles (e.g. "Companies (Amendment &amp; Consequential) Act") even though
    none happen to land in the committed fixture window — a Law Name column that still reads
    "&amp;" is a wrong citation, not a cosmetic bug."""
    assert adapter_singapore._clean_title("Companies (Amendment &amp; Consequential) Act") == (
        "Companies (Amendment & Consequential) Act")
    assert adapter_singapore._clean_title("What&#39;s New Act") == "What's New Act"
    assert adapter_singapore._clean_title("A  &amp;   B") == "A & B"  # also collapses whitespace


def test_the_body_url_is_the_pdf_view(html):
    """SSO serves the whole instrument at ?ViewType=Pdf (verified). The landing page is the
    citable URL; the PDF is what gets fetched."""
    rows = adapter_singapore._browse_rows(html)
    path = rows[0][0]
    assert adapter_singapore._body_url(path).endswith("?ViewType=Pdf")
    assert adapter_singapore._body_url(path).startswith("https://sso.agc.gov.sg/")


def test_search_produces_unique_documents(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_singapore.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_singapore.search_sg_sso(
        client=None, src={"name": "Singapore Statutes Online"}, query="",
        economy=Economy.SG, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.SG for d in docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("sg_sso") is not None


def test_the_corpus_catalogue_imports_the_enumerator_from_the_pipeline():
    """The dependency is REVERSED, not relaxed. The live pipeline still imports nothing from
    backend.corpus (tests/test_pipeline_isolation.py pins that); corpus imports from the
    pipeline. An enumerator is live HTTP, not a stored corpus."""
    import inspect

    from backend.corpus import catalogue
    src = inspect.getsource(catalogue)
    assert "adapter_singapore" in src, (
        "catalogue.py must import the SSO enumeration from the pipeline, not keep its own")


def test_the_shared_enumerator_still_returns_corpus_shaped_rows(monkeypatch, html):
    """catalogue.py consumes these dicts. A DiscoveredDoc here would break the corpus tool,
    and the two id schemes are deliberately different: a corpus row and a discovered document
    are not the same thing."""
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_singapore.portal, "portal_get", lambda *a, **k: _R())
    rows = adapter_singapore.enumerate_sso(client=None, log=lambda *_: None)
    assert rows and isinstance(rows[0], dict)
    for key in ("economy", "portal", "title", "source_url", "body_url", "collection", "status"):
        assert key in rows[0], f"corpus row is missing {key!r}"


def test_relevance_score_discriminates_by_title():
    """`discovery._cap` sorts by relevance_score and trims to `discovery_max_docs` (22 by
    default). A flat score makes the surviving 22-of-524 Acts arbitrary for a mandatory
    economy. This would fail against a flat `score=1.0` implementation."""
    from backend.rdtii.indicators import INDICATORS

    relevant = adapter_singapore._relevance(
        "act", "Personal Data Protection Act 2012", INDICATORS)
    irrelevant = adapter_singapore._relevance(
        "act", "Air Navigation Act 1966", INDICATORS)
    assert relevant > irrelevant
