"""Scanned / image-PDF OCR — the 30% Technical-Resilience rubric item.

Proves three things about the bundled scanned sample:
  1. it is a GENUINE image-only PDF (no text layer to cheat with);
  2. a real raster-OCR engine reads it at CER < 5%;
  3. the pipeline measures that CER and surfaces it at run level.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCAN_PDF = ROOT / "data" / "samples" / "SG" / "mas_notice_655.pdf"
SCAN_REF = ROOT / "data" / "samples" / "SG" / "mas_notice_655.ocr.txt"


def _has_rapidocr() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) for m in ("rapidocr_onnxruntime", "pypdfium2"))


@pytest.mark.skipif(not SCAN_PDF.exists(), reason="scanned sample missing")
def test_sample_is_genuinely_image_only():
    """No text layer → extraction is forced down the OCR path (not a text PDF in disguise)."""
    import pypdfium2
    doc = pypdfium2.PdfDocument(str(SCAN_PDF))
    try:
        chars = sum(len(doc[i].get_textpage().get_text_range()) for i in range(len(doc)))
    finally:
        doc.close()
    assert chars == 0, f"expected an image-only PDF, found {chars} text-layer chars"


@pytest.mark.skipif(not (_has_rapidocr() and SCAN_PDF.exists()), reason="rapidocr not installed")
def test_rapidocr_reads_scanned_pdf_under_5pct_cer():
    from backend.pipeline.cer import character_error_rate
    from backend.providers.ocr_rapidocr import RapidOCRProvider

    text = RapidOCRProvider().ocr_pdf(str(SCAN_PDF)).text
    cer = character_error_rate(SCAN_REF.read_text(encoding="utf-8"), text)
    assert cer < 0.05, f"CER {cer:.3f} exceeds the 5% rubric bar"


@pytest.mark.skipif(not (_has_rapidocr() and SCAN_PDF.exists()), reason="rapidocr not installed")
def test_pipeline_measures_and_reports_cer():
    from backend.pipeline.orchestrator import run_pipeline
    from backend.schemas import Economy

    result = run_pipeline(Economy.SG, [6], use_samples=True,
                          ocr_provider="rapidocr", llm_provider="mock", log=lambda *_: None)
    scanned = [r for r in result.meta.ocr_reports if r.ocr_used and r.cer is not None]
    assert scanned, "expected a run-level OCR report with a measured CER"
    assert all(r.cer_under_5pct for r in scanned)
