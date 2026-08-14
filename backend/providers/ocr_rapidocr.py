"""RapidOCR provider — pip-only OCR (ONNX Runtime), no system binaries.

Renders PDF pages with pypdfium2 (no poppler needed), so SCANNED / image-based PDFs work on
Windows and arm64 without installing Tesseract + poppler. Heavy imports are deferred to
__init__ so importing this module never fails on a machine without the optional deps.

    pip install rapidocr pypdfium2          # preferred, >=3.9
    pip install rapidocr_onnxruntime        # legacy fallback, English/Chinese only

TWO PACKAGES, AND THE DIFFERENCE MATTERS
----------------------------------------
`rapidocr_onnxruntime` is frozen at 1.4.4 (Jan 2025): it bundles PP-OCRv4 Chinese+English
models and exposes NO language selector at all, so Thai, Cyrillic and Vietnamese characters
are simply absent from its output dictionary and cannot be produced. The maintained package
is `rapidocr` (>=3.9, Apache-2.0), which accepts a recognition language and can load the
PP-OCRv5 per-script models. We prefer the new package and degrade to the old one so an
existing environment keeps working — but a non-Latin economy on the legacy package is a
correctness problem, not a performance one, so we say so out loud.
"""
from __future__ import annotations

from .ocr_base import OCRPageResult, OCRProvider, OCRResult


class RapidOCRProvider(OCRProvider):
    name = "rapidocr"

    def __init__(self, dpi: int = 300, lang: str | None = None):
        import pypdfium2  # noqa: F401

        self._pdfium = pypdfium2
        self.lang = lang
        self._ocr, self.engine_package = self._build_engine(lang)
        # 300 dpi is the OCR sweet spot: rendering a scanned page below it loses glyph
        # detail and inflates the character-error rate (200 dpi pushed CER over 5% here).
        self._scale = dpi / 72.0          # pdfium renders at 72 dpi * scale

    @staticmethod
    def _build_engine(lang: str | None):
        """Prefer maintained `rapidocr` (language-aware); fall back to the frozen package."""
        try:
            from rapidocr import RapidOCR as _New
        except Exception:  # noqa: BLE001 — new package absent
            from rapidocr_onnxruntime import RapidOCR as _Old
            if lang and lang not in ("en", "latin", "ch"):
                raise RuntimeError(
                    f"OCR language {lang!r} needs the maintained 'rapidocr' package "
                    f"(pip install 'rapidocr>=3.9'); the installed 'rapidocr_onnxruntime' "
                    f"only ships English/Chinese models and would silently drop this script."
                )
            return _Old(), "rapidocr_onnxruntime"
        if not lang:
            return _New(), "rapidocr"
        # The parameter has been spelled differently across 3.x; try the documented keys and
        # fall back to the default engine rather than crashing on a version mismatch.
        for key in ("Rec.lang_rec", "Rec.lang_type"):
            try:
                return _New(params={key: lang}), "rapidocr"
            except Exception:  # noqa: BLE001 — unknown key on this version
                continue
        return _New(), "rapidocr"

    def ocr_pdf(self, pdf_path: str, pages: list[int] | None = None) -> OCRResult:
        doc = self._pdfium.PdfDocument(pdf_path)
        out: list[OCRPageResult] = []
        want = {p - 1 for p in pages} if pages else None      # 1-indexed arg → 0-indexed pdfium
        try:
            for i in range(len(doc)):
                if want is not None and i not in want:
                    continue
                bitmap = doc[i].render(scale=self._scale)
                img = bitmap.to_numpy()                       # HxWxC uint8
                result, _ = self._ocr(img)                    # [[box, text, score], ...] | None
                lines, confs = [], []
                for item in (result or []):
                    lines.append(item[1])
                    try:
                        confs.append(float(item[2]))
                    except (TypeError, ValueError, IndexError):
                        pass
                page_conf = sum(confs) / len(confs) if confs else None
                out.append(OCRPageResult(page=i + 1, text="\n".join(lines), confidence=page_conf))
        finally:
            doc.close()
        return OCRResult(text="\n\n".join(p.text for p in out), pages=out, provider=self.name)
