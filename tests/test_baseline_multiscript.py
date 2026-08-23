"""Discovery Tag across scripts: claiming the panel's own laws as our discoveries.

`baseline.law_tokens` was `[a-z]{3,}`. For 中华人民共和国个人信息保护法 that returns the EMPTY
SET, `_same_law` refuses an empty set, and every Chinese, Mongolian and Russian provision was
therefore tagged NEW — including the ones the panel's database cites by name. A China pillar-7
run reported KNOWN=1 NEW=21 and neither number looked like a bug.

That is the module's own stated error, inverted. It exists to stop us GIVING AWAY credit when
the panel cites PDPA s.26 and we independently find s.11(3); this made us CLAIM credit for
PIPL. Overstating our own discovery is the error a judge can check by opening the database
they wrote.
"""
import pytest

from backend.rdtii import baseline


@pytest.fixture(autouse=True)
def _fresh():
    baseline.load.cache_clear()
    yield
    baseline.load.cache_clear()


@pytest.mark.parametrize("economy, indicator, law, article", [
    ("China", "P6-I4", "中华人民共和国个人信息保护法", "第三十八条"),
    ("China", "P6-I4", "中华人民共和国个人信息保护法", "第四十条"),
    ("China", "P7-I2", "中华人民共和国网络安全法", "第二十一条"),
    ("China", "P7-I1", "中华人民共和国数据安全法", "第二十七条"),
    ("China", "P7-I5", "中华人民共和国反间谍法", "第二十五条"),
])
def test_a_law_the_panel_cites_is_not_reported_as_our_discovery(economy, indicator, law, article):
    tag, _note = baseline.classify(economy, indicator, law, article)
    assert tag == "KNOWN"


def test_the_english_half_of_a_bilingual_entry_still_matches():
    """The baseline records both forms — `Personal Information Protection Law of the People's
    Republic of China《中华人民共和国个人信息保护法》` — so a run that names the law in English
    must keep matching through the English half."""
    tag, _ = baseline.classify("China", "P6-I4",
                               "Personal Information Protection Law of the People's Republic "
                               "of China", "Article 38")
    assert tag == "KNOWN"


def test_two_different_laws_sharing_the_formal_prefix_stay_distinct():
    """中华人民共和国 is seven characters on the front of every national law — six identical
    bigrams shared by laws with nothing else in common. Left in, the Cybersecurity Law and the
    Data Security Law overlap 8/11 = 0.73, one shared character below the 0.75 threshold."""
    cyber = baseline.law_tokens("中华人民共和国网络安全法")
    data = baseline.law_tokens("中华人民共和国数据安全法")
    assert cyber and data
    assert not baseline._same_law(cyber, data)


def test_a_law_matches_its_own_baseline_entry_exactly():
    ours = baseline.law_tokens("中华人民共和国个人信息保护法")
    theirs = baseline.law_tokens(
        "Personal Information Protection Law of the People's Republic of China"
        "《中华人民共和国个人信息保护法》")
    assert baseline._same_law(ours, theirs)


def test_a_chinese_name_produces_tokens_at_all():
    """The whole failure in one assertion: the old tokeniser returned frozenset()."""
    assert baseline.law_tokens("中华人民共和国个人信息保护法")


@pytest.mark.parametrize("economy, indicator, law, article, tag", [
    ("Singapore", "P7-I1", "Personal Data Protection Act 2012", "Section 26", "KNOWN"),
    ("Singapore", "P7-I2", "Cybersecurity Act 2018", "Section 7", "KNOWN"),
    ("Australia", "P7-I1", "Privacy Act 1988", "APP 8", "KNOWN"),
])
def test_the_latin_script_economies_are_unchanged(economy, indicator, law, article, tag):
    assert baseline.classify(economy, indicator, law, article)[0] == tag


def test_an_unrelated_law_is_still_new():
    assert baseline.classify("China", "P6-I2", "数据出境安全评估办法", "第二条")[0] == "NEW"
    assert baseline.classify("Singapore", "P7-I1", "Road Traffic Act 1961", "Section 3")[0] == "NEW"


# ── the portal's own id, for a language the reference file does not speak ──────────────────

@pytest.mark.parametrize("url, expect", [
    ("https://legalinfo.mn/mn/detail?lawId=16390288615991", "legalinfo.mn#16390288615991"),
    ("https://legalinfo.mn/mn/detail/523", "legalinfo.mn#523"),
    ("https://legalinfo.mn/en/edtl/16531350476261", "legalinfo.mn#16531350476261"),
    # The identity is the wrapped URL; the archive is packaging.
    ("https://web.archive.org/web/20250301225053/https://legalinfo.mn/mn/detail?lawId=99",
     "legalinfo.mn#99"),
    ("https://indiacode.gov.in/handle/123456789/512146", "indiacode.gov.in#512146"),
    # A dated news path is a page name, not an id — too weak to assert identity on, so it
    # falls back to comparing names rather than guessing.
    ("https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm", ""),
    ("", ""),
])
def test_the_portal_id_is_read_out_of_the_url(url, expect):
    assert baseline.url_key(url) == expect


@pytest.mark.parametrize("indicator, article", [
    ("P6-I4", "14 дүгээр зүйл"),
    ("P6-I2", "20 дугаар зүйл"),
    ("P7-I1", ""),
])
def test_mongolia_matches_through_the_portal_id(indicator, article):
    """The reference file writes "Law on Personal Data Protection"; the portal, and therefore
    our run, writes ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ. The two share no characters, so no
    tokeniser can match them — but both cite lawId=16390288615991. Without this every Mongolian
    row is reported as our own discovery."""
    tag, _ = baseline.classify("Mongolia", indicator,
                               "ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ", article,
                               "https://legalinfo.mn/mn/detail?lawId=16390288615991")
    assert tag == "KNOWN"


def test_a_different_law_on_the_same_portal_is_still_new():
    """The id has to identify, not merely share a host."""
    tag, _ = baseline.classify("Mongolia", "P6-I4", "ГААЛИЙН ТУХАЙ", "5 дугаар зүйл",
                               "https://legalinfo.mn/mn/detail?lawId=99999")
    assert tag == "NEW"


def test_the_url_is_optional():
    """Every caller before this change passed four arguments, and the name path must keep
    working on its own — China matches through the Chinese half of a bilingual entry."""
    assert baseline.classify("China", "P6-I4", "中华人民共和国个人信息保护法", "第三十八条")[0] == "KNOWN"
