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

import hashlib
import json
import re
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


# A bold, number-led line is a section heading. Some PDFs (AU legislation.gov.au) number
# sections "77 Requirement…" with NO keyword and NO period — invisible to SECTION_RE — but
# they ARE typeset bold/larger than the body, so the font is the reliable signal. We mark
# such lines with a record-separator (\x1e, never present in legal text) so extraction can
# split on them; SG/MY PDFs don't bold their headings, so nothing is marked and they fall
# back to the regex path unchanged.
HEADING_MARK = "\x1e"
_HEADING_NUM_RE = re.compile(r"^\s*\d{1,3}[A-Za-z]{0,2}\s+[A-Za-z]")


def _is_bold_heading(text: str, chars: list) -> bool:
    if not _HEADING_NUM_RE.match(text):
        return False
    glyphs = [c for c in (chars or []) if (c.get("text") or "").strip()]
    if not glyphs:
        return False
    bold = sum(1 for c in glyphs if "bold" in (c.get("fontname") or "").lower())
    return bold / len(glyphs) >= 0.6


def _strip_running_chrome(pages: list[str]) -> list[str]:
    """General page running-header/footer removal — the robust alternative to per-law patterns.

    A running header/footer (the act title + page number, "Section 77A" / "Division 1" banners,
    "S 63/2021 14", "33 Act 2012 2020 Ed.") sits in the TOP or BOTTOM band of the page and
    repeats across pages; only its page number changes. So: mask digit runs (page numbers),
    look at the first 2 / last 3 lines of every page, and treat any normalised line that recurs
    in that band on a large fraction of pages as chrome — then drop those lines everywhere.
    Body text and one-off marginal headings don't repeat in the band, so they're kept."""
    if len(pages) < 3:
        return pages
    from collections import Counter

    def _norm(s: str) -> str:
        return re.sub(r"\d+", "#", s.replace(HEADING_MARK, "")).strip()

    counts: Counter = Counter()
    for pg in pages:
        ls = [l for l in pg.split("\n") if l.strip()]
        for l in ls[:2] + ls[-3:]:                     # header band + footer band
            n = _norm(l)
            if 0 < len(n) <= 80:
                counts[n] += 1
    thresh = max(3, int(0.25 * len(pages)))            # recurs on ≥¼ of pages → chrome
    chrome = {n for n, c in counts.items() if c >= thresh}
    if not chrome:
        return pages
    return ["\n".join(l for l in pg.split("\n") if _norm(l) not in chrome) for pg in pages]


def _pdf_text_layer(path: str) -> str:
    # x_tolerance infers spaces from glyph gaps — without it, legal PDFs come out with
    # words jammed together ("Anorganisationmustnot"), which wrecks the Character Error
    # Rate and the downstream matching. pdfplumber preserves spacing + line structure.
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for pg in pdf.pages:
                try:
                    # x_tolerance=2 infers spaces from glyph gaps — without it legal PDFs come
                    # out jammed ("personaldatamustnot"); matches the old extract_text() spacing.
                    lines = pg.extract_text_lines(x_tolerance=2)   # per-line text + char fonts
                except Exception:
                    lines = None
                if lines:
                    pages.append("\n".join(
                        (HEADING_MARK + ln["text"]) if _is_bold_heading(ln["text"], ln.get("chars"))
                        else ln["text"] for ln in lines))
                else:
                    pages.append(pg.extract_text(x_tolerance=2, y_tolerance=3) or "")
            return "\n\n".join(_strip_running_chrome(pages))
    except Exception:
        try:
            from pypdf import PdfReader
            return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except Exception:
            return ""


def _content_key(doc: DiscoveredDoc) -> str | None:
    """Stable hash of a document's actual BYTES (not its doc_id/title, which can differ across
    two discoveries of the identical file). Identical bytes always extract to identical text,
    so this is the cache key for get_document_text — independent of filename convention."""
    path = doc.local_path
    try:
        if path and Path(path).exists():
            data = Path(path).read_bytes()
        elif doc.raw_text:
            data = doc.raw_text.encode("utf-8", errors="ignore")
        else:
            return None
    except Exception:
        return None
    return hashlib.sha256(data).hexdigest()[:20]


def _extract_cache_path(key: str, provider_name: str) -> Path:
    d = settings.cache_path / "_extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}_{provider_name}.json"


def get_document_text(doc: DiscoveredDoc, ocr_provider: OCRProvider | None = None) -> tuple[str, OCRMetrics]:
    """Cached wrapper: extraction (OCR/PDF-to-text) is the single biggest per-run cost bucket
    (~44% of wall-clock on a live crawl — bigger than embedding + LLM grading combined), yet the
    SAME document (same bytes, same OCR provider) always extracts to the SAME text. A repeat run
    within fetch_ttl_hours, or the same law showing up for both Pillar 6 and Pillar 7, would
    otherwise re-run pdfplumber/MarkItDown/OCR on it every time. Cache the (text, metrics) result
    keyed by content hash + provider; the fetched BODY cache (fetch.py) already makes this safe —
    this just avoids re-parsing bytes we've already parsed."""
    if not settings.extraction_cache_enabled:
        return _extract_document_text(doc, ocr_provider)
    provider_name = (ocr_provider or get_ocr_provider(settings.ocr_provider)).name
    key = _content_key(doc)
    if key is None:
        return _extract_document_text(doc, ocr_provider)
    cache_f = _extract_cache_path(key, provider_name)
    if cache_f.exists():
        try:
            data = json.loads(cache_f.read_text(encoding="utf-8"))
            return data["text"], OCRMetrics.model_validate(data["metrics"])
        except Exception:
            pass  # unreadable/stale cache -> fall through and re-extract
    text, metrics = _extract_document_text(doc, ocr_provider)
    try:
        cache_f.write_text(json.dumps({"text": text, "metrics": metrics.model_dump()}), encoding="utf-8")
    except Exception:
        pass  # caching is best-effort; never fail the run over a write error
    return text, metrics


def _extract_document_text(doc: DiscoveredDoc, ocr_provider: OCRProvider | None = None) -> tuple[str, OCRMetrics]:
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
                metrics.pages = pages   # exposes page count for location-ref computation
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
