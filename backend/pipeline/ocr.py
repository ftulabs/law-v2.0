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


# Single-page-app framework markers. A page carrying one of these renders its body with
# JavaScript, so a static fetch returns only the app shell (site chrome, no law text).
# legislation.gov.au (Angular: `ng-version`) is the Round-1 case.
_SPA_MARKERS = ("ng-version=", "<app-root", "data-reactroot", "__next_data__",
                "window.__nuxt", 'id="__nuxt"')


def is_js_app_shell(html: str, text: str | None = None) -> bool:
    """True when `html` is an UNRENDERED SPA shell — a JS framework marker is present AND
    the de-chromed text has no legal structure (so extraction would otherwise emit the
    site's navigation chrome as a bogus, non-verbatim 'provision'). If real section
    markers ARE present the page carries server-rendered content and is kept."""
    head = html[:400_000].lower()
    if not any(m in head for m in _SPA_MARKERS):
        return False
    from .extraction import SECTION_RE
    body = text if text is not None else _html_to_text(html)
    return SECTION_RE.search(body) is None


def _page_count(path: str) -> int:
    try:
        import pypdfium2
        doc = pypdfium2.PdfDocument(path)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        try:
            from pypdf import PdfReader
            return len(PdfReader(path).pages)
        except Exception:
            return 1


def _pdf_text_layer(path: str) -> str:
    # x_tolerance infers spaces from glyph gaps — without it, legal PDFs come out with
    # words jammed together ("Anorganisationmustnot"), which wrecks the Character Error
    # Rate and the downstream matching. pdfplumber preserves spacing + line structure.
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n\n".join((pg.extract_text(x_tolerance=2, y_tolerance=3) or "") for pg in pdf.pages)
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
        text = _html_to_text(raw)
        # An unrendered SPA shell (e.g. legislation.gov.au) carries only site chrome — return
        # empty so extraction emits no provisions instead of mapping navigation text as a law.
        if is_js_app_shell(raw, text):
            metrics.notes = "js_app_shell"
            return "", metrics
        return text, metrics

    if fmt == DocFormat.TEXT or (path and path.endswith(".txt")):
        text = Path(path).read_text(encoding="utf-8", errors="ignore") if path and Path(path).exists() else (doc.raw_text or "")
        return text, metrics

    if fmt in (DocFormat.PDF_TEXT, DocFormat.PDF_SCANNED) and path:
        provider = ocr_provider or get_ocr_provider(settings.ocr_provider)

        # For a real text-layer PDF, pdfplumber (with x_tolerance) gives the cleanest
        # text — proper word spacing + structure, low CER. Try it FIRST regardless of the
        # configured engine; only fall back to OCR when the layer is thin PER PAGE, i.e.
        # the PDF is genuinely scanned/image-based (a 300-page Act with ~0 chars/page).
        if fmt == DocFormat.PDF_TEXT:
            text = _pdf_text_layer(path)
            pages = _page_count(path)
            if len(text.strip()) / max(pages, 1) >= 40:   # healthy text density → not scanned
                return text, metrics
            # thin per page → scanned → run OCR (rapidocr/tesseract/azure)

        return _run_provider(provider, path)

    return doc.raw_text or "", metrics


# Engines that re-read a ground-truth sidecar instead of doing raster OCR — measuring
# CER against that same sidecar would be circular (always ~0), so we skip it for them.
_SIDECAR_READERS = {"markitdown", "mock"}


def _measure_cer(provider_name: str, path: str, ocr_text: str) -> float | None:
    """Genuine Character Error Rate against a ground-truth `*.ocr.txt` sidecar, when one
    ships next to the sample (offline accuracy proof for the rubric's CER < 5% bar).
    Only meaningful for true raster-OCR engines — sidecar readers would score a fake 0."""
    if provider_name in _SIDECAR_READERS:
        return None
    ref = Path(path).with_suffix(".ocr.txt")
    if not ref.exists():
        return None
    from .cer import character_error_rate
    return character_error_rate(ref.read_text(encoding="utf-8", errors="ignore"), ocr_text)


def _run_provider(provider, path: str) -> tuple[str, OCRMetrics]:
    result = provider.ocr_pdf(path)
    metrics = OCRMetrics(
        used=True,
        provider=result.provider,
        mean_confidence=result.mean_confidence,
        pages=len(result.pages),
        chars=len(result.text),
        low_conf_pages=result.low_conf_pages,
        cer=_measure_cer(result.provider, path, result.text),
    )
    return result.text, metrics
