"""Provider registry + availability probe.

Lets the dashboard present every OCR/LLM option and tell the judge, up front,
which ones are ready on this machine (library installed? key present?) vs. which
need setup — without trying to import heavy libs eagerly.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from ..config import settings

OCR_PROVIDERS = ["markitdown", "mock", "rapidocr", "tesseract", "paddle", "azure"]
LLM_PROVIDERS = ["openrouter", "mock", "gemini", "anthropic", "openai", "local"]

OCR_LABELS = {"markitdown": "MarkItDown (default)", "mock": "Mock (offline)",
              "rapidocr": "RapidOCR (scanned, pip-only)",
              "tesseract": "Tesseract", "paddle": "PaddleOCR", "azure": "Azure Vision"}
LLM_LABELS = {"openrouter": "OpenRouter (paid · DeepSeek default)", "mock": "Mock grader (offline)",
              "gemini": "Google Gemini", "anthropic": "Anthropic Claude", "openai": "OpenAI",
              "local": "Self-hosted (Ollama/OpenAI-compatible)"}

# Paid failover pool (deepseek default ~$0.07/economy run; `:free` removed — 429s daily even
# on funded keys). Catalogue churns — verify ids via GET /api/v1/models before adding.
OPENROUTER_PAID_MODELS = [
    "deepseek/deepseek-v4-flash",
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-flash-lite",
]

OPENROUTER_MODELS = OPENROUTER_PAID_MODELS


@dataclass
class Availability:
    ready: bool
    note: str            # short status shown next to the option


def _have(*mods: str) -> bool:
    for m in mods:
        try:
            if importlib.util.find_spec(m) is None:
                return False
        except (ImportError, ModuleNotFoundError, ValueError):
            # find_spec imports parent packages; a missing parent raises here
            return False
    return True


def ocr_availability(name: str) -> Availability:
    if name == "markitdown":
        if not _have("markitdown"):
            return Availability(False, "pip install 'markitdown[pdf]'")
        return Availability(True, "ready (text PDF/HTML/Office)")
    if name == "mock":
        return Availability(True, "always on")
    if name == "tesseract":
        if not _have("pytesseract", "pdf2image"):
            return Availability(False, "pip install pytesseract pdf2image + Tesseract/poppler")
        return Availability(True, "ready")
    if name == "paddle":
        if not _have("paddleocr", "paddle", "pypdfium2"):
            return Availability(False, "pip install paddlepaddle paddleocr")
        return Availability(True, "ready (PP-OCRv5, scanned PDFs)")
    if name == "rapidocr":
        if not _have("rapidocr_onnxruntime", "pypdfium2"):
            return Availability(False, "pip install rapidocr_onnxruntime pypdfium2")
        return Availability(True, "ready (scanned PDFs, no system binary)")
    if name == "azure":
        if not _have("azure.ai.vision.imageanalysis"):
            return Availability(False, "pip install azure-ai-vision-imageanalysis")
        if not (settings.azure_vision_endpoint and settings.azure_vision_key):
            return Availability(False, "needs endpoint + key")
        return Availability(True, "ready")
    return Availability(False, "unknown")


def llm_availability(name: str, api_key: str | None = None) -> Availability:
    if name == "mock":
        return Availability(True, "always on")
    if name == "anthropic":
        if not _have("anthropic"):
            return Availability(False, "pip install anthropic")
        if not (api_key or settings.anthropic_api_key):
            return Availability(False, "needs API key")
        return Availability(True, "ready")
    if name == "openai":
        if not _have("openai"):
            return Availability(False, "pip install openai")
        if not (api_key or settings.openai_api_key):
            return Availability(False, "needs API key")
        return Availability(True, "ready")
    if name == "openrouter":
        if not _have("openai"):
            return Availability(False, "pip install openai")
        if not (api_key or settings.openrouter_api_key):
            return Availability(False, "needs OPENROUTER_API_KEY (env/secrets)")
        return Availability(True, "ready (paid models)")
    if name == "gemini":
        if not _have("openai"):
            return Availability(False, "pip install openai")
        if not (api_key or settings.gemini_api_key):
            return Availability(False, "needs GEMINI_API_KEY (env/secrets)")
        return Availability(True, "ready")
    if name == "local":
        if not _have("openai"):
            return Availability(False, "pip install openai")
        if not settings.local_llm_base_url:
            return Availability(False, "set Base URL (e.g. http://gpu-lab:11434/v1)")
        return Availability(True, f"ready: {settings.local_llm_base_url}")
    return Availability(False, "unknown")
