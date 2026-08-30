"""Page-level PDF triage, the single canonical text format, and per-language OCR selection.

Covers the three changes made together because they are one decision: WHICH pages need OCR
(triage), WHAT the extractor is allowed to emit (format), and WHICH model reads them (language).
"""
import pytest

from backend.pipeline import pdf_inspect
from backend.pipeline.ocr import markdown_to_plain, to_canonical
from backend.providers import ocr_languages as L


# ── Task 1: triage ────────────────────────────────────────────────────────────────────────
def test_profile_reports_pages_not_just_a_verdict():
    """The old rule was one number for the whole file; the new one must expose per-page detail."""
    prof = pdf_inspect.profile_pdf("data/samples/SG/mas_notice_655.pdf")
    assert prof.page_count >= 1
    assert prof.doc_type in ("text_based", "scanned", "image_based", "mixed", "unknown")
    assert isinstance(prof.pages_needing_ocr, set)


def test_scanned_sample_is_routed_to_ocr():
    prof = pdf_inspect.profile_pdf("data/samples/SG/mas_notice_655.pdf")
    assert prof.needs_any_ocr, "the bundled image-only notice must be sent to OCR"


def test_text_layer_sample_skips_ocr():
    prof = pdf_inspect.profile_pdf("data/samples/AU/privacy_act.pdf")
    assert not prof.needs_any_ocr, "a text-layer PDF must not pay for OCR"


def test_mixed_document_is_representable():
    """The property the whole change exists for: a file where only SOME pages are scanned.
    The old whole-file density average could not express this at all."""
    prof = pdf_inspect.PdfProfile(page_count=10, pages_needing_ocr={4, 5}, doc_type="mixed")
    assert prof.is_mixed and prof.needs_any_ocr and not prof.is_fully_scanned
    assert prof.text_pages() == [1, 2, 3, 6, 7, 8, 9, 10]


def test_density_fallback_when_inspector_missing(monkeypatch):
    """The optional dependency must never be load-bearing: without it we degrade to the
    original heuristic rather than failing the run."""
    monkeypatch.setattr(pdf_inspect, "_profile_with_inspector", lambda path: None)
    prof = pdf_inspect.profile_pdf(
        "x.pdf", page_texts={1: "a" * 200, 2: "", 3: "b" * 200}, page_count=3)
    assert prof.engine == "density-fallback"
    assert prof.pages_needing_ocr == {2}      # only the empty page, judged per page


# ── Task 2: one canonical format ──────────────────────────────────────────────────────────
def test_markdown_is_reduced_to_plain_text_without_changing_words():
    """Engines stay swappable, so a markdown-emitting engine is normalised at the boundary.
    Wording must survive byte-identically or the verbatim snippet stops matching its source."""
    md = ("## 26. Transfer of personal data\n\n"
          "An **organisation** shall _not_ transfer any personal data outside "
          "[Singapore](https://sso.agc.gov.sg) except as prescribed.\n")
    out = markdown_to_plain(md)
    assert "26. Transfer of personal data" in out
    assert "An organisation shall not transfer any personal data outside Singapore" in out
    for syntax in ("##", "**", "](", "_not_"):
        assert syntax not in out


def test_table_rows_stay_on_separate_lines():
    """Regression: a greedy `\\s*$` swallowed the newline and welded rows into one line,
    which would merge two unrelated provisions into a single snippet."""
    out = markdown_to_plain("| Item | Rule |\n|---|---|\n| 1 | Consent |\n| 2 | Adequacy |\n")
    assert "Rule1" not in out
    assert "1  Consent" in out and "2  Adequacy" in out


def test_plain_text_is_left_untouched():
    """The canonical form must be a fixed point — normalising twice changes nothing, and the
    heading sentinel that extraction splits on must survive."""
    plain = "\x1e77 Requirement not to hold records outside Australia\n(1) The operator must not."
    assert to_canonical(plain) == plain
    assert to_canonical(to_canonical(plain)) == plain


# ── Task 3: per-language engine selection ─────────────────────────────────────────────────
def test_round_one_economies_use_latin_models():
    for eco in ("SG", "AU", "MY"):
        assert L.ocr_code("rapidocr", eco) == "latin"


def test_thai_gets_its_dedicated_model_not_the_latin_bucket():
    assert L.ocr_code("rapidocr", "TH") == "th"
    assert L.ocr_code("tesseract", "TH") == "tha+eng"   # bilingual gazettes, single pass


def test_portuguese_reaches_an_engine_that_can_emit_its_diacritics():
    """Timor-Leste legislates in Portuguese, whose diacritics all sit in Latin-1 Supplement —
    unlike the precomposed tone forms that disqualify the shared `latin` dictionary for other
    languages. So the Latin path IS valid here, and tesseract must be told `por`, not `eng`:
    a verbatim snippet reading "proteção" cannot survive an English-only dictionary."""
    assert L.ocr_code("tesseract", "TL") == "por+eng"
    assert L.ocr_code("rapidocr", "TL") == "latin"


def test_lao_has_only_tesseract_offline_and_is_flagged_unvalidated():
    """No Lao model exists in PaddleOCR, RapidOCR, EasyOCR or Azure. Tesseract is the only
    offline option and has no published accuracy of any kind, so it must not be presented
    as validated coverage."""
    assert L.ocr_code("rapidocr", "LA") is None
    assert L.ocr_code("azure", "LA") is None
    assert L.ocr_code("tesseract", "LA") == "lao"
    assert L.best_engine("LA") == L.TESSERACT
    assert not L.is_validated("LA")


def test_unknown_economy_falls_back_to_latin():
    assert L.ocr_code("rapidocr", "ZZ") == "latin"
    assert L.ocr_code("rapidocr", None) == "latin"


@pytest.mark.parametrize("eco", ["TH", "CN", "RU", "MN", "LA"])
def test_non_latin_economies_are_not_silently_claimed_as_validated(eco):
    """Guards the honesty statement: only scripts with a citable document-level measurement
    may report validated coverage. Everything else must stay explicitly unproven."""
    assert not L.is_validated(eco)


# ── Script properties that break stages AFTER ocr ─────────────────────────────────────────
def test_spaceless_scripts_are_flagged_for_segmentation():
    """Thai, Lao and Chinese have no inter-word spaces. Splitting them on whitespace makes
    BM25 index whole sentences as single terms, so keyword retrieval collapses even when OCR
    is perfect — a failure with no visible error anywhere."""
    assert L.needs_segmentation("TH") == "pythainlp"
    assert L.needs_segmentation("LA") == "laonlp"
    assert L.needs_segmentation("CN") == "jieba"
    for eco in ("SG", "AU", "MY", "RU", "TL"):
        assert L.needs_segmentation(eco) is None


def test_script_validity_detects_legacy_encoded_text():
    """The Lao legacy-font trap: a text layer that extracts as upper-ASCII instead of Lao.
    The CER gate cannot see this because no OCR ran, so the script check is the only defence."""
    real_lao = "ກົດໝາຍວ່າດ້ວຍການປົກປ້ອງຂໍ້ມູນ"
    mojibake = "¡ÃÐÊÇ§ÂØµÔ¸ÃÃÁ¢éÍÁÙÅ"      # Lao letters mapped into upper-ASCII
    assert L.script_validity(real_lao, "LA") == 1.0
    assert L.looks_mojibake(mojibake, "LA")
    assert not L.looks_mojibake(real_lao, "LA")


def test_script_validity_is_neutral_when_nothing_is_checkable():
    """Must return 1.0 rather than 0.0 on empty or unconfigured input, so a low score is a
    real signal instead of a default."""
    assert L.script_validity("", "TH") == 1.0
    assert L.script_validity("12345 ...", "TH") == 1.0


def test_latin_economies_accept_ordinary_english():
    assert not L.looks_mojibake("An organisation shall not transfer personal data", "SG")


def test_india_defaults_to_english_not_devanagari():
    """indiacode.nic.in publishes Central Acts in English as the authoritative text, so the
    cheap Latin path carries India. Devanagari is only needed for Hindi editions, and is hard
    for classical engines (EasyOCR measured 34.3% CER on real printed Devanagari)."""
    assert L.ocr_code("rapidocr", "IN") == "latin"
    assert L.ocr_code("tesseract", "IN") == "eng+hin"   # both, single pass
    assert L.needs_segmentation("IN") is None


def test_portuguese_ordinal_indicator_survives_nfc_but_not_nfkc():
    """Timor-Leste's hazard is normalisation, not OCR. U+00BA (º) decomposes to plain 'o'
    under NFKC, silently rewriting 'Artigo 1.º' to 'Artigo 1.o' and breaking citation
    matching — while a mis-OCR'd degree sign U+00B0 has no decomposition and survives intact,
    so NFKC neither repairs nor flags the error. Portuguese text must use NFC."""
    import unicodedata
    ref = "Lei n.º 13.709"
    assert unicodedata.normalize("NFC", ref) == ref
    assert unicodedata.normalize("NFKC", ref) == "Lei n.o 13.709"   # the destructive case
    assert unicodedata.normalize("NFKC", "25°C") == "25°C"          # the asymmetry
    assert not L.looks_mojibake(ref, "TL")
