"""The second-pass check on accepted rows (mapping.verify_mapping) and how it moves confidence.

Every case here is a row from the 2026-09-25 live runs whose handling decided a design rule."""
from types import SimpleNamespace

from backend.pipeline import confidence
from backend.pipeline.mapping import quote_in_snippet, verify_mapping
from backend.rdtii.indicators import INDICATORS
from backend.schemas import ConfidenceBreakdown

IND = {i.indicator_id: i for i in INDICATORS}

CPC39 = ("Power to access computer\n39.—(1) Subject to subsection (1A), a police officer or an "
         "authorised person investigating an arrestable offence may, at any time —\n(a) access, "
         "inspect and check the operation of a computer that the police officer or authorised "
         "person has reasonable cause to suspect is or has been used in connection with")
PDPA129 = ("Transfer of personal data to places outside Malaysia 129. (1) A data user shall not "
           "transfer any personal data of a data subject to a place outside Malaysia unless to "
           "such place as specified by the Minister, upon the recommendation of the Commissioner, "
           "by notification published in the Gazette.")
BANK55C = ("Approval of transfer 55C.—(1) A transferor must apply to the Court for its approval "
           "of the transfer of the whole or any part of the business of the transferor to a "
           "transferee.")


def _prov(snippet, economy="SG"):
    return SimpleNamespace(economy=economy, law_name="Act", article_section="s1",
                           verbatim_snippet=snippet)


class _Scripted:
    """Answers each call with the next scripted response."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def complete_json(self, system, user):
        self.calls += 1
        return self.answers.pop(0)


def _ans(*quotes, verdict=True, reason="r"):
    return {"elements": [{"element": i, "quote": q} for i, q in enumerate(quotes, 1)],
            "verdict": verdict, "reason": reason}


def test_quote_match_tolerates_dropped_enumerators_and_line_breaks():
    # The checker spliced "(a)" out of "at any time —\n(a) access" — still the statute's words.
    assert quote_in_snippet("may, at any time — access, inspect and check the operation of a "
                            "computer", CPC39)
    assert quote_in_snippet("a police officer or an authorised person", CPC39)


def test_quote_match_refuses_words_the_snippet_does_not_contain():
    assert not quote_in_snippet("without a warrant issued by a Magistrate", CPC39)
    assert not quote_in_snippet("", CPC39)
    assert not quote_in_snippet("ab", CPC39)


def test_quote_match_refuses_words_scattered_across_the_section():
    # every word is somewhere in the snippet, but not together — not a quotation
    assert not quote_in_snippet("offence computer police access subsection", CPC39)


def test_an_element_the_checker_cannot_quote_is_a_refusal():
    # Banking Act s55C filed under 6.4: a transfer of BUSINESS, no data, no foreign destination.
    llm = _Scripted(_ans(None, "must apply to the Court for its approval", verdict=False))
    verdict, why = verify_mapping(IND["P6-I4"], _prov(BANK55C), llm)
    assert verdict is False and "element 1" in why and llm.calls == 1


def test_all_quoted_but_refused_once_is_asked_again_and_a_pass_wins():
    # My Health Records s77 under 6.2: refused on one call, passed on the next, same quotes.
    q = ("transfer any personal data of a data subject to a place outside Malaysia",
         "unless to such place as specified by the Minister")
    llm = _Scripted(_ans(*q, verdict=False), _ans(*q))
    verdict, _ = verify_mapping(IND["P6-I4"], _prov(PDPA129, "MY"), llm)
    assert verdict is True and llm.calls == 2


def test_a_refusal_that_repeats_stands():
    q = ("transfer any personal data of a data subject to a place outside Malaysia",
         "unless to such place as specified by the Minister")
    llm = _Scripted(_ans(*q, verdict=False, reason="cap"), _ans(*q, verdict=False))
    verdict, _ = verify_mapping(IND["P6-I4"], _prov(PDPA129, "MY"), llm)
    assert verdict is False


def test_a_quote_the_code_cannot_find_leaves_the_row_unsettled_not_refused():
    # AU TIA Act s178: the PDF interleaves columns, the checker quoted the sentence as it
    # should read. Unverifiable is not wrong.
    llm = _Scripted(_ans("a police officer or an authorised person",
                         "authorise the disclosure of information or a document",
                         "a police officer or an authorised person"))
    verdict, why = verify_mapping(IND["P7-I5"], _prov(CPC39), llm)
    assert verdict is None and "not in the snippet" in why


def test_a_failed_call_is_unsettled():
    class Boom:
        def complete_json(self, *_):
            raise TimeoutError
    assert verify_mapping(IND["P7-I5"], _prov(CPC39), Boom())[0] is None


def test_7_1_is_not_checked_because_the_expert_asked_for_every_provision():
    assert IND["P7-I1"].verify_elements == []
    assert all(IND[i].verify_elements for i in IND if i != "P7-I1")


def _b(final=0.9):
    return ConfidenceBreakdown(retrieval_score=0.6, legal_match=1.0, snippet_grounding=1.0,
                               scope_alignment=1.0, final=final, explanation="x")


def test_the_check_decides_the_band():
    assert confidence.route(confidence.apply_verification(_b(), False, "no").final).value \
        == "quarantined"
    assert confidence.route(confidence.apply_verification(_b(), None, "?").final).value \
        == "pending_review"
    assert confidence.route(confidence.apply_verification(_b(), True, "q").final).value \
        == "auto_accepted"


def test_subsection_is_read_off_the_verified_quotes_only_when_they_agree():
    from backend.pipeline.mapping import subsection_from_quotes
    s199 = ("199.—(1) Every company must cause to be kept such accounting and other records as "
            "will sufficiently explain the transactions.\n(2) The company must retain the records "
            "for a period of not less than 5 years.\n(4) If accounting records are kept outside "
            "Singapore, the company must send to and keep at a place in Singapore such statements.")
    assert subsection_from_quotes({1: "The company must retain the records",
                                   2: "for a period of not less than 5 years"}, s199) == "(2)"
    # quotes in different subsections → the rule spans them → section level, never a guess
    assert subsection_from_quotes({1: "accounting and other records as will sufficiently",
                                   2: "send to and keep at a place in Singapore"}, s199) is None
    assert subsection_from_quotes({1: "a quote that is nowhere in it"}, s199) is None


def test_a_pass_carries_the_checkers_rationale_and_a_refusal_does_not():
    a = _ans("transfer any personal data of a data subject to a place outside Malaysia",
             "unless to such place as specified by the Minister")
    a["rationale"] = "This Section permits transfer abroad only to Minister-specified places."
    v = verify_mapping(IND["P6-I4"], _prov(PDPA129, "MY"), _Scripted(a))
    assert v[0] is True and v.rationale.startswith("This Section permits")
    assert "_rationale" not in v.quotes
    r = verify_mapping(IND["P6-I4"], _prov(BANK55C), _Scripted(_ans(None, "x", verdict=False)))
    assert r.rationale == ""


def test_the_checker_model_is_only_swapped_on_openrouter(monkeypatch):
    from backend.config import settings
    from backend.pipeline.mapping import _checker_llm
    monkeypatch.setattr(settings, "verify_model", "deepseek/deepseek-v4-pro-0813")
    mock = object()
    assert _checker_llm(mock, lambda *_: None) is mock
