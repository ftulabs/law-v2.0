"""PaddleOCR provider — PP-OCRv5 (PaddleOCR 3.x).

High-accuracy open-source OCR for scanned / image-based legal PDFs. Uses the 3.x
pipeline API (`PaddleOCR(...).predict(...)`, results exposed as `rec_texts` /
`rec_scores`) — NOT the retired 2.x `.ocr(cls=True)` call.

Pages are rasterised with pypdfium2 (no poppler/pdf2image system binary), so this
works on Windows and arm64 (Jetson) out of the box. The heavy doc-orientation and
unwarping sub-models are disabled — legal scans are upright, and skipping them keeps
init fast and avoids extra model downloads.

Measured on the bundled scanned sample (data/samples/SG/mas_notice_655.pdf):
PP-OCRv5 → CER 0.00% (vs RapidOCR 1.11%); it recovers spaced-capital headings the
lighter engine merges. Trade-off: slower per page, especially with enable_mkldnn=False.

    pip install paddlepaddle paddleocr      # PP-OCRv5 models download on first run

Docs: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html
"""
from __future__ import annotations

from .ocr_base import OCRPageResult, OCRProvider, OCRResult


class PaddleOCRProvider(OCRProvider):
    name = "paddle"

    def __init__(self, lang: str = "en", dpi: int = 300, enable_mkldnn: bool = False):
        import pypdfium2  # noqa: F401
        from paddleocr import PaddleOCR

        # 3.x constructor: disable the orientation/unwarping stages (upright legal scans)
        # and keep text-line orientation off for speed; PP-OCRv5 detection+recognition only.
        # enable_mkldnn defaults OFF: PaddlePaddle 3.x's oneDNN path raises
        # "ConvertPirAttribute2RuntimeAttribute not support" on several Windows/CPU builds —
        # the plain CPU kernel is slower but portable. Flip it on where MKLDNN works.
        self._ocr = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=enable_mkldnn,
        )
        self._pdfium = pypdfium2
        self._scale = dpi / 72.0          # pdfium renders at 72 dpi * scale; 300 dpi = OCR sweet spot

    def _predict(self, img):
        """Run PP-OCRv5 on one page bitmap → (lines, confidences). Tolerates the small
        result-shape differences between 3.x point releases (.predict vs .ocr, dict access)."""
        runner = getattr(self._ocr, "predict", None) or self._ocr.ocr
        results = runner(img)
        lines, confs = [], []
        for res in (results or []):
            # 3.x result objects behave like a dict: rec_texts / rec_scores are parallel lists
            texts = scores = None
            try:
                texts, scores = res["rec_texts"], res["rec_scores"]
            except (TypeError, KeyError, IndexError):
                data = getattr(res, "json", None)
                if isinstance(data, dict):
                    blk = data.get("res", data)
                    texts, scores = blk.get("rec_texts"), blk.get("rec_scores")
            for t, s in zip(texts or [], scores or []):
                lines.append(t)
                try:
                    confs.append(float(s))
                except (TypeError, ValueError):
                    pass
        return lines, confs

    def ocr_pdf(self, pdf_path: str, pages: list[int] | None = None) -> OCRResult:
        doc = self._pdfium.PdfDocument(pdf_path)
        pages: list[OCRPageResult] = []
        try:
            for i in range(len(doc)):
                img = doc[i].render(scale=self._scale).to_numpy()   # HxWxC uint8 (RGB)
                lines, confs = self._predict(img)
                page_conf = sum(confs) / len(confs) if confs else None
                pages.append(OCRPageResult(page=i + 1, text="\n".join(lines), confidence=page_conf))
        finally:
            doc.close()
        return OCRResult(text="\n\n".join(p.text for p in pages), pages=pages, provider=self.name)
