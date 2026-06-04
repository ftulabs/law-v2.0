"""Azure AI Vision OCR provider (optional)."""
from __future__ import annotations

from .ocr_base import OCRProvider, OCRResult, OCRPageResult


class AzureOCR(OCRProvider):
    name = "azure"

    def __init__(self, endpoint: str, key: str):
        from azure.ai.vision.imageanalysis import ImageAnalysisClient
        from azure.core.credentials import AzureKeyCredential

        if not endpoint or not key:
            raise ValueError("Azure OCR requires AZURE_VISION_ENDPOINT and AZURE_VISION_KEY")
        self._client = ImageAnalysisClient(endpoint, AzureKeyCredential(key))
        from pdf2image import convert_from_path
        self._convert = convert_from_path

    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        import io
        from azure.ai.vision.imageanalysis.models import VisualFeatures

        images = self._convert(pdf_path, dpi=300)
        pages: list[OCRPageResult] = []
        for idx, img in enumerate(images, start=1):
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            result = self._client.analyze(image_data=buf.getvalue(), visual_features=[VisualFeatures.READ])
            lines, confs = [], []
            if result.read is not None:
                for block in result.read.blocks:
                    for line in block.lines:
                        lines.append(line.text)
                        word_confs = [w.confidence for w in line.words if w.confidence is not None]
                        if word_confs:
                            confs.append(sum(word_confs) / len(word_confs))
            page_conf = sum(confs) / len(confs) if confs else None
            pages.append(OCRPageResult(page=idx, text="\n".join(lines), confidence=page_conf))
        full = "\n\n".join(p.text for p in pages)
        return OCRResult(text=full, pages=pages, provider=self.name)
