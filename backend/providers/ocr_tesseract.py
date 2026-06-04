"""Tesseract OCR provider (requires system `tesseract` + `poppler` for pdf2image).

Heavy imports are deferred to __init__ so importing this module never fails on a
machine without the binaries — the factory only instantiates when selected.
"""
from __future__ import annotations

from .ocr_base import OCRProvider, OCRResult, OCRPageResult


class TesseractOCR(OCRProvider):
    name = "tesseract"

    def __init__(self, tesseract_cmd: str = "", poppler_path: str = ""):
        import pytesseract  # noqa: F401
        from pdf2image import convert_from_path  # noqa: F401

        self._pytesseract = pytesseract
        self._convert = convert_from_path
        self._poppler_path = poppler_path or None
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        images = self._convert(pdf_path, dpi=300, poppler_path=self._poppler_path)
        pages: list[OCRPageResult] = []
        for idx, img in enumerate(images, start=1):
            data = self._pytesseract.image_to_data(
                img, output_type=self._pytesseract.Output.DICT
            )
            words, confs = [], []
            for word, conf in zip(data["text"], data["conf"]):
                if word.strip():
                    words.append(word)
                    try:
                        c = float(conf)
                        if c >= 0:
                            confs.append(c / 100.0)
                    except (TypeError, ValueError):
                        pass
            page_conf = sum(confs) / len(confs) if confs else None
            pages.append(OCRPageResult(page=idx, text=" ".join(words), confidence=page_conf))
        full = "\n\n".join(p.text for p in pages)
        return OCRResult(text=full, pages=pages, provider=self.name)
