"""Provision extraction: component coverage, font-marked AU headings, label normalization,
and noise filtering. Pins the fixes for the AU §76/§76A/§77 lumping and APP-8 isolation.
"""
from backend.pipeline.extraction import (
    HEADING_MARK, _normalise_label, extract_provisions,
)
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, OCRMetrics


def _doc():
    return DiscoveredDoc(doc_id="d", economy=Economy.AU, title="Test Act 2020",
                         source_url="u", portal="p", fmt=DocFormat.PDF_TEXT,
                         discovery_tag=DiscoveryTag.NEW)


def _labels(text):
    return [p.article_section for p in extract_provisions(_doc(), text, OCRMetrics())]


# ─────────────────────── label normalization ───────────────────────
def test_normalise_label_cases():
    assert _normalise_label("section 101") == "Section 101"
    assert _normalise_label("Section 12b)") == "Section 12B"      # uppercase suffix, drop bracket
    assert _normalise_label("APP 1.2") == "APP 1"                  # collapse APP sub-paragraph
    assert _normalise_label("Schedule 3)") == "Schedule 3"         # drop dangling bracket
    assert _normalise_label("sec. 26") == "Section 26"
    assert _normalise_label("Australian Privacy Principle 8") == "APP 8"
    assert _normalise_label("77", marked=True) == "Section 77"
    assert _normalise_label("5. ") == "Section 5"                  # bare number → Section


# ─────────────────── font-marked AU headings (the §77 bug) ───────────────────
def test_font_marked_headings_split_consecutive_sections():
    """The reported bug: AU prints "77 Requirement…" with no keyword/period, so §76/76A/77
    merged. With the bold-heading mark each becomes its own provision."""
    M = HEADING_MARK
    text = (f"{M}76 Requirement to notify\nA provider must give notice within 14 days. "
            f"Civil penalty: 1,500 penalty units.\n"
            f"{M}76A Requirement to notify if organisation ceases\nAn organisation must give notice.\n"
            f"{M}77 Requirement not to hold records outside Australia\n"
            f"(1) The System Operator must not hold the records outside Australia.\n")
    provs = extract_provisions(_doc(), text, OCRMetrics())
    labels = [p.article_section for p in provs]
    assert labels == ["Section 76", "Section 76A", "Section 77"]
    s77 = [p for p in provs if p.article_section == "Section 77"][0]
    assert "outside Australia" in s77.verbatim_snippet and "76A" not in s77.verbatim_snippet


# ─────────────────────── component coverage ───────────────────────
def test_covers_named_components():
    text = ("Section 1 Short title and a body long enough to keep this provision.\n"
            "Article 2 Interpretation with sufficient body text to be kept here.\n"
            "Regulation 3 Some rule with a body that exceeds the minimum length.\n"
            "Schedule 1 Heading\nAustralian Privacy Principle 8 cross-border disclosure of "
            "personal information is only allowed under listed conditions and consent.\n")
    labels = _labels(text)
    assert "Section 1" in labels
    assert "Article 2" in labels
    assert "Regulation 3" in labels
    assert "APP 8" in labels


def test_line_anchored_no_false_match_on_apart():
    # "apart from" / "part of" mid-text must NOT be treated as a Part boundary
    text = ("Section 1 Application and this section has a reasonably long body.\n"
            "apart from the matters listed, nothing else applies under this provision text.\n")
    assert _labels(text) == ["Section 1"]


def test_short_stub_and_running_header_filtered():
    """Part heading stubs and page running-headers (short bodies / year labels) are dropped."""
    text = ("Part 1\nPreliminary\n"                           # stub: body "Preliminary" < 20 chars
            "Section 1 Short title and a real body that is clearly long enough to survive.\n"
            "2020 Ed.\nPersonal Data Protection Act 2012 2\n")  # running header furniture
    labels = _labels(text)
    assert "Section 1" in labels
    assert "Part 1" not in labels        # stub dropped (no substantive body)
    assert not any(l.startswith("2020") for l in labels)
