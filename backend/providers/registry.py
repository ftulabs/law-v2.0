"""Provider registry + availability probe.

Lets the dashboard present every OCR/LLM option and tell the judge, up front,
which ones are ready on this machine (library installed? key present?) vs. which
need setup — without trying to import heavy libs eagerly.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from ..config import settings

OCR_PROVIDERS = ["markitdown", "mock", "tesseract", "paddle", "azure"]
LLM_PROVIDERS = ["openrouter", "mock", "anthropic", "openai", "local"]

OCR_LABELS = {"markitdown": "MarkItDown (default)", "mock": "Mock (offline)",
              "tesseract": "Tesseract", "paddle": "PaddleOCR", "azure": "Azure Vision"}
LLM_LABELS = {"openrouter": "OpenRouter (free models)", "mock": "Mock grader (offline)",
              "anthropic": "Anthropic Claude", "openai": "OpenAI",
              "local": "Self-hosted (Ollama/OpenAI-compatible)"}

# Curated free models on OpenRouter (verified available; availability can change).
OPENROUTER_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-oss-120b:free",
    "z-ai/glm-4.5-air:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]


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
        if not _have("paddleocr", "pdf2image"):
            return Availability(False, "pip install paddleocr paddlepaddle pdf2image")
        return Availability(True, "ready")
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
        return Availability(True, "ready (free models)")
    if name == "local":
        if not _have("openai"):
            return Availability(False, "pip install openai")
        if not settings.local_llm_base_url:
            return Availability(False, "set Base URL (e.g. http://gpu-lab:11434/v1)")
        return Availability(True, f"ready: {settings.local_llm_base_url}")
    return Availability(False, "unknown")
