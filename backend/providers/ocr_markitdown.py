"""MarkItDown extraction/OCR provider — the DEFAULT engine.

Microsoft MarkItDown (https://github.com/microsoft/markitdown) converts PDF/Office/
HTML/images to clean Markdown. We use it as the default document-extraction engine:
for text-bearing PDFs it yields high-fidelity text (no error-prone image OCR needed).

Notes:
  • MarkItDown extracts the PDF text layer; it does not raster-OCR image-only pages on
    its own. For truly scanned/image PDFs, configure Azure Document Intelligence
    (MarkItDown's `docintel_endpoint`) or switch OCR_PROVIDER=tesseract.
  • Confidence is reported as None: this is deterministic extraction, not probabilistic
    OCR, so a fabricated score would mislead. `used=True` still flags the OCR branch.
  • For the offline sample (where the .pdf may be a placeholder), we fall back to a
    sidecar `*.ocr.txt` so the demo always produces text.
"""
from __future__ import annotations

from pathlib import Path

from .ocr_base import OCRProvider, OCRResult, OCRPageResult


class MarkItDownOCR(OCRProvider):
    name = "markitdown"

    def __init__(self, docintel_endpoint: str = ""):
        from markitdown import MarkItDown
        kwargs = {"docintel_endpoint": docintel_endpoint} if docintel_endpoint else {}
        self._md = MarkItDown(**kwargs)

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        p = Path(pdf_path)
        text = ""
        if p.exists():
            try:
                text = (self._md.convert(str(p)).text_content or "").strip()
            except Exception:
                text = ""
        if not text:
            # offline-sample fallback: ground-truth sidecar
            sidecar = p.with_suffix(".ocr.txt")
            if sidecar.exists():
                text = sidecar.read_text(encoding="utf-8")
        if not text.strip():
            text = f"[markitdown] no extractable text for {p.name}"

        chunks = text.split("\f") if "\f" in text else [text]
        pages = [OCRPageResult(page=i, text=c.strip(), confidence=None)
                 for i, c in enumerate(chunks, start=1)]
        return OCRResult(text=text, pages=pages, provider=self.name)
