"""OCR provider factory + a deterministic mock.

The mock reads a sidecar `.txt` next to a sample "scanned" PDF (or the PDF's own
text layer) and simulates per-page OCR confidence, so the full pipeline — including
the scanned-PDF branch and confidence routing — runs offline with no binaries.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from .ocr_base import OCRProvider, OCRResult, OCRPageResult

# Engines whose recognition is chosen per script. LangProfile records None for "this engine
# has no model for this script"; markitdown/mock are not language-keyed and are exempt.
_LANG_KEYED = {"rapidocr", "paddle", "tesseract", "azure"}


class MockOCR(OCRProvider):
    name = "mock"

    def ocr_pdf(self, pdf_path: str, pages: list[int] | None = None) -> OCRResult:
        p = Path(pdf_path)
        text = ""
        # 1) sidecar .txt (sample scanned doc ships its ground-truth text)
        sidecar = p.with_suffix(".ocr.txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8")
        else:
            # 2) try a real text layer via pypdf, if available
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(p))
                text = "\n\n".join((pg.extract_text() or "") for pg in reader.pages)
            except Exception:
                text = ""
        if not text.strip():
            text = f"[mock-ocr] no extractable text for {p.name}"

        # split into pseudo-pages on form feed or blank-line groups
        chunks = text.split("\f") if "\f" in text else _chunk(text, 1800)
        pages: list[OCRPageResult] = []
        for idx, chunk in enumerate(chunks, start=1):
            # deterministic, content-derived "confidence": longer cleaner text → higher
            alpha = sum(c.isalpha() or c.isspace() for c in chunk)
            ratio = alpha / max(len(chunk), 1)
            conf = round(0.55 + 0.4 * ratio, 3)
            pages.append(OCRPageResult(page=idx, text=chunk.strip(), confidence=conf))
        return OCRResult(text=text, pages=pages, provider=self.name)


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


class UnavailableOCR(OCRProvider):
    """An engine that cannot read this document's script — and says so only when asked to.

    Failing at construction time was too early. Mongolia's statutes are served as HTML by
    legalinfo.mn and never reach an OCR engine at all, yet resolving the provider up-front
    raised and killed the entire run. Deferring the error keeps the honest part of the old
    behaviour — a scanned page in an unreadable script still fails LOUDLY rather than
    returning empty text — while letting a run that needs no OCR proceed.
    """
    name = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    def ocr_pdf(self, pdf_path: str, pages: list[int] | None = None) -> OCRResult:
        raise RuntimeError(self.reason)


def _build(name: str, economy: str | None, azure_endpoint: str | None,
           azure_key: str | None) -> OCRProvider:
    """Construct exactly the engine asked for; may raise if it has no model for the script."""
    from .ocr_languages import ocr_code, profile_for

    if name == "markitdown":
        from .ocr_markitdown import MarkItDownOCR
        return MarkItDownOCR(settings.azure_vision_endpoint)
    if name == "mock":
        return MockOCR()
    if name == "tesseract":
        from .ocr_tesseract import TesseractOCR
        return TesseractOCR(settings.tesseract_cmd, settings.poppler_path,
                            lang=ocr_code("tesseract", economy) or "eng")
    if name == "paddle":
        from .ocr_paddle import PaddleOCRProvider
        # Was PaddleOCRProvider() — the constructor's lang="en" default was never overridden,
        # so recognition ran English-only for every document in every economy.
        return PaddleOCRProvider(lang=ocr_code("paddle", economy) or "en")
    if name == "rapidocr":
        from .ocr_rapidocr import RapidOCRProvider
        return RapidOCRProvider(lang=ocr_code("rapidocr", economy))
    if name == "vlm":
        # Not language-keyed: a vision model has no per-script output dictionary, which is
        # precisely why it is the fallback for the scripts the others cannot spell.
        from .ocr_vlm import VLMOCRProvider
        return VLMOCRProvider(lang=profile_for(economy).language)
    if name == "azure":
        from .ocr_azure import AzureOCR
        return AzureOCR(azure_endpoint or settings.azure_vision_endpoint,
                        azure_key or settings.azure_vision_key)
    raise ValueError(f"Unknown OCR_PROVIDER: {name}")


def get_ocr_provider(name: str | None = None, azure_endpoint: str | None = None,
                     azure_key: str | None = None, economy: str | None = None) -> OCRProvider:
    """Build an OCR engine, configured for the document's language.

    `economy` selects the recognition model: engines are per-script, so an engine loaded
    without a language hint can only emit characters from whatever dictionary it defaulted
    to. Before this argument existed every provider ran its English/Chinese default no
    matter what the document was, which is invisible on Round-1 Latin text and silently
    destructive on Thai or Cyrillic.

    Azure endpoint/key can be overridden at runtime (dashboard) — other providers read
    their settings (tesseract path, poppler) from `.env`.
    """
    from .ocr_languages import VLM, ocr_code, profile_for

    requested = (name or settings.ocr_provider or "rapidocr").lower()
    first_error: Exception | None = None
    if requested in _LANG_KEYED and not ocr_code(requested, economy):
        # The registry states this engine has NO model for the script. Building it anyway
        # succeeds — it just loads whatever dictionary it defaults to (English) and can then
        # only emit those characters, so Lao comes back as plausible-looking garbage with no
        # error anywhere. Not attempting it is the whole point of recording None.
        first_error = RuntimeError(
            f"{requested} has no recognition model for {profile_for(economy).script}")
    else:
        try:
            return _build(requested, economy, azure_endpoint, azure_key)
        except ValueError:
            raise                               # an unknown engine name is a config error
        except Exception as exc:
            # Python unbinds the `as` name at the end of the block, so keep it under our own.
            first_error = exc

    # The requested engine cannot read this script. Substituting beats both alternatives:
    # running it anyway emits only the characters its default dictionary holds — silent,
    # script-destroying corruption — and raising here would kill runs whose documents are
    # HTML and never touch OCR at all.
    profile = profile_for(economy)
    for candidate in profile.preferred:
        if candidate == requested or not ocr_code(candidate, economy):
            continue
        try:
            provider = _build(candidate, economy, azure_endpoint, azure_key)
        except Exception:
            continue
        provider.substituted_for = requested     # the orchestrator logs this, never hides it
        return provider

    # Last resort before admitting defeat: a vision model, which has no per-script dictionary
    # to be missing a letter from. It bills per page and returns no confidence, so it is never
    # preferred — but "no engine can read Lao" is not an answer a sealed live test accepts,
    # and the alternative to a costed page is a lost economy.
    if settings.vlm_ocr_auto_fallback and requested != VLM:
        try:
            provider = _build(VLM, economy, azure_endpoint, azure_key)
        except Exception:
            provider = None
        if provider is not None:
            provider.substituted_for = requested
            return provider

    return UnavailableOCR(
        f"No installed OCR engine can read {profile.script} ({profile.language}); "
        f"'{requested}' has no model for it and no alternative in {profile.preferred} is "
        f"available. Text-layer documents still work — this fails only if a scanned page "
        f"actually needs OCR. Original error: {first_error}")
