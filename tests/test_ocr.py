"""OCR / extraction: engine selection and text-layer handling on the bundled PDFs."""
from pathlib import Path

import pytest

from backend.providers import get_ocr_provider
from backend.providers import registry as reg

ROOT = Path(__file__).resolve().parent.parent
AU_PDF = ROOT / "data" / "samples" / "AU" / "privacy_act.pdf"


def test_default_engine_does_real_raster_ocr():
    """The default must be an engine that can actually read a scanned page.

    It used to be MarkItDown, which does not do raster OCR at all — it re-reads a text layer.
    On a genuinely scanned page that returned little or nothing, and what it did return was
    markdown fed into a splitter that only understands plain text. Text-layer PDFs never
    reached it either, since the pipeline tries pdfplumber first.
    """
    from backend.config import settings
    assert settings.ocr_provider == "rapidocr"
    assert reg.ocr_availability("rapidocr").ready


@pytest.mark.skipif(not AU_PDF.exists(), reason="sample PDF missing")
def test_markitdown_remains_selectable():
    """Engines stay swappable — a judge may still pick MarkItDown explicitly."""
    provider = get_ocr_provider("markitdown")
    result = provider.ocr_pdf(str(AU_PDF))
    assert result.provider == "markitdown"
    assert len(result.text) > 500
    assert "privacy" in result.text.lower()


# ── general running-header/footer removal (page-furniture, no per-law patterns) ──
def test_strip_running_chrome_removes_repeated_footers_keeps_body():
    """A footer that recurs in the page band with only its page number changing is dropped;
    one-off marginal headings and body text are kept. This is the general page-furniture fix."""
    from backend.pipeline.ocr import _strip_running_chrome
    pages = [f"Body sentence {i} continues here.\n(2) Provision text on this page.\n"
             f"Privacy Act 1988\n{i} Privacy Act 1988" for i in range(1, 7)]
    pages[2] = ("Transfer of personal data\n26.—(1) An organisation must not transfer.\n"
                "(2) exempt.\nPrivacy Act 1988\n3 Privacy Act 1988")
    joined = "\n".join(_strip_running_chrome(pages))
    assert "Privacy Act 1988" not in joined                 # repeated footer gone (page nums masked)
    assert "Transfer of personal data" in joined            # one-off heading kept
    assert "26.—(1) An organisation must not transfer" in joined  # body kept
