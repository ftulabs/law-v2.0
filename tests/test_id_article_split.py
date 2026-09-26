"""Indonesian article splitting on BPK gazette text (defects measured 2026-09-26)."""
from backend.pipeline.extraction import extract_provisions
from backend.schemas import DiscoveredDoc, DocFormat, Economy, OCRMetrics

FILL = "Penyelenggara Sistem Elektronik wajib melaksanakan ketentuan ini dengan baik.\n"


def _split(text):
    doc = DiscoveredDoc(doc_id="ID-t", economy=Economy.ID, title="Peraturan Menteri",
                        source_url="https://peraturan.bpk.go.id/Download/1/x.pdf", portal="x",
                        fmt=DocFormat.PDF_TEXT)
    return extract_provisions(doc, text, OCRMetrics(used=False, provider="none", pages=3,
                                                    chars=len(text)))


def _body(n):
    return "".join(f"Pasal {i}\n{FILL * 2}" for i in range(1, n + 1))


def test_a_wrapped_cross_reference_is_not_a_new_article():
    text = (_body(16) + "Pasal 17\n(1) Pusat data Penyelenggara Sistem Elektronik untuk pelayanan "
            "publik sebagaimana dimaksud dalam\nPasal 3 wajib ditempatkan dalam wilayah negara "
            "Republik Indonesia.\n" + FILL + "Pasal 18\n" + FILL * 2)
    ps = {p.article_section: p.verbatim_snippet for p in _split(text)}
    assert "wajib ditempatkan dalam wilayah" in ps["Pasal 17"]
    assert list(ps).count("Pasal 3") == 1


def test_the_page_catchword_gives_way_to_the_real_heading():
    text = (_body(20) + "...\nPasal 21\n\n\x0c18\x0c\nREPUBLIK INDONESIA\n-18-\nPasal 21\n(1) "
            + FILL * 2 + "Pasal 22\n" + FILL * 2)
    labels = [p.article_section for p in _split(text)]
    assert labels.count("Pasal 21") == 1


def test_the_elucidation_is_cut_off():
    body = _body(40) + "Pasal 41\nPeraturan Pemerintah ini mulai berlaku pada tanggal diundangkan.\n"
    elu = ("\nP E N J E L A S A N\nATAS\nPERATURAN PEMERINTAH\nI. UMUM\n"
           "wajib menempatkan pusat data di wilayah Indonesia.\nII. PASAL DEMI PASAL\n"
           + "".join(f"Pasal {i}\nCukup jelas.\n" for i in range(1, 42)))
    ps = _split(body + elu)
    assert [p.article_section for p in ps].count("Pasal 1") == 1
    assert "pusat data" not in ps[-1].verbatim_snippet


def test_misread_digits_are_repaired_in_the_label_only():
    text = _body(69) + "Pasal 7O\nSetiap Orang dilarang menjual Data Pribadi milik orang lain.\n" + FILL
    last = _split(text)[-1]
    assert last.article_section == "Pasal 70"


def test_an_indonesian_localisation_rule_is_on_topic_for_pillar_6():
    # PP 71/2019 art. 20(2), quarantined as "no pillar concept terms" on 2026-09-26
    from backend.pipeline.confidence import topical_grounded
    s = ("(2) Penyelenggara Sistem Elektronik Lingkup Publik wajib melakukan pengelolaan, "
         "pemrosesan, dan/atau penyimpanan Sistem Elektronik dan Data Elektronik di wilayah "
         "Indonesia.")
    assert topical_grounded(s, 6)


def test_an_annex_is_split_into_its_own_entries_not_left_in_the_last_article():
    body = _body(7) + "Pasal 8\nPeraturan Menteri ini mulai berlaku pada tanggal diundangkan.\n"
    annex = ("LAMPIRAN I\nPERATURAN MENTERI KOMUNIKASI DAN DIGITAL\nNOMOR 15 TAHUN 2025\n"
             "A. SEKTOR POS, TELEKOMUNIKASI, DAN PENYIARAN\n"
             "1. STANDAR KEGIATAN USAHA AKTIVITAS KURIR\n" + FILL * 3 +
             "2. STANDAR KEGIATAN USAHA JASA TELEPONI\n1. Ruang Lingkup layanan telepon.\n"
             "Penyelenggara wajib merekam dan menyimpan data penggunaan pelanggan paling "
             "singkat 3 (tiga) bulan.\n" + FILL * 2)
    ps = {p.article_section: p.verbatim_snippet for p in _split(body + annex)}
    assert "Lampiran I, A.2" in ps and "paling singkat 3" in ps["Lampiran I, A.2"]
    assert "LAMPIRAN" not in ps["Pasal 8"]
    assert "Lampiran I, A.1" in ps          # the mixed-case "1. Ruang Lingkup" stays inside A.2
