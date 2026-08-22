"""The other ten pillars — coverage, separation, and the traps in the numbering.

The final-round brief warns the sealed test may name "a pillar you have not worked on". These
pin the two things that make that survivable: every in-scope indicator is defined, and adding
fifty-two of them did not disturb the nine that are measured.
"""
import pytest

import main
from backend.rdtii import codes, instrument
from backend.rdtii.indicators import INDICATORS, get_indicator, get_indicators, siblings
from backend.rdtii.indicators_wide import INDICATORS_WIDE, INVERTED, PILLAR_NAMES
from backend.rdtii.keywords import portal_search_queries


# ── coverage ─────────────────────────────────────────────────────────────────────────
def test_every_in_scope_rdtii_indicator_is_defined_somewhere():
    """61 regulatory indicators, from the panel's own Methodology sheet. A pillar with criteria
    but no legal_test is not "unsupported" at run time — it silently returns "No provision
    found" for every indicator, which reads exactly like a clean economy."""
    defined = {i.indicator_id for i in INDICATORS_WIDE} | {"6.1", "6.2", "6.3", "6.4",
                                                           "7.1", "7.2", "7.3", "7.4", "7.5"}
    assert codes.official_codes() - defined == set()


def test_no_indicator_is_invented():
    assert {i.indicator_id for i in INDICATORS_WIDE} <= codes.official_codes()


def test_every_wide_indicator_has_a_legal_test_and_query_terms():
    for ind in INDICATORS_WIDE:
        assert len(ind.legal_test) > 120, ind.indicator_id
        assert ind.query_terms, ind.indicator_id


def test_all_twelve_pillars_are_named():
    assert sorted(PILLAR_NAMES) == list(range(1, 13))


# ── separation: the measured nine must not move ──────────────────────────────────────
def test_the_measured_nine_are_untouched():
    """The retrieval parameters in docs/retrieval-redesign.md were swept against exactly these,
    and backend/eval builds its corpus from get_indicators(None). Widening that default would
    re-baseline every measurement we hold, without failing anything."""
    assert len(INDICATORS) == 9
    assert len(get_indicators(None)) == 9
    assert {i.pillar for i in INDICATORS} == {6, 7}


def test_the_wide_registry_never_shadows_pillars_six_and_seven():
    assert not {i.pillar for i in INDICATORS_WIDE} & {6, 7}


@pytest.mark.parametrize("pillar", [1, 2, 3, 4, 5, 8, 9, 10, 11, 12])
def test_every_other_pillar_now_resolves(pillar):
    assert get_indicators(pillar), pillar


def test_siblings_reach_across_the_wide_registry():
    """The mapper shows siblings so a model can tell one limb from another. 12.4 splits into
    seven limbs distinguished only by which aspect of a payment they restrict; a grader shown
    one in isolation maps any payment rule to it."""
    others = {i.indicator_id for i in siblings("12.4.5")}
    assert {"12.4.1", "12.4.4", "12.4.6"} <= others
    assert "12.4.5" not in others


# ── the numbering traps ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code", ["4.01", "4.1", "12.01", "12.4.1", "12.9"])
def test_the_codes_that_a_float_would_destroy_survive_as_themselves(code):
    """4.01 read as a number becomes 4.1, and 12.10 becomes 12.1 — four different indicators.
    These IDs are the numeric code precisely because P<pillar>-I<n> cannot express them."""
    assert get_indicator(code) is not None
    assert codes.to_rdtii_code(code) == code
    assert codes.is_valid(code)


def test_four_zero_one_and_four_one_are_different_indicators():
    assert get_indicator("4.01").title != get_indicator("4.1").title


# ── polarity ─────────────────────────────────────────────────────────────────────────
def test_absence_framed_indicators_say_so_in_their_own_legal_test():
    """Nine of these score when the framework is MISSING, so finding the law is the result, not
    a null. A grader reading only the test must not conclude otherwise — the same inversion
    scoring_rubric.py documents for 7.1 and 7.2."""
    for code in INVERTED:
        assert "POLARITY" in get_indicator(code).legal_test, code


def test_every_inverted_code_is_a_real_indicator():
    assert INVERTED <= {i.indicator_id for i in INDICATORS_WIDE}


# ── discovery reaches them ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("pillar", [1, 2, 3, 4, 5, 8, 9, 10, 11, 12])
def test_a_full_text_lane_has_something_to_search_for(pillar):
    assert len(portal_search_queries("SG", pillar, name_only=False)) >= 4


@pytest.mark.parametrize("pillar", [1, 2, 3, 4, 5, 8, 9, 10, 11, 12])
def test_a_name_only_portal_gets_law_name_fragments_not_obligation_phrases(pillar):
    """AU's OData matches `contains(name,…)` against the Act TITLE. Firing "shall not be
    exported" at it returns nothing, and returns it silently."""
    got = portal_search_queries("AU", pillar, name_only=True)
    assert got, pillar
    assert all(len(q.split()) <= 5 for q in got), got


# ── the CLI ──────────────────────────────────────────────────────────────────────────
def test_all_still_means_the_two_mandatory_pillars():
    """Not twelve. Every script, doc and cached result in the repo assumes it, and widening the
    default would multiply the cost of every existing command by six."""
    assert main.parse_pillars("all") == [6, 7]


@pytest.mark.parametrize("raw,want", [
    ("6", [6]), ("9", [9]), ("6,7,12", [6, 7, 12]), ("all12", list(range(1, 13))),
])
def test_pillar_selection(raw, want):
    assert main.parse_pillars(raw) == want


def test_an_impossible_pillar_is_refused_rather_than_run_empty():
    with pytest.raises(SystemExit):
        main.parse_pillars("99")


# ── a portal publishes more than law ─────────────────────────────────────────────────
@pytest.mark.parametrize("name", [
    "《数据出境安全评估办法》答记者问",          # CAC press Q&A — mapped 4× in a real CN run
    "《中华人民共和国数据安全法》解读",           # expert commentary on the Act
    "个人信息保护政策法规问答（2026年1月）",
    "Press release: new data rules take effect",
    "Explanatory Memorandum to the Privacy Regulations",
])
def test_commentary_published_beside_a_measure_is_not_the_measure(name):
    """These retrieve at the top of the list because they use the measure's exact vocabulary,
    and they graded confidently. The tell is the citation: a press release has no article to
    cite, so every one of them came out as "(document)"."""
    assert instrument.classify(name) is instrument.Status.COMMENTARY


@pytest.mark.parametrize("name", [
    "Advisory Guidelines on Key Concepts in the PDPA",       # PDPC guidance — a cited answer
    "信息安全技术 个人信息安全影响评估指南",                    # GB/T 39335 — a cited answer
    "Cybersecurity Act 2018",
    "中华人民共和国网络安全法",
])
def test_guidance_and_standards_are_not_swept_up_with_the_press_releases(name):
    """Several of the panel's own answers ARE guidance or a technical standard. Blocking the
    word "guidance" to catch a press release would cost real evidence."""
    assert instrument.classify(name) is instrument.Status.SCOREABLE
