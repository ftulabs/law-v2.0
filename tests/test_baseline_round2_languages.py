"""The 2025 baseline for Thailand, Indonesia, Laos and Russia — read, and actually matchable.

Two defects, found 2026-09-29, both silent. The reference file read only three of the seven
economies in the panel's Round-2 Database, so every Thai, Indonesian, Lao and Russian row was
NEW by default. And once those rows were added, almost nothing matched them anyway: "มาตรา 28",
"Статья 12" and "Pasal 35" reduced to no article at all, the panel cites Indonesian law by a
JDIH BPK URL whose id sits before a slug, and it names Russian law "No. 152-FZ" where the portal
writes "№ 152-ФЗ". Measured on the 2026-09-26 outputs: KNOWN went TH 1→17, RU 0→17, ID 0→13.
"""
import pytest

from backend.rdtii import baseline as B


@pytest.mark.parametrize("text, expect", [
    ("มาตรา 28", {"28"}),
    ("มาตรา ๒๘", {"28"}),                        # Thai digits
    ("ມາດຕາ ໑໒", {"12"}),                        # Lao label, Lao digits
    ("Статья 22.1", {"22.1", "22"}),
    ("Pasal 14(1)", {"14(1)", "14"}),
    ("Pasal 35 ayat (2)", {"35(2)", "35"}),
    ("Section 26 (1)", {"26(1)", "26"}),
])
def test_native_article_labels_reduce_to_the_same_spine(text, expect):
    assert B.article_spine(text) == expect


def test_an_id_before_a_slug_is_the_identity():
    assert (B.url_key("https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022")
            == "peraturan.bpk.go.id#229798")


def test_a_gazette_file_path_is_not_mistaken_for_an_id():
    assert B.url_key("http://www.ratchakitcha.soc.go.th/DATA/PDF/2562/A/069/T_0052.PDF") == ""


def test_every_url_in_a_cell_counts():
    keys = B.url_keys("http://jdih.kkp.go.id/peraturan/pp-46-2014.pdf; "
                      "https://peraturan.bpk.go.id/Details/5461/pp-no-46-tahun-2014")
    assert "peraturan.bpk.go.id#5461" in keys


def test_a_federal_law_number_is_the_same_in_either_script():
    assert B.law_numbers("Федеральный закон от 27.07.2006 № 152-ФЗ") == {"152-fz"}
    assert B.law_numbers('Federal Law No. 152-FZ "On Personal Data"') == {"152-fz"}
    assert not B.law_numbers("Law No. 27 of 2022")


def test_all_seven_round2_economies_are_in_the_baseline():
    econ = {e for e, _ in B.load()}
    assert {"Thailand", "Indonesia", "Lao People's Democratic Republic",
            "Russian Federation", "China", "India", "Mongolia"} <= econ


def test_thai_pdpa_section_28_is_known():
    tag, note = B.classify("Thailand", "P6-I4",
                           "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. ๒๕๖๒", "มาตรา 28",
                           "https://www.law.go.th/DetailLawPage?table_of_law_id=382")
    assert (tag, note) == ("KNOWN", None)


def test_russian_152_fz_is_matched_by_its_number():
    tag, _ = B.classify("Russian Federation", "P6-I4", "О персональных данных", "Статья 12",
                        "http://pravo.gov.ru/proxy/ips/?doc_itself=&nd=102108261",
                        law_number="Федеральный закон от 27.07.2006 № 152-ФЗ")
    assert tag == "KNOWN"


def test_indonesian_pdp_law_is_matched_by_its_bpk_id():
    tag, _ = B.classify("Indonesia", "P7-I1", "Undang-undang (UU) Nomor 27 Tahun 2022",
                        "Pasal 35",
                        "https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022")
    assert tag == "KNOWN"


def test_a_different_russian_law_is_still_new():
    tag, _ = B.classify("Russian Federation", "P6-I4", "О банках и банковской деятельности",
                        "Статья 26", "http://pravo.gov.ru/proxy/ips/?nd=1",
                        law_number="Федеральный закон № 395-1")
    assert tag == "NEW"
