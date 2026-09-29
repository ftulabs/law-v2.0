"""A pillar-6 acceptance needs a quote that NAMES a place (mapping._check_once, place_words.py).

The fixture is the Mongolia pillar-6 run of 2026-09-29 (run-c3826900): the ten rows it kept, the
snippet each was graded on, and the quotes the second-pass checker gave. A reviewer marked four
wrong, and all four had passed the check on a quote that names no country:
  • Cybersecurity Law art.14 (6.3): the powers of the armed forces' cyber unit, quoted for
    "the words placing that infrastructure inside the country" as a list of armed-forces units;
  • credit-information rule 2.3 (6.2): a policy must STATE the storage "байршил" (location);
    none is fixed;
  • environmental-database rule 2.2 (6.2): "Улсын мэдээллийн санд", in the STATE database;
  • credit-information rule 5.1 (6.4): may transfer "бусдад", to others; no foreign destination.
The six others each quote Монгол Улс, its territory, or abroad, and must still pass."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.pipeline.mapping import quote_in_snippet, verify_mapping
from backend.rdtii.indicators import INDICATORS
from backend.rdtii.place_words import names_place

IND = {i.indicator_id: i for i in INDICATORS}
ROWS = json.loads((Path(__file__).parent / "fixtures" / "mn_p6_checker_2026_09_29.json")
                  .read_text(encoding="utf-8"))


class _Scripted:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def complete_json(self, system, user):
        self.calls += 1
        return self.answers.pop(0)


def _answer(quotes: dict, verdict=True):
    return {"elements": [{"element": int(k), "quote": v} for k, v in quotes.items()],
            "verdict": verdict, "reason": "r", "rationale": "This Article requires X."}


def _prov(row):
    return SimpleNamespace(economy="MN", law_name=row["law"], article_section=row["article"],
                           verbatim_snippet=row["snippet"], language=None)


def _id(row):
    return f"{row['indicator']}-{row['article'].split()[0]}-{row['user_verdict']}"


def test_the_fixture_is_the_run():
    assert len(ROWS) == 10
    assert sorted((r["indicator"], r["article"]) for r in ROWS if r["user_verdict"] == "wrong") == [
        ("P6-I2", "2.2"), ("P6-I2", "2.3"), ("P6-I3", "14 дүгээр зүйл"), ("P6-I4", "5.1")]
    for r in ROWS:
        # every quote really is in the snippet — which is why the old check let the wrong ones pass
        for q in r["checker_quotes"].values():
            assert quote_in_snippet(q, r["snippet"]), (r["article"], q)


@pytest.mark.parametrize("row", [r for r in ROWS if r["user_verdict"] == "wrong"], ids=_id)
def test_a_wrong_row_is_refused_on_the_quotes_that_used_to_pass_it(row):
    llm = _Scripted(_answer(row["checker_quotes"]), _answer(row["checker_quotes"]))
    verdict, why = verify_mapping(IND[row["indicator"]], _prov(row), llm)
    assert verdict is False
    k = IND[row["indicator"]].verify_place_element
    assert f"element {k} names no place" in why
    # none of these four snippets names a place anywhere, so no second call is spent on them
    assert not names_place(row["snippet"]) and llm.calls == 1


@pytest.mark.parametrize("row", [r for r in ROWS if r["user_verdict"] == "right"], ids=_id)
def test_a_right_row_still_passes(row):
    llm = _Scripted(_answer(row["checker_quotes"]))
    verdict, _ = verify_mapping(IND[row["indicator"]], _prov(row), llm)
    assert verdict is True and llm.calls == 1


def _row(indicator, article):
    return next(r for r in ROWS if r["indicator"] == indicator and r["article"] == article)


def test_a_short_quote_on_a_snippet_that_names_a_place_is_asked_again_and_the_fuller_one_wins():
    # 7.1: the servers "shall be located within the territory of Mongolia". A quote of only the
    # verb is not enough on its own, but the snippet does name the place — ask again.
    row = _row("P6-I2", "7.1")
    short = {1: row["checker_quotes"]["1"], 2: "байршина"}
    llm = _Scripted(_answer(short), _answer(row["checker_quotes"]))
    verdict, _ = verify_mapping(IND["P6-I2"], _prov(row), llm)
    assert verdict is True and llm.calls == 2


def test_the_same_short_quote_twice_is_a_refusal():
    row = _row("P6-I2", "7.1")
    short = {1: row["checker_quotes"]["1"], 2: "байршина"}
    llm = _Scripted(_answer(short), _answer(short))
    verdict, why = verify_mapping(IND["P6-I2"], _prov(row), llm)
    assert verdict is False and "element 2 names no place" in why and llm.calls == 2


def test_only_the_place_element_is_held_to_it():
    # 6.3 on rule 3.2: element 3 is "shall meet the following conditions" (хангасан байна), which
    # names no place and must not need to.
    row = _row("P6-I3", "3.2")
    assert not names_place(row["checker_quotes"]["3"])
    verdict, _ = verify_mapping(IND["P6-I3"], _prov(row), _Scripted(_answer(row["checker_quotes"])))
    assert verdict is True


def test_the_place_element_is_the_one_whose_description_asks_for_a_place():
    assert {i.indicator_id: i.verify_place_element for i in INDICATORS} == {
        "P6-I1": 2, "P6-I2": 2, "P6-I3": 2, "P6-I4": 1,
        "P7-I1": None, "P7-I2": None, "P7-I3": None, "P7-I4": None, "P7-I5": None}
    for iid in ("P6-I1", "P6-I2", "P6-I3", "P6-I4"):
        ind = IND[iid]
        text = ind.verify_elements[ind.verify_place_element - 1]
        assert "country" in text or "outside" in text, (iid, text)


def test_pillar_7_is_untouched():
    # 7.3 retention: a quote with no place in it passes as before
    snippet = "A data user shall retain the records for a period of seven years."
    ind = IND["P7-I3"]
    quotes = {i: "shall retain the records for a period of seven years"
              for i in range(1, len(ind.verify_elements) + 1)}
    verdict, _ = verify_mapping(ind, SimpleNamespace(economy="MY", law_name="A", article_section="s1",
                                                     verbatim_snippet=snippet, language=None),
                                _Scripted(_answer(quotes)))
    assert verdict is True


# Quotes from panel answers that passed the live checker on 2026-09-29 — each must name a place.
@pytest.mark.parametrize("quote", [
    "Монгол Улсын нутаг дэвсгэрт байршуулна",                       # MN public-information law 27.7
    "хандах эрх зөвхөн Монгол Улсаас байх",                           # MN credit rule 14.1.7 (declined)
    "мэдээллийг гадаад улс дахь хүн, хуулийн этгээд",                  # MN PDP law 14.1
    "应当在中华人民共和国境内存储",                                     # CN PIPL art.36
    "确需向境外提供的",                                                 # CN PIPL art.40
    "应当在中国内地存储和使用",                                         # CN ride-hailing art.27
    "transfer any personal data to a country or territory outside Singapore",  # SG PDPA s26
    "there must be sent to and kept at a place in Singapore",           # SG Companies Act s199(4)
    "must not: (a) hold the records, or take the records, outside Australia",  # AU MHR s77
    "transfer of personal data by a Data Fiduciary for processing to such country",  # IN DPDP s16
    "Transfer of personal data to places outside Malaysia",             # MY PDPA s129
    "shall be kept and retained in Malaysia",                           # MY Income Tax s82A
    "di wilayah Indonesia",                                             # ID PP 71/2019 art.20
    "ส่งหรือโอนข้อมูลส่วนบุคคลไปยังต่างประเทศ",                        # TH PDPA s28
    "на территории Российской Федерации",                               # RU 152-FZ art.18(5)
    "a place in this jurisdiction",                                     # AU Corporations Act s172
])
def test_panel_quotes_name_a_place(quote):
    assert names_place(quote)


@pytest.mark.parametrize("quote", [
    "хадгалах хугацаа болон байршил",      # storage period and location — no place fixed
    "Улсын мэдээллийн санд",               # in the State database — "Улсын" is "State"
    "бусдад дамжуулж болно",               # may transfer to others
    "гадаад, дотоодын ижил чиг үүрэгтэй байгууллагуудтай",   # foreign and domestic ORGANISATIONS
    "向第三方转移儿童个人信息",             # to a third party
    "disclose personal data about an individual without the individual's consent",
    "the place or location where PD is stored",
    "",
    None,
])
def test_words_that_name_no_place(quote):
    assert not names_place(quote)
