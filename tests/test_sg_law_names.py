"""Singapore law names that reached the submission wrong, and why each one did.

Three defects, all in the Law Name column of a live SG pillar-7 run, all different causes:

    TERRORISM FINANCING AND PROLIFERATION FINANCING) RULES 2023
    (Confiscation of Benefits) Act 1992
    Personal Data Protection Regulations 2021 - Singapore ...

The first begins mid-word and closes a bracket it never opened. The second begins at a
parenthetical. The third is a search engine's rendering of the title, ellipsis and site
branding included — and it was the top-ranked row for indicator 7.4, so it is the first thing
a judge reads.
"""
import pytest

from backend.pipeline import extraction as E
from backend.schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy


def _doc(title):
    return DiscoveredDoc(
        doc_id="SG-x", economy=Economy.SG, title=title,
        source_url="https://sso.agc.gov.sg/x", portal="sso.agc.gov.sg",
        fmt=DocFormat.PDF_TEXT, relevance_score=1.0, discovery_tag=DiscoveryTag.NEW)


# The SSO PDF headers, as PyMuPDF extracts them.
_THREE_LINE_TITLE = """First published in the Government Gazette, Electronic Edition, on 1 June 2023 at 5 pm.
No. S 328
ACCOUNTANTS ACT 2004
ACCOUNTANTS (PREVENTION OF MONEY LAUNDERING,
TERRORISM FINANCING AND PROLIFERATION
FINANCING) RULES 2023
ARRANGEMENT OF RULES
"""

_FOUR_LINE_TITLE = """THE STATUTES OF THE REPUBLIC OF SINGAPORE
CORRUPTION, DRUG TRAFFICKING
AND OTHER SERIOUS CRIMES
(CONFISCATION OF BENEFITS)
ACT 1992
2020 REVISED EDITION
ARRANGEMENT OF SECTIONS
"""

_REGULATIONS = """First published in the Government Gazette, Electronic Edition, on 29 January 2021 at 5 pm.
No. S 63
PERSONAL DATA PROTECTION ACT 2012
(ACT 26 OF 2012)
PERSONAL DATA PROTECTION
REGULATIONS 2021
ARRANGEMENT OF REGULATIONS
"""


def test_a_title_wrapped_over_three_lines_is_assembled_whole():
    """The walk up the page used to test `block[0]` — the line most recently prepended —
    instead of the name assembled so far. The middle line here carries no bracket of its own,
    so the walk stopped while the name still had one open."""
    assert E._recover_law_name(_THREE_LINE_TITLE) == (
        "ACCOUNTANTS (PREVENTION OF MONEY LAUNDERING, TERRORISM FINANCING AND "
        "PROLIFERATION FINANCING) RULES 2023")


def test_a_name_never_begins_with_a_conjunction():
    """"And Other Serious Crimes (Confiscation of Benefits) Act 1992" is the middle of a title.
    Brackets balance here, so only the conjunction says the name is still incomplete."""
    # Compared case-insensitively: the SSO header prints in caps and the display casing is
    # decided elsewhere. What this test is about is whether the name is COMPLETE.
    got = E._recover_law_name(_FOUR_LINE_TITLE).lower()
    assert got.startswith("corruption, drug trafficking")
    assert "confiscation of benefits" in got
    assert "act 1992" in got


def test_a_truncated_title_loses_to_the_document_even_when_it_is_longer():
    """The guard was `len(recovered) > len(cleaned)`. The search engine renders the title as
    57 characters of stump plus site branding; the correct name is 41. Longer is not better —
    the ellipsis is proof the title is incomplete, so the document wins outright."""
    name = E._law_name(_doc("Personal Data Protection Regulations 2021 - Singapore ..."),
                       _REGULATIONS)
    assert name == "PERSONAL DATA PROTECTION REGULATIONS 2021"
    assert "..." not in name and "Singapore" not in name


@pytest.mark.parametrize("title, head, expect", [
    ("Personal Data Protection Act 2012 - Singapore Statutes Online",
     "PERSONAL DATA PROTECTION ACT 2012\nARRANGEMENT OF SECTIONS\n",
     "Personal Data Protection Act 2012"),
    ("Cybersecurity Act 2018 - Singapore Statutes Online",
     "CYBERSECURITY ACT 2018\nARRANGEMENT OF SECTIONS\n",
     "Cybersecurity Act 2018"),
])
def test_the_names_that_were_already_right_do_not_move(title, head, expect):
    """These two carry SG's measured output; the fix must not touch them."""
    assert E._law_name(_doc(title), head) == expect


@pytest.mark.parametrize("label, law, expect", [
    ("Section 15", "PERSONAL DATA PROTECTION REGULATIONS 2021", "Regulation 15"),
    ("Section 16", "ACCOUNTANTS (PREVENTION OF MONEY LAUNDERING, TERRORISM FINANCING AND "
                   "PROLIFERATION FINANCING) RULES 2023", "Rule 16"),
    ("Section 69", "Corruption, Drug Trafficking and Other Serious Crimes "
                   "(Confiscation of Benefits) Act 1992", "Section 69"),
])
def test_the_citation_unit_follows_the_corrected_name(label, law, expect):
    """A knock-on the fix earns: `_unit_label` reads the instrument type off the END of the
    name, so a name ending "- Singapore ..." could never be recognised as Regulations. The 7.4
    row was cited as "Section 15" of an instrument that has regulations, not sections."""
    assert E._unit_label(label, law) == expect
