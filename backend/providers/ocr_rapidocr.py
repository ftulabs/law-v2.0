"""RapidOCR provider — pip-only OCR (ONNX Runtime), no system binaries.

Renders PDF pages with pypdfium2 (no poppler needed) and OCRs with rapidocr_onnxruntime,
so SCANNED / image-based PDFs work on Windows AND on the Jetson (arm64) without installing
Tesseract + poppler. Heavy imports are deferred to __init__ so importing this module never
fails on a machine without the optional deps.

    pip install rapidocr_onnxruntime pypdfium2
"""
from __future__ import annotations

from .ocr_base import OCRPageResult, OCRProvider, OCRResult


class RapidOCRProvider(OCRProvider):
    name = "rapidocr"

    def __init__(self, dpi: int = 200):
        import pypdfium2  # noqa: F401
        from rapidocr_onnxruntime import RapidOCR

        self._pdfium = pypdfium2
        self._ocr = RapidOCR()
        self._scale = dpi / 72.0          # pdfium renders at 72 dpi * scale

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        doc = self._pdfium.PdfDocument(pdf_path)
        pages: list[OCRPageResult] = []
        try:
            for i in range(len(doc)):
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
                pages.append(OCRPageResult(page=i + 1, text="\n".join(lines), confidence=page_conf))
        finally:
            doc.close()
        return OCRResult(text="\n\n".join(p.text for p in pages), pages=pages, provider=self.name)
