"""Economy → OCR language mapping, with the evidence behind each choice.

Why this file exists
--------------------
Until now the OCR layer had no language concept at all: RapidOCR was constructed with no
arguments (its frozen `rapidocr_onnxruntime` build only carries Chinese+English models),
`PaddleOCRProvider` hard-coded `lang="en"`, and Tesseract was called without `-l`. That is
adequate for Round 1 (Singapore, Australia, Malaysia are English/Malay, both plain Latin) and
silently wrong for every Finals economy that does not write in Latin script.

Recognition models are per-script, so the choice is load-bearing: an engine can only emit
characters that exist in its output dictionary. Two verified examples of that failing hard:

* PaddleOCR routes Vietnamese to its shared `latin` recogniser, whose dictionary contains the
  base letters (ă â đ ê ô ơ ư) but NONE of the 45 precomposed tone-marked forms (ế ộ ữ …), and
  no combining marks either. Vietnamese output is therefore corrupted deterministically, not
  probabilistically — a verbatim legal snippet cannot survive it.
* PaddleOCR's pre-v5 Cyrillic dictionary omits Ө/Ү entirely, so Mongolian loses two letters.

Evidence grade is recorded per language because most of these numbers do not exist. Anything
marked `validated=False` has NO published document-level CER for any engine, and our own
CER gate cannot be satisfied by citation — it has to be measured on a local ground-truth
sidecar before we claim a number. See docs/OCR_LANGUAGE_EVIDENCE.md.
"""
from __future__ import annotations

from dataclasses import dataclass

# Engine identifiers used elsewhere in the provider layer.
RAPIDOCR, PADDLE, TESSERACT, AZURE, GOOGLE = "rapidocr", "paddle", "tesseract", "azure", "google"


@dataclass(frozen=True)
class LangProfile:
    """How each engine names this economy's script, and which engine to prefer."""

    script: str
    #: `Rec.lang_rec` for rapidocr>=3.9; None when that engine has no model for the script.
    rapidocr: str | None
    #: PaddleOCR `lang=`; None when unsupported or known-broken for the script.
    paddle: str | None
    #: Tesseract `-l` value (may combine scripts, e.g. "tha+eng").
    tesseract: str | None
    #: Azure Document Intelligence locale; None when the service cannot read the script.
    azure: str | None
    #: Engine preference, best first, given CPU-only operation and verbatim requirements.
    preferred: tuple[str, ...]
    #: True only when a document-level accuracy figure exists that we could actually cite.
    validated: bool
    note: str


# Latin-script default. Round 1 economies all land here, which is why the missing language
# plumbing never showed up: English and Malay are exactly what the untuned models handle.
_LATIN = LangProfile(
    script="Latin", rapidocr="latin", paddle="en", tesseract="eng", azure="en",
    preferred=(RAPIDOCR, PADDLE, TESSERACT, AZURE), validated=True,
    note="Measured on the bundled scanned SG notice: CER 1.11% with RapidOCR.",
)

PROFILES: dict[str, LangProfile] = {
    # ── Round 1 ───────────────────────────────────────────────────────────────────────────
    "SG": _LATIN,
    "AU": _LATIN,
    "MY": _LATIN,          # Bahasa Malaysia is Latin script; the AGC portal is bilingual.
    "ID": _LATIN,

    # ── Finals candidates ─────────────────────────────────────────────────────────────────
    "TH": LangProfile(
        script="Thai", rapidocr="th", paddle="th", tesseract="tha+eng", azure="th",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=False,
        note=("Dedicated th_PP-OCRv5_mobile_rec exists (Apache-2.0). Vendor reports 82.68% but "
              "that is LINE-level exact match on a private set, not CER — do not quote it as CER. "
              "On ThaiOCRBench full-page OCR Tesseract scores 0.614, level with GPT-4o, so it is a "
              "reasonable fallback. No published Thai document CER exists for any engine."),
    ),
    "CN": LangProfile(
        script="Han (Simplified)", rapidocr="ch", paddle="ch", tesseract="chi_sim", azure="zh-Hans",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=False,
        note=("Best-served non-Latin script. PP-OCRv5 is the mature path; PP-OCRv6 is ~5x faster "
              "on CPU via OpenVINO. No independent CER measurement obtained."),
    ),
    "RU": LangProfile(
        script="Cyrillic", rapidocr="eslav", paddle="eslav", tesseract="rus", azure="ru",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=False,
        note=("Use eslav (East Slavic) ahead of the generic cyrillic model. Tesseract rus is weak "
              "out of the box (CER 21.6% on historical Russian print) — keep it last."),
    ),
    "MN": LangProfile(
        script="Cyrillic (Mongolian)", rapidocr="cyrillic", paddle="cyrillic", tesseract="mon",
        azure="mn", preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=False,
        note=("Cyrillic Khalkha only. PIN PaddleOCR >= v5: the v3/v4 cyrillic dictionary lacks Ө/Ү "
              "entirely. Tesseract's mon training text contains legacy mis-encodings (Ukrainian "
              "є/ї substituted for ө/ү). NO engine reads traditional vertical Mongol Bichig, which "
              "Mongolia has mandated alongside Cyrillic in official documents since Jan 2025 — that "
              "content must be flagged unextractable, never guessed at with a Cyrillic model."),
    ),
    "VN": LangProfile(
        # Deliberately NOT paddle: its latin dictionary cannot emit Vietnamese tone marks.
        script="Latin (Vietnamese)", rapidocr=None, paddle=None, tesseract="vie", azure="vi",
        preferred=(AZURE, TESSERACT), validated=True,
        note=("PaddleOCR/RapidOCR latin models are DISQUALIFIED here: 45 precomposed tone-marked "
              "letters are absent from the output dictionary, so diacritics are lost by "
              "construction. Measured on VieBookRead: Azure 0.04 CER, Tesseract vie 0.12, "
              "EasyOCR 0.25."),
    ),
    "LA": LangProfile(
        script="Lao", rapidocr=None, paddle=None, tesseract="lao", azure=None,
        preferred=(TESSERACT, GOOGLE), validated=False,
        note=("WEAKEST COVERAGE OF ANY TARGET ECONOMY. No Lao model in PaddleOCR, RapidOCR, "
              "EasyOCR or docTR. Azure Document Intelligence cannot read Lao. Tesseract's lao "
              "traineddata is the only offline option and has NO published accuracy of any kind. "
              "Google Cloud Vision is the only production service covering Lao. On real documents "
              "the best VLM scored ~64.5 NED (~35% error) while scoring 79 on synthetic Lao — "
              "treat any vendor Lao claim resting on synthetic data as unproven. Additional "
              "hazard: legacy Lao fonts map characters into upper-ASCII with no standard, so even "
              "text-layer extraction can yield garbage."),
    ),
}


def profile_for(economy: str | None) -> LangProfile:
    """Language profile for an economy code, defaulting to Latin script."""
    return PROFILES.get((economy or "").upper(), _LATIN)


def ocr_code(engine: str, economy: str | None) -> str | None:
    """The language code `engine` expects for `economy`, or None if it has no model."""
    return getattr(profile_for(economy), engine, None)


def is_validated(economy: str | None) -> bool:
    """False when no citable document-level accuracy exists for this economy's script."""
    return profile_for(economy).validated


def best_engine(economy: str | None, available: set[str] | None = None) -> str | None:
    """Highest-ranked engine for this economy that is actually available."""
    for eng in profile_for(economy).preferred:
        if available is None or eng in available:
            return eng
    return None
