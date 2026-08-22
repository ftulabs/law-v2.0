"""A law's name, taken from the clause where the law names itself.

Every name-recovery path in `extraction` reads the HEADER region — an "ARRANGEMENT OF" anchor,
an uppercase title block, a "LAWS OF MALAYSIA / Act A1727" header. A Gazette of India
notification defeats all of them at once: pages 1-23 are the Hindi text, so the English name
first appears on page 23, well past the 8,000-character window those paths read.

The cost was visible in a submission. India's operative cross-border instrument, the Digital
Personal Data Protection Rules 2025, reached the CSV with a Law Name of
`53450e6e5dc0bfa85ebd78686cadad39` — the MeitY upload's filename — and its rule 15, which is
the 6.4 evidence, cited as "Section 15", a provision that does not exist in it.
"""
import pytest

from backend.pipeline.extraction import _recover_short_title, _unit_label


@pytest.mark.parametrize("text, expect", [
    ("These rules may be called the Digital Personal Data Protection Rules, 2025.",
     "Digital Personal Data Protection Rules, 2025"),
    ("This Act may be cited as the Personal Data Protection Act 2010.",
     "Personal Data Protection Act 2010"),
    ("1. This Act may be called the Information Technology Act, 2000.",
     "Information Technology Act, 2000"),
    # The clause continues past the name; the joining word ends it.
    ("These regulations may be known as the Cybersecurity Regulations 2018 and shall come "
     "into operation on 31 August 2018.", "Cybersecurity Regulations 2018"),
])
def test_the_instrument_names_itself(text, expect):
    assert _recover_short_title(text) == expect


def test_the_name_is_found_even_when_the_clause_wraps():
    """This is how the real PDF reads, and why the first implementation returned None: the
    name breaks across a line, a newline-bounded match captures the half without the year, and
    the year check then rejects it — silently, because a missing name is not an error."""
    wrapped = ("1. Short title and commencement. — (1) These rules may be called the Digital "
               "Personal Data Protection\nRules, 2025.\n(2) They shall come into force …")
    assert _recover_short_title(wrapped) == "Digital Personal Data Protection Rules, 2025"


@pytest.mark.parametrize("text", [
    "A witness may be called upon to produce records of the company.",
    "The Minister may be known as the competent authority for this purpose.",
    "These rules may be called the Scheme.",            # no year — not identifying
    "",
])
def test_ordinary_prose_does_not_become_a_law_name(text):
    """The capture has to look like an instrument — a law-type word AND a year — or a document
    full of the words 'may be called' would rename itself off any sentence."""
    assert _recover_short_title(text) is None


def test_it_runs_only_after_the_measured_header_paths(monkeypatch):
    """A fallback, not a new primary rule. The header paths are measured against SG/MY/AU and
    this must not move a name they already get right."""
    from backend.pipeline import extraction as E
    doc = ("PERSONAL DATA PROTECTION ACT 2010\n"
           "ARRANGEMENT OF SECTIONS\n"
           "1. This Act may be cited as the Wrong Name Act 1999.\n")
    assert E._recover_law_name(doc) == "PERSONAL DATA PROTECTION ACT 2010"


@pytest.mark.parametrize("label, law, expect", [
    ("Section 15", "Digital Personal Data Protection Rules, 2025", "Rule 15"),
    ("Section 5", "Personal Data Protection Regulations 2021", "Regulation 5"),
    ("Section 12B", "Cybersecurity Rules 2018", "Rule 12B"),
    # An Act keeps sections, including one whose SUBJECT is rules.
    ("Section 26", "Personal Data Protection Act 2012", "Section 26"),
    ("Section 3", "The Interpretation of Rules Act, 1950", "Section 3"),
    # Already spelled out by the document, or not a bare number — left alone.
    ("Regulation 7", "Some Rules 2020", "Regulation 7"),
    ("APP 8", "Privacy Act 1988", "APP 8"),
    # Deliberately not handled: a type-leading name. Under-reaching is the safe direction.
    ("Section 40", "Rules of Court 2021", "Section 40"),
])
def test_a_rule_is_cited_as_a_rule(label, law, expect):
    assert _unit_label(label, law) == expect
