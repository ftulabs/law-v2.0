"""OCR provider interface. Implementations are interchangeable and selected at
runtime by `ocr_factory.get_ocr_provider()` from `OCR_PROVIDER`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OCRPageResult:
    page: int
    text: str
    confidence: float | None = None   # 0..1, None if provider gives none


@dataclass
class OCRResult:
    text: str
    pages: list[OCRPageResult] = field(default_factory=list)
    provider: str = "mock"

    @property
    def mean_confidence(self) -> float | None:
        confs = [p.confidence for p in self.pages if p.confidence is not None]
        return sum(confs) / len(confs) if confs else None

    @property
    def low_conf_pages(self) -> list[int]:
        return [p.page for p in self.pages if p.confidence is not None and p.confidence < 0.6]


class OCRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def ocr_pdf(self, pdf_path: str) -> OCRResult:
        """Run OCR over a scanned PDF and return text + per-page confidence."""
        raise NotImplementedError
