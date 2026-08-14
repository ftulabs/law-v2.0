"""ZONE 2a — PDF triage: which pages carry a real text layer, which need raster OCR.

Why this exists
---------------
The old test was one number for the WHOLE file: `len(text)/pages >= 40 chars`. That cannot
express a mixed document — a gazette whose first pages are typeset text and whose schedules
are photographed. Such a file is classified once and then handled wrongly end to end: either
the scanned half is silently dropped, or OCR is run over hundreds of pages that already had
perfectly good text.

Mixed files are rare in the Round-1 corpus (0 of 146 cached PDFs) but are the normal shape of
the older bilingual gazettes we expect in the Finals economies, where reprints of pre-2000
instruments are photographed and appended to typeset text.

Engine
------
`pdf-inspector` (Firecrawl, MIT, Rust with an abi3 wheel — no toolchain needed) samples the
content streams and returns a per-page OCR verdict plus a machine-readable reason. It carries
no ML model and no OCR of its own: it is a router, not an extractor. Measured here on the
bundled corpus it agreed with the density heuristic on every document while additionally
reporting page-level detail the heuristic cannot represent, and it independently found 348 of
the 352 bold section headings pdfplumber marks in the 472-page AU Privacy Act, which is a
useful cross-check that its page model matches ours.

The dependency is OPTIONAL. When it is missing (or throws on a malformed file) we fall back to
the original density rule, applied per page where possible, so the pipeline never hard-fails on
a PDF-parsing dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Density floor, in stripped characters per page, below which a page is treated as scanned.
# Kept identical to the historical whole-file rule so fallback behaviour is unchanged.
MIN_CHARS_PER_PAGE = 40


@dataclass
class PdfProfile:
    """Per-page triage verdict for one PDF."""

    page_count: int = 0
    #: 1-indexed page numbers that need raster OCR.
    pages_needing_ocr: set[int] = field(default_factory=set)
    #: "text_based" | "scanned" | "image_based" | "mixed" | "unknown"
    doc_type: str = "unknown"
    confidence: float = 0.0
    #: which implementation produced this verdict, for the audit trail
    engine: str = "density-fallback"
    #: machine-readable reasons keyed by 1-indexed page, when the engine supplies them
    reasons: dict[int, list[str]] = field(default_factory=dict)

    @property
    def needs_any_ocr(self) -> bool:
        return bool(self.pages_needing_ocr)

    @property
    def is_fully_scanned(self) -> bool:
        return self.page_count > 0 and len(self.pages_needing_ocr) >= self.page_count

    @property
    def is_mixed(self) -> bool:
        """Some pages have a usable text layer and some do not."""
        return 0 < len(self.pages_needing_ocr) < self.page_count

    def text_pages(self) -> list[int]:
        """1-indexed pages that can be read straight from the text layer."""
        return [p for p in range(1, self.page_count + 1) if p not in self.pages_needing_ocr]


def available() -> bool:
    """True when the optional pdf-inspector wheel is importable."""
    try:
        import importlib.util

        return importlib.util.find_spec("pdf_inspector") is not None
    except Exception:  # noqa: BLE001 — treat any probe failure as "not available"
        return False


def profile_pdf(path: str, page_texts: dict[int, str] | None = None,
                page_count: int | None = None) -> PdfProfile:
    """Classify `path` page by page.

    `page_texts` / `page_count` are only consulted by the density fallback, so a caller that
    has already extracted the text layer can avoid a second parse.
    """
    prof = _profile_with_inspector(path)
    if prof is not None:
        return prof
    return _profile_by_density(path, page_texts, page_count)


def _profile_with_inspector(path: str) -> PdfProfile | None:
    try:
        import pdf_inspector
    except Exception:  # noqa: BLE001 — optional dependency
        return None
    try:
        det = pdf_inspector.detect_pdf(path)
    except Exception:  # noqa: BLE001 — malformed/encrypted PDF → let the fallback decide
        return None

    # NOTE: `detect_pdf`/`process_pdf` report 1-indexed pages, while `classify_pdf` reports
    # 0-indexed ones. We standardise on 1-indexed everywhere, matching pdfplumber page numbers
    # and the "p. N" location reference in the output CSV.
    pages = {int(p) for p in (getattr(det, "pages_needing_ocr", None) or [])}
    reasons: dict[int, list[str]] = {}
    for entry in (getattr(det, "ocr_reasons_by_page", None) or []):
        try:
            reasons[int(entry.page)] = list(entry.reasons)
        except Exception:  # noqa: BLE001 — reason payload is advisory only
            continue

    count = int(getattr(det, "page_count", 0) or 0)
    doc_type = str(getattr(det, "pdf_type", "unknown") or "unknown")
    # A file reported as wholly scanned but with no explicit page list still needs every page
    # OCR'd; without this the hybrid router would find nothing to do.
    if not pages and doc_type in ("scanned", "image_based") and count:
        pages = set(range(1, count + 1))

    return PdfProfile(
        page_count=count,
        pages_needing_ocr={p for p in pages if 1 <= p <= count} if count else pages,
        doc_type=doc_type,
        confidence=float(getattr(det, "confidence", 0.0) or 0.0),
        engine="pdf-inspector",
        reasons=reasons,
    )


def _profile_by_density(path: str, page_texts: dict[int, str] | None,
                        page_count: int | None) -> PdfProfile:
    """Original heuristic, kept as the no-dependency fallback.

    Applied per page when the caller supplies per-page text; otherwise it degrades to the
    historical whole-file average, which is what shipped before page-level triage existed.
    """
    from .ocr import _page_count, _pdf_text_layer

    count = page_count if page_count is not None else (_page_count(path) or 0)
    if page_texts:
        thin = {p for p, t in page_texts.items() if len((t or "").strip()) < MIN_CHARS_PER_PAGE}
        doc_type = ("text_based" if not thin
                    else "scanned" if len(thin) >= count > 0
                    else "mixed")
        return PdfProfile(page_count=count, pages_needing_ocr=thin, doc_type=doc_type,
                          confidence=0.5, engine="density-fallback")

    text = _pdf_text_layer(path)
    dense = len(text.strip()) / max(count, 1) >= MIN_CHARS_PER_PAGE
    return PdfProfile(
        page_count=count,
        pages_needing_ocr=set() if dense else set(range(1, count + 1)),
        doc_type="text_based" if dense else "scanned",
        confidence=0.5,
        engine="density-fallback",
    )
