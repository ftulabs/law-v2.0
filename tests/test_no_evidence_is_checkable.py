"""A correct negative must be distinguishable from a broken run.

Singapore pillar 1 reads the Countervailing and Anti-Dumping Duties Act 1996 and its 1997
Regulations — the right instruments, ranked first by discovery — and then correctly declines
to cite them: indicator 1.4 asks for a duty IMPOSED on an ICT good, and its own legal test says
"the enabling ACT alone is not a measure". The portal carries no notice imposing a duty on any
product, so "No provision found" is the answer.

The run reported 7 documents, 480 provisions and 0 matches, and the row said only "no active
provision was identified". Nothing on the screen or in the CSV showed that the search had
reached the right law, so a correct refusal read as a failure.
"""
from backend.pipeline.orchestrator import _no_evidence_placeholders, _searched_laws
from backend.rdtii import get_indicators
from backend.schemas import Economy


class _Prov:
    def __init__(self, law_name):
        self.law_name = law_name


def _corpus():
    return ([_Prov("Countervailing and Anti-Dumping Duties Act 1996")] * 180
            + [_Prov("Countervailing and Anti-Dumping Duties Regulations 1997")] * 120
            + [_Prov("Regulation of Imports and Exports Act 1995")] * 90
            + [_Prov("Wildlife Act 1965")] * 60)


def test_the_laws_actually_read_are_ranked_by_how_much_of_the_corpus_they_are():
    assert _searched_laws(_corpus(), limit=2) == [
        "Countervailing and Anti-Dumping Duties Act 1996",
        "Countervailing and Anti-Dumping Duties Regulations 1997",
    ]


def test_a_no_evidence_row_names_what_it_read():
    rows = _no_evidence_placeholders("run-x", Economy.SG, get_indicators(1), [],
                                     lambda _m: None, _corpus())
    assert len(rows) == 1
    notes = rows[0].notes
    assert "Countervailing and Anti-Dumping Duties Act 1996" in notes
    assert "Laws read for this run" in notes


def test_the_row_itself_keeps_the_wording_the_judges_asked_for():
    """The Q&A fixed the snippet text and the N/A columns; only Notes gains anything."""
    row = _no_evidence_placeholders("run-x", Economy.SG, get_indicators(1), [],
                                    lambda _m: None, _corpus())[0]
    assert row.law_name == "No provision found"
    assert row.verbatim_snippet == "No evidence found"
    assert row.article_section == "N/A"


def test_a_run_with_no_provisions_says_nothing_extra():
    """No corpus means nothing to report, and inventing a sentence would be worse than the
    generic one — so the note is unchanged rather than padded."""
    for corpus in (None, []):
        row = _no_evidence_placeholders("run-y", Economy.SG, get_indicators(1), [],
                                        lambda _m: None, corpus)[0]
        assert "Laws read" not in row.notes


def test_an_indicator_that_did_find_evidence_gets_no_placeholder():
    from backend.schemas import ReviewStatus

    class _M:
        indicator_id = "1.4"
        review_status = ReviewStatus.AUTO_ACCEPTED

    assert _no_evidence_placeholders("run-z", Economy.SG, get_indicators(1), [_M()],
                                     lambda _m: None, _corpus()) == []
