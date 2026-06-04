"""OCR provider factory + a deterministic mock.

The mock reads a sidecar `.txt` next to a sample "scanned" PDF (or the PDF's own
text layer) and simulates per-page OCR confidence, so the full pipeline — including
the scanned-PDF branch and confidence routing — runs offline with no binaries.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from .ocr_base import OCRProvider, OCRResult, OCRPageResult


class MockOCR(OCRProvider):
    name = "mock"

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        p = Path(pdf_path)
        text = ""
        # 1) sidecar .txt (sample scanned doc ships its ground-truth text)
        sidecar = p.with_suffix(".ocr.txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8")
        else:
            # 2) try a real text layer via pypdf, if available
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(p))
                text = "\n\n".join((pg.extract_text() or "") for pg in reader.pages)
            except Exception:
                text = ""
        if not text.strip():
            text = f"[mock-ocr] no extractable text for {p.name}"

        # split into pseudo-pages on form feed or blank-line groups
        chunks = text.split("\f") if "\f" in text else _chunk(text, 1800)
        pages: list[OCRPageResult] = []
        for idx, chunk in enumerate(chunks, start=1):
            # deterministic, content-derived "confidence": longer cleaner text → higher
            alpha = sum(c.isalpha() or c.isspace() for c in chunk)
            ratio = alpha / max(len(chunk), 1)
            conf = round(0.55 + 0.4 * ratio, 3)
            pages.append(OCRPageResult(page=idx, text=chunk.strip(), confidence=conf))
        return OCRResult(text=text, pages=pages, provider=self.name)


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


def get_ocr_provider(name: str | None = None) -> OCRProvider:
    name = (name or settings.ocr_provider or "mock").lower()
    if name == "mock":
        return MockOCR()
    if name == "tesseract":
        from .ocr_tesseract import TesseractOCR
        return TesseractOCR(settings.tesseract_cmd, settings.poppler_path)
    if name == "paddle":
        from .ocr_paddle import PaddleOCRProvider
        return PaddleOCRProvider()
    if name == "azure":
        from .ocr_azure import AzureOCR
        return AzureOCR(settings.azure_vision_endpoint, settings.azure_vision_key)
    raise ValueError(f"Unknown OCR_PROVIDER: {name}")
