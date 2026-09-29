"""Pillar 6/7 definitions against the RDTII 2.1 guide — the rules a China P6 run broke.

Measured 2026-09-29 by re-grading 24 (provision, indicator) pairs three to four times each on the
shipped grader and checker (deepseek-v4-flash + deepseek-v4-pro-0813): the old definitions were
right on every repetition for 20, these for 22. What moved: storage-only rules stopped landing in
6.1 (accounting backup copies 2-3/3 → 0/3, audit working papers 2-3/3 → 0/3) while every 6.1
panel answer stayed; computer-crime offences came back into 7.2 (Malaysia CCA s.3 0/4 → 4/4).
These tests pin the wording that produced that, so a later edit cannot quietly undo it.
"""
from backend.pipeline import mapping
from backend.rdtii.indicators import get_indicator


def test_storage_alone_is_local_storage_not_local_processing():
    """Guide p.51: a measure goes under both only when the law requires processing AND storage."""
    test = get_indicator("P6-I1").legal_test
    assert "LIMB (b) NEEDS MORE THAN STORAGE" in test
    assert "compelling any of those activities to happen domestically" not in test
    place = get_indicator("P6-I1").verify_elements[1]
    assert "storage or keeping a copy is the ONLY" in place


def test_processing_verbs_beyond_storage_still_satisfy_6_1():
    """Russia 152-FZ art.18(5) is the panel's 6.1 answer: recording, systematisation, accumulation."""
    place = get_indicator("P6-I1").verify_elements[1]
    for verb in ("recording", "systematisation", "accumulation", "retrieval", "TRANSACTIONS"):
        assert verb in place


def test_not_exceeding_an_approved_scope_is_a_condition_not_a_ban():
    assert "EXCEEDING" in get_indicator("P6-I1").legal_test
    assert "EXCEED" in get_indicator("P6-I4").legal_test


def test_storage_plus_assessment_is_both_6_2_and_6_4():
    """The panel cites PIPL art.40 under 6.2 and 6.4."""
    assert "PIPL art.40 under both" in get_indicator("P6-I4").legal_test
    assert "BOTH P6-I2 AND P6-I4" in mapping.SYSTEM


def test_grader_no_longer_says_every_storage_prohibition_is_a_ban():
    assert "is BOTH a ban (P6-I1) AND a local-storage requirement" not in mapping.SYSTEM
    assert "ONLY fixes where data or a copy is stored is P6-I2 alone" in mapping.SYSTEM


def test_data_centre_licensing_belongs_to_9_4():
    assert "9.4" in get_indicator("P6-I3").legal_test


def test_cybercrime_offences_count_for_7_2():
    """The Round-2 Database cites Thailand's Computer-Related Crime Act s.5/s.9 for 7.2."""
    ind = get_indicator("P7-I2")
    assert "CYBERCRIME OFFENCES ARE PART OF THE FRAMEWORK" in ind.legal_test
    assert "an offence of damaging a computer" not in " ".join(ind.verify_elements)
    assert "OFFENCE" in ind.verify_elements[1]
