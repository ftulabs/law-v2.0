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
