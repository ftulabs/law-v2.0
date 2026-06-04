"""ZONE 2a — text acquisition + OCR.

`get_document_text` turns a DiscoveredDoc into raw text plus OCRMetrics,
branching by format:
  • html       → strip tags (BeautifulSoup) to readable text
  • pdf_text   → pdfplumber/pypdf text layer
  • pdf_scanned→ pluggable OCR provider (mock|tesseract|paddle|azure)

For text PDFs we also detect a "secretly scanned" PDF (empty text layer) and fall
back to OCR automatically — a common real-world failure mode.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..providers import get_ocr_provider
from ..providers.ocr_base import OCRProvider
from ..schemas import DiscoveredDoc, DocFormat, OCRMetrics


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _pdf_text_layer(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n\n".join((pg.extract_text() or "") for pg in pdf.pages)
    except Exception:
        try:
            from pypdf import PdfReader
            return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except Exception:
            return ""


def get_document_text(doc: DiscoveredDoc, ocr_provider: OCRProvider | None = None) -> tuple[str, OCRMetrics]:
    metrics = OCRMetrics()
    path = doc.local_path
    fmt = doc.fmt

    if fmt == DocFormat.HTML or (path and path.endswith(".html")):
        raw = Path(path).read_text(encoding="utf-8", errors="ignore") if path and Path(path).exists() else (doc.raw_text or "")
        return _html_to_text(raw), metrics

    if fmt == DocFormat.TEXT or (path and path.endswith(".txt")):
        text = Path(path).read_text(encoding="utf-8", errors="ignore") if path and Path(path).exists() else (doc.raw_text or "")
        return text, metrics

    if fmt in (DocFormat.PDF_TEXT, DocFormat.PDF_SCANNED) and path:
        provider = ocr_provider or get_ocr_provider(settings.ocr_provider)
        is_markitdown = getattr(provider, "name", "") == "markitdown"

        # MarkItDown is the default extraction engine: use it for ALL PDFs. For real
        # OCR engines (tesseract/azure), prefer a clean text layer and only OCR when
        # the layer is thin (genuinely scanned).
        if fmt == DocFormat.PDF_TEXT and not is_markitdown:
            text = _pdf_text_layer(path)
            if len(text.strip()) >= 200:
                return text, metrics
            # fall through → scanned, run OCR

        return _run_provider(provider, path)

    return doc.raw_text or "", metrics


def _run_provider(provider, path: str) -> tuple[str, OCRMetrics]:
    result = provider.ocr_pdf(path)
    metrics = OCRMetrics(
        used=True,
        provider=result.provider,
        mean_confidence=result.mean_confidence,
        pages=len(result.pages),
        chars=len(result.text),
        low_conf_pages=result.low_conf_pages,
    )
    return result.text, metrics
