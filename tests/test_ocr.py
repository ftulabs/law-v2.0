"""OCR / extraction: MarkItDown (default engine) extracts the bundled PDFs."""
from pathlib import Path

import pytest

from backend.providers import get_ocr_provider
from backend.providers import registry as reg

ROOT = Path(__file__).resolve().parent.parent
AU_PDF = ROOT / "data" / "samples" / "AU" / "privacy_act.pdf"


def test_markitdown_is_default_and_available():
    from backend.config import settings
    assert settings.ocr_provider == "markitdown"
    assert reg.ocr_availability("markitdown").ready


@pytest.mark.skipif(not AU_PDF.exists(), reason="sample PDF missing")
def test_markitdown_extracts_pdf_text():
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
