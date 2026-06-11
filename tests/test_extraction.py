"""Provision extraction: component coverage, font-marked AU headings, label normalization,
and noise filtering. Pins the fixes for the AU §76/§76A/§77 lumping and APP-8 isolation.
"""
from backend.pipeline.extraction import (
    HEADING_MARK, _normalise_label, extract_provisions,
)
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy, OCRMetrics


def _doc(economy=Economy.AU):
    return DiscoveredDoc(doc_id="d", economy=economy, title="Test Act 2020",
                         source_url="u", portal="p", fmt=DocFormat.PDF_TEXT,
                         discovery_tag=DiscoveryTag.NEW)


def _labels(text):
    return [p.article_section for p in extract_provisions(_doc(), text, OCRMetrics())]


# ─────────────────────── SG subsidiary-legislation (per-country) ───────────────────────
def test_sg_sso_chrome_and_cross_ref_and_heading():
    """SG SSO PDFs: strip page chrome (incl. its bold HEADING_MARK), split em-dash sections
    "11.—(1)" with the marginal heading attached, never the previous reg's tail, and IGNORE
    "section N of the Act" cross-references (SG numbers its own sections, so the keyword form
    is only ever a reference)."""
    M = HEADING_MARK
    text = (
        "ARRANGEMENT OF PROVISIONS\n"
        "10. Requirements for transfer\n"
        "11. Legally enforceable obligations\n"
        "Requirements for transfer\n"
        "10.—(1) For the purposes of section 26 of the Act, a transferring organisation must "
        "comply with the requirements, the fee allowed by the Commission under section 48H(2) "
        "of the Act being payable.\n"
        f"{M}1 S 63/2021\n"                                      # bold page footer (marked) → chrome
        "(4) This Part does not prevent an individual from withdrawing consent.\n"
        "Legally enforceable obligations\n"
        "11.—(1) For the purposes of regulation 10(1), legally enforceable obligations include "
        "obligations imposed on a recipient under any law.\n"
        "Informal Consolidation – version in force from 2/3/2026\n"
        "S 63/2021 14\n")
    provs = extract_provisions(_doc(Economy.SG), text, OCRMetrics())
    labels = [p.article_section for p in provs]
    assert labels.count("Section 11") == 1 and "Section 10" in labels
    assert "Section 48H" not in " ".join(labels)               # cross-ref is not a boundary
    s11 = next(p for p in provs if p.article_section == "Section 11")
    assert s11.verbatim_snippet.startswith("Legally enforceable obligations")  # starts at the heading
    assert "11.—(1) For the purposes of regulation 10(1)" in s11.verbatim_snippet
    assert "withdrawing consent" not in s11.verbatim_snippet    # no previous reg's tail
    assert "S 63/2021" not in s11.verbatim_snippet              # chrome (and its mark) stripped
    assert "Informal Consolidation" not in s11.verbatim_snippet


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


# ─────────────────── AU: schedules, APPs, cross-reference traps (per-country) ───────────────────
def test_au_app_relabel_schedule_scope_and_cross_ref_suppressed():
    """AU font-marked PDF: a font-marked heading inside Schedule 1 is relabelled 'APP N' and
    keeps its full text; a marked section in Schedule 2 is scoped so its restarted numbering
    doesn't collide with the main body; and an 'Australian Privacy Principle 8.3' / 'Schedule 2'
    CROSS-REFERENCE in a main section is NOT treated as a boundary."""
    M = HEADING_MARK
    text = (
        f"{M}100 Regulations\n"
        "(1A) Before the Governor-General makes regulations for the purposes of\n"
        "Australian Privacy Principle 8.3 prescribing a country or binding scheme, the Minister "
        "must be satisfied, including matters set out in Schedule 2 to the Act.\n"
        "Schedule 1—Australian Privacy Principles\n"
        f"{M}8 Australian Privacy Principle 8—cross-border disclosure of personal information\n"
        "8.1 Before an APP entity discloses personal information about an individual to an "
        "overseas recipient, the entity must take reasonable steps.\n"
        "8.2 Subclause 8.1 does not apply to the disclosure in certain listed circumstances here.\n"
        f"{M}9 Australian Privacy Principle 9—adoption of government related identifiers\n"
        "9.1 An organisation must not adopt a government related identifier of an individual.\n"
        "Schedule 2—Statutory Tort for Serious Invasions of Privacy\n"
        f"{M}1 Objects of this Schedule\n"
        "The objects of this Schedule are to establish a cause of action for serious invasions.\n")
    provs = extract_provisions(_doc(Economy.AU), text, OCRMetrics())
    labels = [p.article_section for p in provs]
    assert "Section 100" in labels                         # main section kept, NOT scoped
    assert "APP 8" in labels and "APP 9" in labels         # Schedule-1 headings relabelled
    assert not any(l.startswith("APP 8") and l != "APP 8" for l in labels)  # no false APP from "8.3"
    assert "Schedule 2, Section 1" in labels               # other-schedule section scoped
    app8 = next(p for p in provs if p.article_section == "APP 8")
    assert "8.1" in app8.verbatim_snippet and "8.2" in app8.verbatim_snippet  # full principle, not just 8.1
    s100 = next(p for p in provs if p.article_section == "Section 100")
    assert "prescribing a country" in s100.verbatim_snippet  # the cross-ref text stays in s100
