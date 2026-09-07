"""Timor-Leste: a 1990s static frameset, and the easiest portal of the eleven.

TL is on the panel's published list and carries the difficulty bonus, and until this adapter
it had no lane at all — every document had to come through a web search that was returning
HTTP 403 from every engine.

Fixture saved 2026-09-07 from
https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws/RDTL-Laws.htm
No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_timor
from backend.schemas import DocFormat, Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "tl_rdtl_laws.htm"
BASE = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws/RDTL-Laws.htm"


@pytest.fixture(scope="module")
def rows():
    return adapter_timor._law_rows(FIXTURE.read_text(encoding="utf-8", errors="replace"), BASE)


def test_the_index_yields_every_pdf_it_lists(rows):
    assert len(rows) >= 120, "RECON: the saved index listed 127 PDFs on 2026-09-07"


def test_every_url_is_absolute_and_on_the_ministry_host(rows):
    """The index uses relative hrefs (`Law-2002-01.pdf`), so a naive parser yields URLs that
    cannot be fetched and the whole economy silently produces nothing."""
    assert all(u.startswith("https://mj.gov.tl/") for u, _ in rows)
    assert all(u.lower().endswith(".pdf") for u, _ in rows)


def test_titles_are_not_just_the_filename(rows):
    """A citation reading "Law-2002-01.pdf" is not a Law Name. The index's anchor text
    carries the instrument's real title; keep it."""
    titled = [t for _, t in rows if t and not t.lower().endswith(".pdf")]
    assert len(titled) >= len(rows) // 2


def test_rows_are_deduplicated(rows):
    assert len({u for u, _ in rows}) == len(rows)


def test_the_index_covers_more_than_one_year(rows):
    """RECON: record the real span. A lane that stops in 2011 is a finding to report, not to
    hide — home-e.htm advertises an index "as of 31 August 2011"."""
    import re
    years = {m.group(1) for u, _ in rows for m in [re.search(r"Law-(\d{4})-", u)] if m}
    assert len(years) > 1, f"only these years present: {sorted(years)}"


def test_search_returns_discovered_docs_with_pdf_format(monkeypatch):
    """The adapter's public shape: the same signature discovery dispatches on."""
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")

    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_timor.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_timor.search_tl_gazette(
        client=None, src={"name": "Jornal da República"}, query="",
        economy=Economy.TL, indicators=[], log=lambda *_: None)
    assert docs, "the adapter returned nothing from a page with 127 PDFs"
    assert all(d.fmt == DocFormat.PDF_TEXT for d in docs)
    assert all(d.economy == Economy.TL for d in docs)
    assert len({d.doc_id for d in docs}) == len(docs), "doc_ids must be unique"


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("tl_gazette") is not None
