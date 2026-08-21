"""Vision-model OCR — the engine of last resort for scripts no local model can read.

Why this exists
---------------
The per-script recognition models we ship do not cover every live-test economy, and the gaps
are MEASURED, not assumed (see `ocr_languages`): PaddleOCR's East-Slavic dictionary has no
Ө/Ү, so Mongolian loses four letters and Kazakh sixteen; its Latin dictionary has đ ă ơ ư but
none of the 45 precomposed Vietnamese tone forms; no maintained engine ships a Lao model at
all. Saying "no OCR engine can read this" is an honest answer, but it is not a usable one for
a sealed live test that may name any of nine economies.

A vision language model has no per-script dictionary — it reads what it sees — so it closes
the gap in one place instead of nine. It is deliberately the LAST engine tried, for three
reasons that should stay visible:

  * it costs money per page, where the local engines cost only CPU;
  * it returns no per-character confidence, so the CER gate has nothing to grade. We report
    `confidence=None` rather than inventing a number that would read as measured;
  * a VLM can HALLUCINATE fluent, plausible statutory text. Classical OCR degrades into
    visible noise; a VLM degrades into a clean sentence that was never in the document. For a
    deliverable whose Verbatim Snippet column IS the statute, that is the more dangerous
    failure, so every page produced here is marked and the mark travels into Notes.

Mitigations against the third: temperature 0, an instruction that transcribes and refuses to
translate or summarise, and a per-page marker the pipeline can surface to a reviewer.

Open weights, not just hosted
-----------------------------
Section 3 of the submission declares that the core pipeline runs with no proprietary API, and
the README makes that apply to OCR as well as to the language model. So this provider speaks
the OpenAI chat-completions shape and takes its base URL from configuration: point it at
OpenRouter for a hosted run, or at a local Ollama / vLLM serving an open-weights VLM
(Qwen2.5-VL, InternVL) for a run with no external service at all. Same code path either way.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from ..config import settings
from .ocr_base import OCRPageResult, OCRProvider, OCRResult

# Transcribe, do not interpret. Every clause here is defending against a specific way a chat
# model damages a legal citation: it answers instead of transcribing, it tidies the layout, it
# helpfully translates, or it fills an illegible patch with something that reads well.
_SYSTEM = (
    "You are a document transcription engine, not an assistant. Return the text of the page "
    "image EXACTLY as printed.\n"
    "- Preserve the original language and script. NEVER translate.\n"
    "- Preserve article and section headings, numbering and punctuation verbatim.\n"
    "- Do not summarise, explain, correct spelling, or add commentary.\n"
    "- If a region is illegible, write [illegible] there. NEVER guess at the wording: an "
    "invented sentence is far worse than an acknowledged gap, because this text is quoted as "
    "a legal citation.\n"
    "- Output the page text and nothing else — no preamble, no code fences."
)


class VLMOCRProvider(OCRProvider):
    """OCR by asking a vision model to transcribe each rendered page."""

    name = "vlm"

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, lang: str | None = None, dpi: int = 200,
                 max_pages: int = 40, timeout: int = 180):
        import pypdfium2  # noqa: F401  — fail here, not mid-run, if rendering is unavailable

        self._pdfium = pypdfium2
        self.base_url = (base_url or settings.vlm_ocr_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.vlm_ocr_api_key
        self.model = model or settings.vlm_ocr_model
        self.lang = lang
        # 200 dpi, not the 300 the classical engines want: a VLM is billed per image tile, and
        # doubling the pixels doubles the cost for accuracy that saturates well before then.
        self._scale = dpi / 72.0
        # A cost ceiling with a name. A 600-page compilation silently costing 600 model calls
        # is exactly the kind of bill nobody notices until it has already been paid.
        self.max_pages = max_pages
        self.timeout = timeout
        if not self.model:
            raise RuntimeError(
                "VLM OCR needs a model name (VLM_OCR_MODEL), e.g. 'qwen/qwen2.5-vl-72b-instruct' "
                "on OpenRouter or 'qwen2.5vl' on a local Ollama.")

    # ── rendering ────────────────────────────────────────────────────────────────────
    def _page_png(self, page) -> bytes:
        return page.render(scale=self._scale).to_pil().convert("RGB")._repr_png_()

    # ── one model call ───────────────────────────────────────────────────────────────
    def _transcribe(self, png: bytes) -> str:
        data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        hint = (f"The page is written in {self.lang}. " if self.lang else "")
        body = {
            "model": self.model,
            "temperature": 0,        # transcription is not a creative task
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": [
                    {"type": "text",
                     "text": hint + "Transcribe this page exactly as printed."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"VLM OCR call failed ({exc.code}) against {self.base_url}: "
                f"{exc.read()[:300].decode('utf-8', 'replace')}") from exc
        return (payload["choices"][0]["message"]["content"] or "").strip()

    # ── the interface ────────────────────────────────────────────────────────────────
    def ocr_pdf(self, pdf_path: str, pages: list[int] | None = None) -> OCRResult:
        doc = self._pdfium.PdfDocument(pdf_path)
        wanted = pages or list(range(1, len(doc) + 1))
        wanted = [n for n in wanted if 1 <= n <= len(doc)][: self.max_pages]

        out: list[OCRPageResult] = []
        for n in wanted:
            text = self._transcribe(self._page_png(doc[n - 1]))
            # confidence stays None ON PURPOSE. A VLM emits no per-character probability, and
            # a fabricated 0.9 here would flow into ocr_quality.cer and be read as measured.
            out.append(OCRPageResult(page=n, text=text, confidence=None))
        return OCRResult(text="\n\n".join(p.text for p in out), pages=out, provider=self.name)
