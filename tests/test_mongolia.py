"""Mongolia — the export route, and the two silent failures it already produced.

Every case here is pinned because the bug it guards produced NO error: legalinfo.mn returns
200 and plausible Cyrillic in all three of the wrong states, so the run completes, the CSV
writes, and every indicator reads "No provision found" — which is indistinguishable from an
economy that has no such law. Offline throughout; the bytes are the shape the portal returns.
"""
import re

import pytest

from backend.pipeline import adapter_mongolia as mn
from backend.pipeline.extraction import _STRUCT_RE_MN, _boundaries
from backend.schemas import Economy

# What /mn/downloadFile actually returns: labelled .doc, bytes are Word-flavoured HTML.
EXPORT = ("<html xmlns:o='urn:schemas-microsoft-com:office:office'><body>"
          "<p>{worksheet}</p>"
          "<p>ХҮНИЙ ХУВИЙН МЭДЭЭЛЭЛ ХАМГААЛАХ ТУХАЙ</p>"
          "<p>1 дүгээр зүйл. Хуулийн зорилт</p>"
          "<p>1.1. Энэ хуулийн зорилт нь хувь хүний мэдээллийг хамгаалахтай холбогдсон "
          "харилцааг зохицуулахад оршино.</p>"
          "<p>2 дугаар зүйл. Хууль тогтоомж</p>"
          "<p>2.1. Үндсэн хуулийн Арван зургадугаар зүйлийн 17 дахь хэсэгт заасны дагуу.</p>"
          "<p>3 дугаар зүйл. Хилийн чанад дахь дамжуулалт</p>"
          "<p>3.1. Хувь хүний мэдээллийг хилийн чанадад дамжуулахыг хориглоно.</p>"
          "</body></html>").encode("utf-8")


# ── the failure that cost the whole corpus ───────────────────────────────────────────
def test_the_export_keeps_line_breaks_because_the_article_pattern_is_line_anchored():
    """The first version flattened the document with a single `\\s+ → " "`. It returned 34,196
    characters of perfectly good Mongolian for the Personal Data Protection Law, from which
    zero articles were found — the pattern is anchored to `^` to keep cross-references out, and
    a law arriving as one enormous line has exactly one line start."""
    text = mn.export_text(EXPORT)
    assert "\n" in text, "block elements must survive as line breaks"
    assert len(_STRUCT_RE_MN.findall(text)) == 3


def test_the_export_marker_is_not_mistaken_for_statutory_text():
    assert "{worksheet}" not in mn.export_text(EXPORT)


def test_a_flattened_export_would_have_found_nothing():
    """The counter-example, stated so the guard above cannot be quietly relaxed."""
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", EXPORT.decode("utf-8")))
    assert _STRUCT_RE_MN.findall(flat) == []


# ── the article pattern itself ───────────────────────────────────────────────────────
@pytest.mark.parametrize("line,expected", [
    ("14 дүгээр зүйл. Мэдээлэл хамгаалах", "14 дүгээр зүйл"),      # modern, digits
    ("26 дугаар зүйл", "26 дугаар зүйл"),                          # the other vowel harmony
    ("Хоёрдугаар зүйл", "Хоёрдугаар зүйл"),                        # 1940 Constitution, art. 2
    ("Гучингуравдугаар зүйл", "Гучингуравдугаар зүйл"),            # art. 33, one compound word
    ("Арван нэгдүгээр зүйл", "Арван нэгдүгээр зүйл"),              # art. 11, two words
])
def test_spelled_out_ordinals_are_headings_too(line, expected):
    """A digits-only pattern found nothing in the constitutions, so the whole instrument
    collapsed into one block with no error reported anywhere."""
    m = _STRUCT_RE_MN.search(line)
    assert m and m.group(1) == expected


@pytest.mark.parametrize("line", [
    "9 дүгээр зүйлийн 1 дэх хэсэгт заасны дагуу",       # genitive — a cross-reference
    "26 дугаар зүйлд заасан журмаар",                    # dative — also a cross-reference
])
def test_a_cross_reference_is_not_an_article_boundary(line):
    """Mongolian preambles open by citing another Act. Treating that as a heading splits the
    recital off as its own provision and mis-scopes everything after it."""
    assert _STRUCT_RE_MN.search(line) is None


def test_an_english_translation_falls_back_to_the_latin_pattern():
    """legalinfo.mn also serves English texts (the Cyber Security law is one). Those carry
    "Article 1." and no зүйл at all, so the MN branch must not simply return nothing."""
    english = ("LAW OF MONGOLIA ON CYBER SECURITY\nCHAPTER ONE\n"
               "Article 1. Purpose of the law\n1.1. The purpose of this law is to regulate...\n"
               "Article 2. Legislation\n2.1. The legislation consists of...\n"
               "Article 3. Definitions\n3.1. In this law...\n")
    assert len(_boundaries(english, Economy.MN)) >= 3


# ── the catalogue ────────────────────────────────────────────────────────────────────
def test_titles_match_on_a_stem_because_mongolian_is_agglutinative():
    title = "Хувь хүний мэдээлэл хамгаалах тухай хууль"
    assert mn._matches(title, "хувь хүний мэдээлэл")
    assert mn._matches(title, "ХУВЬ ХҮНИЙ")                 # case-folded
    assert not mn._matches(title, "мэдээллийг")             # inflected — will not match


def test_an_unresolved_law_id_is_reported_as_absent_not_as_an_empty_law(monkeypatch):
    """An id that does not exist still answers 200, with a short shell and an EMPTY filename.
    Length alone is a fragile test — a one-line presidential decree is legitimately short — so
    the empty filename is what distinguishes the two."""
    class Resp:
        status_code = 200
        headers = {"content-disposition": 'attachment; filename=".doc"'}
        content = b"x" * 6768

    class Client:
        def post(self, url, headers=None):
            return Resp()

    assert mn.export_law(Client(), "20001") == ("", b"")


def test_the_source_url_is_the_page_a_reviewer_can_open_not_the_post_export():
    doc = mn._doc("16390288615991", "Хувь хүний мэдээлэл хамгаалах тухай",
                  Economy.MN, "Unified Legal Information System")
    assert doc.source_url == "https://legalinfo.mn/mn/detail?lawId=16390288615991"
    assert "downloadFile" not in doc.source_url
    assert doc.law_name == "Хувь хүний мэдээлэл хамгаалах тухай"
