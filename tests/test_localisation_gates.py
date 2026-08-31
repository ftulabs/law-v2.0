"""The three localisation indicators must keep the gates that were measured into them.

An independent auditor (tools/audit_rows.py, google/gemini-2.5-flash, calibrated against a
control group of the panel's own rows) refused 83% of the rows we filed under P6-I1, 80% under
P6-I3 and 67% under P6-I2 — against 28% for P7-I2. Reading all 24 refusals gave three groups,
and `backend/rdtii/indicators.py` now answers each with an explicit negative gate.

These tests are not style checks. Each asserts one gate, and each names the real provision that
was wrongly exported before the gate existed, because a definition edit that quietly removes a
gate looks exactly like a tidy-up in review — and its cost only shows up in a fresh audit
weeks later.

The measurement that justified them (tools/replay_grade.py, 107 exported rows, two independent
samplings agreeing): the panel's own rows survived 11/11, auditor-upheld rows survived 8/8, and
auditor-rejected rows dropped from 4 to 14 of 24.
"""
from __future__ import annotations

import pytest

from backend.rdtii import get_indicator


def test_p6i1_requires_the_restricted_thing_to_be_data():
    """India's Chemical Weapons Convention Act s.15-16 bans the transfer of "toxic Chemicals or
    Precursors" and was exported as a cross-border DATA ban. It shares "transfer" and
    "prohibited" with the test and nothing else."""
    t = get_indicator("P6-I1").legal_test.lower()
    assert "must be data" in t
    for other in ("goods", "chemicals", "currency"):
        assert other in t, f"the gate must name {other} as a non-qualifying subject"


def test_p6i1_rejects_licence_revocation():
    """Australia's Insurance Act s.15(1)(f) and Malaysia's PDPA s.18(4) are both revocation of an
    authorisation, exported as transfer bans."""
    t = get_indicator("P6-I1").legal_test.lower()
    assert "revoking" in t and ("licence" in t or "authorisation" in t)


def test_p6i2_requires_a_named_location():
    """Six refusals were record-keeping duties silent on where — SG Income Tax Act s.67(1)(a),
    Confiscation of Benefits Act s.43. The auditor's own phrase, five times: "does not specify a
    geographical location"."""
    t = get_indicator("P6-I2").legal_test.lower()
    assert "location must be named" in t
    assert "silent about" in t, "the gate must say a place-less record-keeping duty fails"


def test_p6i2_still_accepts_the_panel_s_own_answers():
    """The gate must not be worded so tightly that the key's P6-I2 provisions fail it. Each names
    a place, and each phrasing has to remain admissible: SG Companies Act s.199 "at the
    registered office … or such other place in Singapore", CN PIPL art.36 "within the territory",
    IN Companies Act s.128 "accessible in India", AU My Health Records Act s.77 (negative form,
    "must not be held … outside Australia")."""
    t = get_indicator("P6-I2").legal_test.lower()
    for phrasing in ("registered office", "territory", "accessible from within", "not outside it"):
        assert phrasing in t, f"the gate must admit the {phrasing!r} phrasing"


def test_p6i3_requires_named_infrastructure_not_an_agency_s_functions():
    """Both P6-I3 refusals were a provision listing what a MINISTRY does — China's domain-name
    measures art.4, Mongolia's public-information law art.32 — read as an infrastructure
    mandate."""
    t = get_indicator("P6-I3").legal_test.lower()
    assert "infrastructure must be named and located" in t
    assert "functions" in t and ("ministry" in t or "regulator" in t)
    for thing in ("server", "data centre"):
        assert thing in t


@pytest.mark.parametrize("iid", ["P6-I1", "P6-I2", "P6-I3"])
def test_each_gate_tells_the_grader_what_to_do_when_it_cannot_quote(iid):
    """Every gate ends in the same instruction: if you cannot quote the words, answer false. The
    audit's finding was over-assignment on topical overlap, and a gate that only describes the
    right answer without saying how to refuse does not stop it."""
    assert "answer false" in get_indicator(iid).legal_test.lower()


def test_nothing_is_left_staged_in_the_candidate_file():
    """tools/candidate_indicators.py is a staging area, not a second source of truth. A non-empty
    CANDIDATE means a measured change was never copied into the shipped definitions — the replay
    numbers would then describe text that no run actually uses."""
    from tools.candidate_indicators import CANDIDATE

    assert CANDIDATE == {}, f"unshipped staged edits: {sorted(CANDIDATE)}"
