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
    """The list page carries 141 `agencies_id=` and 36 `legaltype=` links — browse filters,
    not instruments. A parser that keeps them fills the document budget with navigation."""
    rows = adapter_laos._detail_ids(html, BASE)
    assert not any("agencies_id" in u or "legaltype" in u for u, _ in rows)


def test_pdf_links_are_absolute_and_under_the_upload_path(html):
    pdfs = adapter_laos._pdf_links(html, BASE)
    assert all(p.startswith("https://laoofficialgazette.gov.la/") for p in pdfs)
    assert all(".pdf" in p.lower() for p in pdfs)
    assert all("/kcfinder/upload/files/" in p for p in pdfs), (
        "PDFs must resolve under the portal's own upload path, not just be some absolute "
        "URL ending in .pdf on the host")


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


# ── fix round 1, Finding 1 — nothing locked in relevance-score diversity ──────────────────
#
# `discovery.py` sorts by `relevance_score` and `discovery._cap` trims to
# `settings.discovery_max_docs` (22). A flat score makes that trim arbitrary rather than
# relevance-driven, and the run still completes and still exports a CSV — nothing raises. Each
# test below asserts STRICT inequality, so a regression to a flat default fails it.

def test_scores_differ_by_category(html):
    """The highest- and lowest-weighted instrument types in `_CATEGORY_WEIGHT` must not score
    the same. Category strings are taken from the dict's own keys, not retyped by hand — Lao
    "ຳ" can be one precomposed codepoint or two decomposed ones, and a retyped string that
    LOOKS identical but isn't would silently miss the dict and fall back to the default,
    making this test pass for the wrong reason."""
    weights = adapter_laos._CATEGORY_WEIGHT
    high_cat = max(weights, key=weights.get)
    low_cat = min(weights, key=weights.get)
    high = adapter_laos._relevance(high_cat, "Some title", "01-01-2020", [])
    low = adapter_laos._relevance(low_cat, "Some other title", "01-01-2020", [])
    assert high != low
    assert high > low, f"{high_cat!r} (weight {weights[high_cat]}) should outrank " \
                        f"{low_cat!r} (weight {weights[low_cat]})"


def test_scores_differ_by_year(html):
    """Same instrument type, only the document date changes. The category string is read off
    the fixture's own first row (verified elsewhere to be "ຂໍ້ຕົກລົງ") rather than retyped, for
    the same codepoint-safety reason as the test above."""
    rows = adapter_laos._rows(html, BASE)
    category = rows[0][3]
    older = adapter_laos._relevance(category, "title", "01-01-1980", [])
    newer = adapter_laos._relevance(category, "title", "01-01-2030", [])
    assert older != newer
    assert newer > older, "recency is a small positive signal, not a negative one"


def test_scores_are_not_all_equal_across_the_fixture(html):
    """Old flat-default failure mode, exercised end-to-end against the committed fixture: every
    row on the real list page, scored the way `search_la_gazette` actually scores it, must not
    collapse to one value. The live run this fixture was saved from measured 70 distinct scores
    across 400 documents (see task-3-report.md); this fixture alone already carries 5 distinct
    instrument categories, so a flat implementation fails this immediately."""
    rows = adapter_laos._rows(html, BASE)
    scores = {adapter_laos._relevance(cat, title, date, []) for _, title, _, cat, date in rows}
    assert len(scores) > 1, f"relevance collapsed to a single value across the fixture: {scores}"
