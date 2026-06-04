"""PaddleOCR provider (optional). Deferred imports keep this safe to import."""
from __future__ import annotations

from .ocr_base import OCRProvider, OCRResult, OCRPageResult


class PaddleOCRProvider(OCRProvider):
    name = "paddle"

    def __init__(self, lang: str = "en"):
        from paddleocr import PaddleOCR
        from pdf2image import convert_from_path

        self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        self._convert = convert_from_path

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        import numpy as np

        images = self._convert(pdf_path, dpi=300)
        pages: list[OCRPageResult] = []
        for idx, img in enumerate(images, start=1):
            result = self._ocr.ocr(np.array(img), cls=True)
            lines, confs = [], []
            for block in (result[0] or []):
                text, conf = block[1][0], block[1][1]
                lines.append(text)
                confs.append(float(conf))
            page_conf = sum(confs) / len(confs) if confs else None
            pages.append(OCRPageResult(page=idx, text="\n".join(lines), confidence=page_conf))
        full = "\n\n".join(p.text for p in pages)
        return OCRResult(text=full, pages=pages, provider=self.name)
