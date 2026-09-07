"""Laos: recorded as "host does not resolve" and "the weakest coverage of the nine".

Both were false. Probed 2026-09-07 the host answers HTTP 200 with 110 KB and 12,477 Lao
characters, and is a Yii application with a fully paginated document list. It is one of the
most tractable portals of the eleven.

Fixture saved 2026-09-07 from
https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page=1
No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_laos
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "la_list_page1.html"
BASE = "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page=1"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_detail_ids_are_found_on_the_list_page(html):
    """Ids come from the list page and nowhere else: a guessed id=1 returns HTTP 404
    (verified 2026-09-07), so an adapter that walks a numeric range finds nothing."""
    rows = adapter_laos._detail_ids(html, BASE)
    assert len(rows) >= 10, f"only {len(rows)} detail links parsed from the list page"
    assert all("r=site/display" in u for u, _ in rows)


def test_detail_urls_are_absolute(html):
    rows = adapter_laos._detail_ids(html, BASE)
    assert all(u.startswith("https://laoofficialgazette.gov.la/") for u, _ in rows)


def test_agency_and_type_links_are_not_mistaken_for_documents(html):
    """The list page carries 94 `agencies_id=` and 24 `legaltype=` links — browse filters,
    not instruments. A parser that keeps them fills the document budget with navigation."""
    rows = adapter_laos._detail_ids(html, BASE)
    assert not any("agencies_id" in u or "legaltype" in u for u, _ in rows)


def test_pdf_links_are_absolute_and_under_the_upload_path(html):
    pdfs = adapter_laos._pdf_links(html, BASE)
    assert all(p.startswith("https://laoofficialgazette.gov.la/") for p in pdfs)
    assert all(".pdf" in p.lower() for p in pdfs)


def test_rows_are_deduplicated(html):
    rows = adapter_laos._detail_ids(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_search_returns_docs_from_the_list_page(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_laos.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_laos.search_la_gazette(
        client=None, src={"name": "Lao Official Gazette"}, query="",
        economy=Economy.LA, indicators=[], log=lambda *_: None)
    assert docs
    assert all(d.economy == Economy.LA for d in docs)
    assert len({d.doc_id for d in docs}) == len(docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("la_gazette") is not None
