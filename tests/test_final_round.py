"""Final-round compliance: the nine live-test economies, and the output the panel validates.

Two kinds of test live here. The first kind pins a FORMAT the secretariat checks
programmatically — a column name, an indicator code — where being wrong costs the row even
though the underlying finding is right. The second kind pins a SILENT defect: a missing table
entry or an off-language model that produces plausible output and reports no error at all.
"""
import re

import pytest

from backend.providers import engine_profile as EP
from backend.providers.ocr_languages import PROFILES, is_english_text, is_latin_script, profile_for
from backend.rdtii import codes, instrument
from backend.schemas import (ECONOMY_UN_NAME, LIVE_TEST_NINE, SUBMISSION_COLUMNS, Economy,
                             resolve_economy)


# ── the nine ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code", LIVE_TEST_NINE)
def test_every_live_test_economy_is_declarable(code):
    """"Be ready for any of the nine." An economy that cannot even be named is not a thin
    pass, it is a zero, and six of the nine were undeclared until now."""
    assert code in ECONOMY_UN_NAME
    assert Economy(code)


@pytest.mark.parametrize("typed,expected", [
    ("Thailand", "TH"), ("Viet Nam", "VN"), ("Vietnam", "VN"), ("Indonesia", "ID"),
    ("Kazakhstan", "KZ"), ("Lao PDR", "LA"), ("Laos", "LA"),
    ("Lao People's Democratic Republic", "LA"), ("Russian Federation", "RU"), ("Russia", "RU"),
])
def test_the_names_a_steward_will_actually_type_resolve(typed, expected):
    assert resolve_economy(typed).value == expected


def test_un_names_match_the_instructions_exactly():
    """The Instructions sheet names two spellings itself, and both are easy to get wrong:
    "Viet Nam" is two words with no circumflex, and Lao PDR's UN name is not "Laos"."""
    assert ECONOMY_UN_NAME["VN"] == "Viet Nam"
    assert ECONOMY_UN_NAME["LA"] == "Lao People's Democratic Republic"


@pytest.mark.parametrize("code", LIVE_TEST_NINE)
def test_every_live_test_economy_has_its_own_language_profile(code):
    """Kazakhstan had no entry, so profile_for("KZ") returned the Latin default: Cyrillic text
    would have been called Latin script, handed to an English cross-encoder, and reported as
    English in the Language of Source column. A missing key is silent in all three places."""
    assert code in PROFILES, f"{code} falls through to the Latin default"


# ── language is not script ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("code", ["SG", "AU", "MY", "IN"])
def test_english_economies_take_the_english_lane(code):
    assert EP.profile_for(code).lane == EP.LANE_ENGLISH


@pytest.mark.parametrize("code", ["VN", "ID"])
def test_latin_script_but_not_english_takes_the_non_english_lane(code):
    """The defect this pins: both economies write in Latin letters, so a script-keyed lane put
    them on the English cross-encoder. That model's score is fused at the same weight as BM25,
    so an off-language reranker makes the ranking worse — it does not merely fail to help."""
    assert is_latin_script(code) and not is_english_text(code)
    assert EP.profile_for(code).lane == EP.LANE_NON_ENGLISH
    from backend.pipeline import ranking
    assert ranking._ce_model_for(code) is None


@pytest.mark.parametrize("code", LIVE_TEST_NINE)
def test_no_economy_reports_a_language_it_does_not_speak(code):
    """Language of Source is a REQUIRED column driving criterion C1c. Indonesia inherited the
    Latin default, whose language field says "English"."""
    lang = EP.profile_for(code).language_of_source
    assert lang and lang != ""
    if code == "ID":
        assert lang == "Indonesian"
    if code == "KZ":
        assert lang == "Kazakh"


# ── OCR: no script may be a dead end ─────────────────────────────────────────────────
@pytest.mark.parametrize("code", LIVE_TEST_NINE)
def test_every_live_test_economy_resolves_a_real_ocr_engine(code):
    """"No installed engine can read this script" is honest and useless: the live test names
    one economy of nine and gives an hour. A vision model has no per-script dictionary, so it
    closes every remaining gap in one place."""
    from backend.providers.ocr_factory import UnavailableOCR, get_ocr_provider
    provider = get_ocr_provider(economy=code)
    assert not isinstance(provider, UnavailableOCR), getattr(provider, "reason", "")


@pytest.mark.parametrize("code", ["MN", "KZ"])
def test_paddle_is_disqualified_for_mongolian_and_kazakh_by_measurement(code):
    """Measured against eslav_PP-OCRv5_mobile_rec's own 517-character dictionary: Ө Ү ө ү are
    absent (Mongolian loses four letters) and sixteen Kazakh letters are absent. Setting a
    paddle code here would produce fluent text missing letters, with no error raised."""
    assert profile_for(code).paddle is None


def test_paddle_language_keys_match_the_installed_paddleocr():
    """The registry said paddle="cyrillic"/"eslav". PaddleOCR 3.x raises ValueError on both,
    the factory caught it, and the run reported "no engine can read Cyrillic" — while the
    engine sat installed the whole time under a different key."""
    assert profile_for("RU").paddle == "ru"


def test_vietnamese_never_routes_to_a_latin_recogniser():
    """latin_PP-OCRv5_mobile_rec carries đ ă ơ ư but none of the 45 precomposed tone forms, so
    a Vietnamese verbatim snippet cannot survive it. paddle lang "vi" loads that very model
    without raising, which is why this is pinned rather than left to the note."""
    p = profile_for("VN")
    assert p.paddle is None and p.rapidocr is None
    assert "vlm" in p.preferred


# ── indicator codes ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("internal,numeric", [
    ("P6-I1", "6.1"), ("P6-I4", "6.4"), ("P7-I2", "7.2"), ("P7-I5", "7.5"),
    ("P12-I9", "12.9"), ("P6_I2", "6.2"), ("6.4", "6.4"), ("12.10", "12.10"), ("4.01", "4.01"),
])
def test_indicator_ids_convert_to_the_template_form(internal, numeric):
    assert codes.to_rdtii_code(internal) == numeric


def test_codes_stay_text_so_12_10_does_not_collapse():
    """"Entered as a number, 12.10 collapses to 12.1 and 4.01 to 4.1, and those are different
    indicators." So the exporter must never round-trip through a float."""
    assert codes.to_rdtii_code("12.10") != codes.to_rdtii_code("12.1")
    assert codes.to_rdtii_code("4.01") != codes.to_rdtii_code("4.1")
    assert isinstance(codes.to_rdtii_code("12.10"), str)


def test_the_sixty_one_in_scope_codes_are_loaded():
    known = codes.official_codes()
    assert len(known) == 61
    assert {"6.1", "6.2", "6.3", "6.4", "7.1", "7.2", "7.3", "7.4", "7.5"} <= known


def test_a_non_regulatory_code_is_not_a_valid_target():
    """6.5 (binding commitments) and 12.10 are third-party-sourced indicators the panel's own
    PDF places outside automated retrieval. A row claiming one is a scoring error, not a find."""
    assert not codes.is_valid("6.5")
    assert not codes.is_valid("12.10")


@pytest.mark.parametrize("code", ["P6-I1", "P6-I2", "P6-I3", "P6-I4",
                                  "P7-I1", "P7-I2", "P7-I3", "P7-I4", "P7-I5"])
def test_every_indicator_we_ship_maps_to_a_real_rdtii_code(code):
    assert codes.is_valid(codes.to_rdtii_code(code))


# ── unscoreable instruments ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,status", [
    ("Personal Data Protection Act 2012", instrument.Status.SCOREABLE),
    ("Personal Data Protection (Amendment) Act 2020", instrument.Status.AMENDING),
    ("Personal Data Protection (Amendment No. 2) Act 2021", instrument.Status.AMENDING),
    ("An Act to amend the Privacy Act 1988", instrument.Status.AMENDING),
    ("Cybersecurity Bill 2017", instrument.Status.DRAFT),
    ("Draft Personal Data Protection Regulations", instrument.Status.DRAFT),
    ("Data Protection Repeal Act 2019", instrument.Status.REPEALED),
])
def test_unscoreable_instruments_are_recognised(name, status):
    assert instrument.classify(name) is status


@pytest.mark.parametrize("name", [
    "个人信息保护法修正案",                                    # zh
    "Закон о внесении изменений в Федеральный закон",          # ru
    "Luật sửa đổi, bổ sung một số điều của Luật An ninh mạng",  # vi
    "Undang-Undang tentang Perubahan atas UU ITE",             # id
    "Akta Perlindungan Data Peribadi (Pindaan) 2024",          # ms
])
def test_amending_acts_are_caught_in_the_statute_language(name):
    """Six of the nine do not legislate in English, and an amending act in Chinese scores
    exactly as much as one in English: nothing."""
    assert instrument.classify(name) is instrument.Status.AMENDING


def test_a_principal_act_that_merely_mentions_repeal_stays_scoreable():
    """Principal acts repeal their predecessors as a matter of routine drafting. Disqualifying
    on the word alone would throw away the instrument the indicator is actually about."""
    assert instrument.is_scoreable("Companies Act 1967 which repeals the 1940 Ordinance")
    assert instrument.is_scoreable("Personal Data Protection Act 2012")


def test_the_amending_note_tells_a_reviewer_what_to_do():
    """The finding is usually right and only the citation is wrong, so the row is annotated
    rather than dropped — and the note has to say which act to cite instead."""
    note = instrument.note_for(instrument.Status.AMENDING)
    assert note and "principal" in note.lower()


# ── the workbook ─────────────────────────────────────────────────────────────────────
def test_submission_columns_match_the_final_round_template():
    """Thirteen Round-1 columns unchanged and in the same order, plus Language of Source."""
    assert len(SUBMISSION_COLUMNS) == 14
    assert SUBMISSION_COLUMNS[-1] == "Language of Source"
    assert SUBMISSION_COLUMNS[:13] == [
        "Economy", "Law Name", "Law Number / Ref", "Last Amended", "Indicator ID",
        "Article / Section", "Discovery Tag", "Location Reference", "Verbatim Snippet",
        "Mapping Rationale", "Source URL", "Confidence", "Notes"]


def test_we_do_not_write_the_auto_pillar_column():
    """Column O carries a formula deriving the pillar from the Indicator ID, and the Coverage
    Matrix reads its output. Writing a literal there would overwrite the formula and empty
    every coverage count without any error."""
    assert not any(c.lower().startswith("pillar") for c in SUBMISSION_COLUMNS)


def test_exported_row_carries_the_numeric_code_and_the_language():
    from backend.export.csv_export import _row
    from backend.schemas import ConfidenceBreakdown, DiscoveryTag, EvidenceMapping, ReviewStatus
    m = EvidenceMapping(
        mapping_id="m1", run_id="r1", economy=Economy.VN, pillar=6, indicator_id="P6-I4",
        law_name="Luật An ninh mạng 2018", article_section="Điều 26", verbatim_snippet="…",
        source_url="https://example.test/x", mapping_rationale="…", confidence_score=0.9,
        discovery_tag=DiscoveryTag.NEW, review_status=ReviewStatus.AUTO_ACCEPTED,
        provision_id="p1", confidence=ConfidenceBreakdown())
    row = _row(m)
    assert row["Indicator ID"] == "6.4"
    assert row["Language of Source"] == "Vietnamese"
    assert row["Economy"] == "Viet Nam"


def test_an_amending_act_row_is_annotated_on_export():
    from backend.export.csv_export import _row
    from backend.schemas import ConfidenceBreakdown, DiscoveryTag, EvidenceMapping, ReviewStatus
    m = EvidenceMapping(
        mapping_id="m2", run_id="r1", economy=Economy.SG, pillar=7, indicator_id="P7-I4",
        law_name="Personal Data Protection (Amendment) Act 2020", article_section="s. 5",
        verbatim_snippet="…", source_url="https://example.test/y", mapping_rationale="…",
        confidence_score=0.9, discovery_tag=DiscoveryTag.NEW,
        review_status=ReviewStatus.AUTO_ACCEPTED, provision_id="p2",
        confidence=ConfidenceBreakdown())
    assert "principal" in _row(m)["Notes"].lower()


# ── tokenisation, for the Latin-script economies that are not English ─────────────────
def test_vietnamese_words_survive_tokenisation():
    """"dữ liệu được chuyển" tokenised as ['d','li','u','đư','c','chuy','n'] — every diacritic
    split the word. Unlike the Chinese zero this returns plausible non-zero scores from
    one-letter fragments that match any document, so nothing reports a problem."""
    from backend.pipeline import retrieval
    toks = retrieval._tok("Dữ liệu cá nhân không được chuyển ra ngoài lãnh thổ")
    assert "dữ" in toks and "liệu" in toks and "được" in toks and "chuyển" in toks
    assert not any(len(t) == 1 for t in toks)


def test_portuguese_and_spanish_diacritics_survive_too():
    from backend.pipeline import retrieval
    assert "proteção" in retrieval._tok("Artigo 1.º proteção de dados")


def test_ascii_tokenisation_is_still_bit_identical_to_round1():
    """The retrieval parameters were swept against this exact tokenisation, so widening the
    branch is only safe because the added code points cannot occur in ASCII text."""
    from backend.pipeline import retrieval
    t = "Personal data shall not be transferred outside Singapore under s26(1) of the PDPA."
    assert retrieval._tok(t) == re.compile(r"[a-z0-9]+").findall(t.lower())


# ── the README is a graded deliverable, so it gets tests ─────────────────────────────
def _readme() -> str:
    from backend.config import ROOT
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_line_references_still_point_where_they_claim():
    """The "Crawling Politely" table cites file:line, and criterion C4a is marked by someone
    reading it. A line reference that has drifted is worse than none — it sends a reviewer to
    an unrelated line and reads as carelessness about the very claim being made."""
    import re

    from backend.config import ROOT
    expectations = {
        "backend/config.py": "crawl_delay_seconds",
        "backend/pipeline/robots.py": None,
    }
    refs = re.findall(r"\((backend/[\w/]+\.py)#L(\d+)\)", _readme())
    assert refs, "the politeness table lost its file:line references"
    for path, line in refs:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        n = int(line)
        assert 1 <= n <= len(lines), f"{path}#L{n} is past the end of the file"
        body = lines[n - 1].strip()
        assert body and not body.startswith("#"), f"{path}#L{n} points at a blank or comment line"
        marker = expectations.get(path)
        if marker:
            assert marker in body, f"{path}#L{n} no longer contains {marker!r}"


def test_readme_documents_all_fourteen_columns_in_order():
    """The output table in the README is what a reviewer checks our CSV against, so it must not
    drift from SUBMISSION_COLUMNS."""
    body = _readme()
    start = body.index("| # | Column | Required | Description |")
    table = body[start:body.index("\n\n", start)]
    for i, col in enumerate(SUBMISSION_COLUMNS, 1):
        assert f"| {i} | {col} |" in table, f"README is missing column {i} ({col})"


def test_readme_states_the_final_round_not_round_one():
    body = _readme()
    assert "Round: **Final**" in body
    assert "P6-I1" not in body.split("## Output Format")[1].split("## Measured Cost")[0] \
        or "Never `P6-I1`" in body
