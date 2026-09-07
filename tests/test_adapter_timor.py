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


# ── fix round 1: Finding 1 — six of nine categories were silently unread ──────────────────
#
# `_INDEX_PAGES` used to read three of the nine legal-instrument categories the portal
# publishes (Laws, Decree-Laws, Gov-Decrees) and reported success anyway — the run completed,
# emitted documents, and nothing said a third-plus of the corpus (Ministerial Orders,
# Instructions, Government Resolutions, Parliament Resolutions, Presidential Decree-Laws,
# Public Institution Regulations, and the Constitution) was never read. These two tests exist
# so a future edit that drops a category fails loudly instead of shipping quietly.

_EXPECTED_CATEGORIES = {
    "Law", "Decree-Law", "Gov-Decree", "Minist-Order", "Instruction",
    "Gov-Resolution", "Resolution", "Presidential-Decree-Law", "Public-Inst-Reg",
}


def test_index_pages_cover_every_category():
    got = {category for _, category in adapter_timor._INDEX_PAGES}
    assert got == _EXPECTED_CATEGORIES, f"missing: {_EXPECTED_CATEGORIES - got}"
    import collections
    counts = collections.Counter(category for _, category in adapter_timor._INDEX_PAGES)
    assert all(n == 2 for n in counts.values()), \
        f"every category needs an EN entry and a PT twin: {counts}"


def test_the_fourteen_previously_missing_pages_are_present():
    """The exact fourteen URLs the review named as missing (twelve index pages plus the two
    direct Constitution PDFs), matched as substrings so URL-encoding quirks in the assertion
    itself can't hide a real gap."""
    urls = ({u for u, _ in adapter_timor._INDEX_PAGES}
            | {u for u, _, _ in adapter_timor._DIRECT_PDFS})
    must_contain = [
        "RDTL-Constitution.pdf", "RDTL-Constitution-P.pdf",
        "RDTL-Minist-Orders/RDTL-Oreders.htm", "RDTL-Minist-Orders-P/RDTL-Oreders.htm",
        "RDTL-Instructions/RDTL-Instr.htm", "RDTL-Instructions-P/RDTL-Instr.htm",
        "RDTL-Gov-Resolutions/RDTL-Gov-Resolutions.htm",
        "RDTL-Gov-Resolutions-P/RDTL-Gov-Resolutions.htm",
        "RDTL-Resolutions/RDTL-Resolutions.htm",
        "RDTL-Resolutions-P/RDTL-Resolutions-P.htm",
        "Presidential-Decree-Laws/Presidential-Decree-Laws.htm",
        "Presidential-Decree-Laws-P/Presidential%20DecreeLaws-.htm",
        "Public%20Inst-Regs/Public%20Inst-Regs.htm",
        "Public%20Inst-Regs-P/Public%20Inst-Regs.htm",
    ]
    assert len(must_contain) == 14
    for fragment in must_contain:
        assert any(fragment in u for u in urls), f"missing page: {fragment}"


# ── fix round 1: Finding 2 — every document scored the flat default 1.0 ───────────────────

def test_scores_differ_by_category():
    """Old implementation: every call returns the flat default 1.0 regardless of arguments —
    this fails against it."""
    law = adapter_timor._relevance("Law", "https://mj.gov.tl/x/Law-2010-01.pdf", "Some Act", [])
    resolution = adapter_timor._relevance(
        "Resolution", "https://mj.gov.tl/x/Res-2010-01.pdf", "Some Resolution", [])
    assert law != resolution
    assert law > resolution, "Laws are a primary legislative vehicle; Resolutions are not"


def test_scores_differ_by_year():
    older = adapter_timor._relevance(
        "Law", "https://mj.gov.tl/x/Law-2002-01.pdf", "Publication of Acts", [])
    newer = adapter_timor._relevance(
        "Law", "https://mj.gov.tl/x/Law-2012-01.pdf", "Publication of Acts", [])
    assert older != newer
    assert newer > older, "recency is a small positive signal, not a negative one"


def test_scores_are_never_the_old_flat_default():
    for category in _EXPECTED_CATEGORIES:
        score = adapter_timor._relevance(category, "https://mj.gov.tl/x/doc.pdf", "A Title", [])
        assert score != 1.0, f"{category} still scores the flat default"


# ── fix round 1: parser coverage for the Portuguese path ──────────────────────────────────
#
# Only the English "Laws" fixture was covered by the original test suite; the "-P" twin pages
# were checked live during recon but that recon was never committed, so a regression in
# Portuguese parsing (or in `_decode`'s charset handling, added in this same fix round) had no
# test to catch it.

FIXTURE_PT = Path(__file__).parent / "fixtures" / "portals" / "tl_rdtl_laws_p.htm"
BASE_PT = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws-P/RDTL-Laws.htm"


def test_the_portuguese_index_also_parses():
    """Saved 2026-09-08 from https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws-P/RDTL-Laws.htm
    RECON: 131 PDFs (the Portuguese "Laws" index is LARGER than the English one, 127)."""
    html = FIXTURE_PT.read_text(encoding="utf-8", errors="replace")
    rows = adapter_timor._law_rows(html, BASE_PT)
    assert len(rows) >= 125, f"expected ~131 PDFs, got {len(rows)}"
    assert all(u.startswith("https://mj.gov.tl/") and u.lower().endswith(".pdf")
               for u, _ in rows)
    assert len({u for u, _ in rows}) == len(rows)


def test_decode_repairs_the_unhonoured_meta_charset():
    """httpx decodes this portal's pages as UTF-8 by default because the charset is declared
    only in a <meta> tag, not the HTTP header — invisible on the English pages (ASCII body),
    but it corrupts every accented character on the Portuguese ones. Found while adding the
    fixture above: 'ção' round-tripped through the naive `.text` path came out as replacement
    characters. `_decode` reads the declared charset from the raw bytes instead."""
    raw = FIXTURE_PT.read_bytes()

    class _R:
        content = raw

        @property
        def text(self):
            return raw.decode("utf-8", errors="replace")

    decoded = adapter_timor._decode(_R())
    assert "ção" in decoded or "ção".encode("utf-8").decode("utf-8") in decoded
