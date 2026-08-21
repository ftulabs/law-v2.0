"""Discovery Tag at provision level, against the panel's own 2025 databases.

The old rule matched a law name and a URL, with no article anywhere in the signature. So when
our tool independently surfaced a provision the panel had not cited, we reported it as something
we were handed. This is the column that says whether a row is a discovery; getting it wrong
costs credit in the direction we can least afford.
"""
import pytest

from backend.rdtii import baseline as B


# ── the numeric spine, across four drafting conventions ──────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("Section 199", {"199"}),
    ("Section 199; Section 4", {"199", "4"}),
    ("s. 26(1)", {"26", "26(1)"}),                  # the bare article too, so "Section 26" hits
    ("Art. 26(2)", {"26", "26(2)"}),
    ("Article 20.1.5", {"20", "20.1.5"}),           # 20.1.5 also answers to article 20
    ("Regulation 53(2)", {"53", "53(2)"}),
    ("Section 187C; Section 187AA", {"187c", "187aa"}),
    ("APP 8", {"app8"}),
    ("", set()),
])
def test_spine_normalises_latin_citations(text, expected):
    assert B.article_spine(text) == expected


@pytest.mark.parametrize("han,arabic", [
    ("第一条", "1"), ("第十条", "10"), ("第二十七条", "27"), ("第四十条", "40"),
    ("第五十二条", "52"), ("第一百零一条", "101"), ("第40条", "40"),
])
def test_chinese_han_numerals_reduce_to_the_panels_arabic_form(han, arabic):
    """Our extractor emits the statute's own heading, 第四十条; the panel's database records
    'Article 40'. Without the conversion, no Chinese provision could ever match the baseline."""
    assert arabic in B.article_spine(han)


def test_mongolian_article_heading_reduces_to_its_number():
    assert "14" in B.article_spine("14 дүгээр зүйл")
    assert "20" in B.article_spine("20 дугаар зүйл")


def test_label_words_do_not_affect_the_spine():
    assert B.article_spine("Section 26") == B.article_spine("s. 26") == B.article_spine("Art. 26")


# ── the four outcomes ────────────────────────────────────────────────────────────────
def test_law_and_article_both_cited_is_known():
    tag, note = B.classify("Singapore", "P6-I4", "Personal Data Protection Act 2012", "Section 26")
    assert tag == "KNOWN" and note is None


def test_same_law_different_article_is_a_discovery():
    """The definition is about the provision — "not in the 2025 baseline". Reporting KNOWN here
    is exactly the giveaway this module exists to stop. The note keeps it honest."""
    tag, note = B.classify("Singapore", "P6-I4",
                           "Personal Data Protection Act 2012", "Section 11(3)")
    assert tag == "NEW"
    assert note and "different article" in note


def test_law_cited_without_any_article_is_known_and_says_so():
    """Unknowable, so we do not claim the discovery — overstating is the error a judge can
    check by opening the database they wrote."""
    tag, note = B.classify("Singapore", "P7-I1", "Personal Data Protection Act 2012", "Section 99")
    assert tag == "KNOWN"
    assert note and "without naming an article" in note


def test_law_absent_from_the_baseline_is_new():
    tag, note = B.classify("Singapore", "P6-I4", "Some Act We Invented 2024", "Section 3")
    assert tag == "NEW" and note is None


@pytest.mark.parametrize("economy,indicator,law,section", [
    ("Australia", "P6-I4", "Privacy Act 1988", "APP 8"),
    ("Australia", "P6-I1", "My Health Records Act 2012", "Section 77"),
    ("Singapore", "P6-I2", "Companies Act 1967", "Section 199"),
    ("China", "P6-I2", "Personal Information Protection Law", "第四十条"),
    ("Mongolia", "P6-I4", "Law on Personal Data Protection", "14 дүгээр зүйл"),
])
def test_the_panels_own_answer_key_reads_as_known(economy, indicator, law, section):
    """Every one of these is a citation the panel wrote down. If any reads NEW, the matcher is
    broken in the expensive direction — we would be claiming their answers as our discoveries."""
    assert B.classify(economy, indicator, law, section)[0] == "KNOWN"


def test_an_economy_outside_the_baseline_is_all_new():
    assert B.classify("Thailand", "P6-I1", "Anything", "Section 1") == ("NEW", None)


def test_missing_baseline_file_degrades_instead_of_crashing():
    B.load.cache_clear()
    try:
        assert B.load("does/not/exist.csv") == {}
    finally:
        B.load.cache_clear()


def test_baseline_actually_loaded():
    s = B.stats()
    assert s["rows"] == 180 and s["rows_with_article"] == 101
    assert len(s["economies"]) == 6
