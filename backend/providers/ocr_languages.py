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
#: Vision-model OCR. Unlike every engine above it has NO per-script dictionary, so it is
#: never disqualified by script — which is exactly why it is the last-resort fallback for
#: Mongolian, Kazakh, Vietnamese and Lao. See ocr_vlm.py for what it costs to use it.
VLM = "vlm"

# ── What the public benchmarks do and do not settle (read 2026-08-22) ────────────────
#
# Two benchmarks were checked before choosing anything, and they answer different questions.
#
# olmOCR-bench (AllenAI, 1,403 PDFs, 7,010 unit tests) is ENGLISH-ONLY. It measures document
# parsing — reading order, table structure, and whether headers/footers are correctly EXCLUDED
# — so it is relevant to extraction quality and says nothing at all about our hard scripts.
#
# MDPBench (3,400 documents, 17 languages, digital and photographed) is the one that covers
# the languages we need. Per-language scores for the systems that matter here:
#
#                                 overall   vi    th    ru    id    zh
#   Gemini-3-pro-preview             86.4  91.6  85.5  90.4  91.5  84.9   proprietary
#   MonkeyOCRv2-S-Parsing            82.5  87.2  88.7  87.1  85.4  78.0   open, self-host only
#   dots.ocr                         76.5  87.8  68.5  77.3  82.5  66.8   open, self-host only
#   Qwen3-VL-8B                      68.3  79.1  61.9  58.4  68.5  57.9   open, ON OpenRouter
#   PP-StructureV3                   45.4  68.9  15.4   7.7  69.6   7.5   Paddle's PIPELINE
#
# Three conclusions, and the third is the one that constrains us.
#
# 1. Purpose-built document parsers beat general vision models by a wide margin (MonkeyOCRv2-S
#    82.5 against Qwen3-VL-8B's 68.3). None of them is served by OpenRouter — they are
#    self-host-only — so the hosted fallback has to be a general VLM, and Qwen3-VL-8B is the
#    best-evidenced one we can actually reach.
#
# 2. NEITHER benchmark covers Lao, Mongolian or Kazakh — our three hardest scripts. Every
#    number about them remains our own or nobody's.
#
# 3. PP-StructureV3's collapse on Thai (15.4), Russian (7.7) and Chinese (7.5) is a warning,
#    NOT a verdict on the engines below. It scores PaddleOCR's document-parsing PIPELINE on
#    photographed pages, whereas we call the per-script RECOGNISER (th_PP-OCRv5_mobile_rec,
#    eslav_PP-OCRv5_mobile_rec) on pages we render ourselves from clean government PDFs — a
#    different system on easier input. Treating a pipeline score as a recogniser score would be
#    the same category error as quoting line-level accuracy as CER. It does mean the Thai and
#    Cyrillic Paddle paths stay `validated=False` until we measure them on a local sidecar.


@dataclass(frozen=True)
class LangProfile:
    """How each engine names this economy's script, and which engine to prefer.

    The fields after `validated` are NOT about OCR — they describe properties of the script
    that break stages further down the pipeline, and each one has already caused a real bug
    class somewhere in the industry:

    * `spaces_between_words=False` (Thai, Lao, Chinese) breaks every whitespace tokeniser.
      BM25 retrieval silently degrades to near-zero recall because the "words" it indexes are
      whole sentences, and this happens even when OCR is perfect. A segmenter is required.
    * `stacking_marks=True` (Thai, Lao, Vietnamese) is the dominant OCR error mode for these
      scripts, and it also means CER must be computed on Unicode-normalised text or the metric
      reports phantom errors from NFC/NFD differences alone.
    * `legacy_encoding_risk=True` means a PDF can carry a perfectly good text layer that still
      extracts as mojibake, with no OCR involved — so the OCR-side CER gate cannot see it.
      A Unicode-range validity check on extracted text is the only defence.
    """

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
    #: Unicode ranges the extracted text should predominantly fall in, for a sanity check.
    unicode_ranges: tuple[tuple[int, int], ...] = ()
    #: False for scripts written without inter-word spaces → needs a word segmenter.
    spaces_between_words: bool = True
    #: True when vowel/tone marks stack on a base character.
    stacking_marks: bool = False
    #: True when non-Unicode legacy font encodings are common in older official PDFs.
    legacy_encoding_risk: bool = False
    #: Word segmenter to use when `spaces_between_words` is False.
    segmenter: str | None = None
    #: Language the AUTHORITATIVE statute text is written in, named the way a person would say
    #: it. Fed to the grading LLM: a model told "the snippet is in Mongolian" behaves markedly
    #: better than one left to infer it from the bytes.
    language: str = "English"


# Latin-script default. Round 1 economies all land here, which is why the missing language
# plumbing never showed up: English and Malay are exactly what the untuned models handle.
_LATIN = LangProfile(
    script="Latin", rapidocr="latin", paddle="en", tesseract="eng", azure="en",
    preferred=(RAPIDOCR, PADDLE, TESSERACT, AZURE), validated=True,
    note="Measured on the bundled scanned SG notice: CER 1.11% with RapidOCR.",
    unicode_ranges=((0x0020, 0x024F),),
)

PROFILES: dict[str, LangProfile] = {
    # ── Round 1 ───────────────────────────────────────────────────────────────────────────
    "SG": _LATIN,
    "AU": _LATIN,
    "MY": _LATIN,          # Bahasa Malaysia is Latin script; the AGC portal is bilingual.

    # ── Finals candidates ─────────────────────────────────────────────────────────────────
    "ID": LangProfile(
        # Was mapped to the Latin default, which is right about the SCRIPT and wrong about
        # everything the script does not decide. `_LATIN.language` is "English", so the
        # Language of Source column — the new column that drives criterion C1c — would have
        # reported every Indonesian statute as English. Bahasa Indonesia is plain ASCII, so
        # no tokeniser or OCR error would ever have surfaced the mistake.
        script="Latin", rapidocr="latin", paddle="en", tesseract="ind+eng", azure="id",
        preferred=(RAPIDOCR, PADDLE, TESSERACT, AZURE, VLM), validated=True,
        note=("Lowest script risk of the nine: Bahasa Indonesia is written in unaccented ASCII "
              "Latin, so the Round-1 extraction path applies unchanged. The obstacle here is "
              "ACCESS, not reading — peraturan.bpk.go.id sits behind a WAF that 403s a plain "
              "client (the browser lane clears it). It does NOT disallow us: its robots.txt "
              "blocks nine named AI crawlers and grants the wildcard group, which is where "
              "VeriTrade-Research/0.2 falls. See data/sources.yaml and pipeline/robots.py."),
        unicode_ranges=((0x0020, 0x024F),),

        language="Indonesian",
    ),
    "TH": LangProfile(
        script="Thai", rapidocr="th", paddle="th", tesseract="tha+eng", azure="th",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT, VLM), validated=False,
        note=("Dedicated th_PP-OCRv5_mobile_rec exists (Apache-2.0). Vendor reports 82.68% but "
              "that is LINE-level exact match on a private set, not CER — do not quote it as CER. "
              "On ThaiOCRBench full-page OCR Tesseract scores 0.614, level with GPT-4o, so it is a "
              "reasonable fallback. No published Thai document CER exists for any engine."),
        unicode_ranges=((0x0E00, 0x0E7F),), spaces_between_words=False,
        stacking_marks=True, segmenter="pythainlp",
    
        language="Thai",
    ),
    "CN": LangProfile(
        script="Han (Simplified)", rapidocr="ch", paddle="ch", tesseract="chi_sim", azure="zh-Hans",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT, VLM), validated=False,
        note=("Best-served non-Latin script. PP-OCRv5 is the mature path; PP-OCRv6 is ~5x faster "
              "on CPU via OpenVINO. No independent CER measurement obtained."),
        unicode_ranges=((0x4E00, 0x9FFF), (0x3000, 0x303F)), spaces_between_words=False,
        segmenter="jieba",
    
        language="Chinese (Simplified)",
    ),
    "RU": LangProfile(
        # paddle="ru", NOT "eslav": PaddleOCR 3.x renamed its language keys, and the old names
        # raise ValueError("No models are available for the language 'eslav'") — which the
        # factory caught and turned into "no engine can read Cyrillic". The engine was there
        # the whole time; we were asking for it by a name that no longer exists.
        script="Cyrillic", rapidocr="eslav", paddle="ru", tesseract="rus", azure="ru",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT, VLM), validated=False,
        note=("paddle lang 'ru' loads eslav_PP-OCRv5_mobile_rec (East Slavic). Verified against "
              "its shipped 517-character dictionary: full Russian coverage. Tesseract rus is weak "
              "out of the box (CER 21.6% on historical Russian print) — keep it last."),
        unicode_ranges=((0x0400, 0x04FF),),
    
        language="Russian",
    ),
    "MN": LangProfile(
        # paddle=None is now MEASURED, not inherited caution. PaddleOCR 3.x has no "cyrillic"
        # key at all; the nearest is "ru" -> eslav_PP-OCRv5_mobile_rec, and reading that model's
        # own character dictionary (517 entries) shows Ө Ү ө ү are all absent. Mongolian
        # would come back missing four of its letters, in fluent-looking text, with no error.
        script="Cyrillic (Mongolian)", rapidocr="cyrillic", paddle=None, tesseract="mon",
        azure="mn", preferred=(RAPIDOCR, AZURE, TESSERACT, VLM), validated=False,
        note=("Cyrillic Khalkha only. PaddleOCR is DISQUALIFIED by measurement: the East-Slavic "
              "dictionary it would load contains no Ө/Ү/ө/ү. Same defect historically: "
              "the v3/v4 cyrillic dictionary lacks Ө/Ү "
              "entirely. Tesseract's mon training text contains legacy mis-encodings (Ukrainian "
              "є/ї substituted for ө/ү). On vertical Mongol Bichig: no engine reads it, and "
              "Tesseract's `mon` model will silently emit CYRILLIC when fed it (verified: "
              "mon.unicharset has 70 Cyrillic entries and 0 in U+1800-18AF) — a failure that "
              "looks like success. But it is NOT on the critical path for legislation: a sweep "
              "of legalinfo.mn found zero U+1800-18AF bytes across nine pages, and the Jan 2025 "
              "dual-script mandate binds administrative record-keeping rather than statutes. "
              "Keep the U+1800-18AF check as a guard, not as an expected case."),
        unicode_ranges=((0x0400, 0x04FF),),
    
        language="Mongolian",
    ),
    "KZ": LangProfile(
        # Kazakhstan was ABSENT from this table until the live-test nine were declared, so
        # profile_for("KZ") returned the Latin default: is_latin_script() said True, the English
        # cross-encoder was applied to Cyrillic, and OCR would have loaded a Latin dictionary.
        # Every one of those is silent. A missing key is the most expensive kind of entry here.
        script="Cyrillic (Kazakh)", rapidocr="cyrillic", paddle=None, tesseract="kaz",
        azure="kk", preferred=(RAPIDOCR, AZURE, TESSERACT, VLM), validated=False,
        note=("Worst Cyrillic coverage of the nine. Measured against eslav_PP-OCRv5_mobile_rec's "
              "own dictionary, SIXTEEN of the 42 Kazakh letters are missing (Ә Ғ Қ Ң Ө Ұ Ү Һ "
              "and their lower case; only І/і are present), so PaddleOCR is disqualified by "
              "measurement rather than by caution. Second hazard, unique to Kazakhstan: the "
              "2017-2025 Latin-alphabet transition means adil.gov.kz carries statutes in BOTH "
              "Cyrillic and Latin orthography, and Russian is co-official — so script detection "
              "must run per document, never per economy."),
        unicode_ranges=((0x0400, 0x04FF), (0x0020, 0x024F)),

        language="Kazakh",
    ),
    "VN": LangProfile(
        # Deliberately NOT paddle: its latin dictionary cannot emit Vietnamese tone marks.
        script="Latin (Vietnamese)", rapidocr=None, paddle=None, tesseract="vie", azure="vi",
        preferred=(AZURE, TESSERACT, VLM), validated=True,
        note=("PaddleOCR/RapidOCR latin models are DISQUALIFIED here, and it is now measured: "
              "latin_PP-OCRv5_mobile_rec's 836-character dictionary DOES carry đ ă ơ ư but "
              "NOT one of the precomposed tone forms (ế ộ ữ ạ ằ …), so diacritics are lost by "
              "construction. Note paddle lang 'vi' CONSTRUCTS without error and quietly loads "
              "that same latin model — a config that looks like it works and does not. Measured on VieBookRead: Azure 0.04 CER, Tesseract vie 0.12, "
              "EasyOCR 0.25."),
        unicode_ranges=((0x0020, 0x024F), (0x1EA0, 0x1EF9)), stacking_marks=True,
    
        language="Vietnamese",
    ),
    "IN": LangProfile(
        # indiacode.nic.in publishes Central Acts in ENGLISH as the authoritative text, so the
        # Latin path carries the load and Devanagari is only needed for Hindi editions. That
        # makes India by far the cheapest non-Round-1 economy on the extraction side.
        script="Latin (+ Devanagari for Hindi editions)",
        rapidocr="latin", paddle="en", tesseract="eng+hin", azure="en",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=True,
        note=("English is the authoritative language of Central Acts, so default to the Latin "
              "path. If a Hindi edition must be read, note Devanagari is hard for CLASSICAL "
              "engines: measured CER 34.3% for EasyOCR on real printed Devanagari versus 4.4% "
              "for the best VLM (arXiv 2606.29213, Jun 2026) — the shirorekha headline joins "
              "characters within a word so there is no whitespace to segment on, and matras "
              "attach above/below/either side of a base glyph or conjunct. No head-to-head of "
              "Tesseract vs Google vs Azure on Devanagari exists in the literature."),
        unicode_ranges=((0x0020, 0x024F), (0x0900, 0x097F)),
    ),
    "TL": LangProfile(
        # Portuguese + Tetum, both Latin script with complete legacy codepage coverage
        # (ISO-8859-1/CP1252), so extraction risk is low. The hazard here is NOT the script.
        script="Latin (Portuguese / Tetum)",
        rapidocr="latin", paddle="en", tesseract="por+eng", azure="pt",
        preferred=(RAPIDOCR, PADDLE, AZURE, TESSERACT), validated=True,
        note=("Lowest script risk of any candidate: every Portuguese diacritic sits in Latin-1 "
              "Supplement and Tetum is near-ASCII. The real hazard is NORMALISATION, not OCR — "
              "U+00BA MASCULINE ORDINAL INDICATOR (º), used in every Portuguese article "
              "reference ('Artigo 1.º', 'Lei n.º 13.709'), carries a compatibility "
              "decomposition to plain 'o'. Applying NFKC silently rewrites 'n.º' to 'n.o' and "
              "breaks citation matching, while leaving a mis-OCR'd degree sign (U+00B0, no "
              "decomposition) untouched — so normalisation neither repairs nor flags the error. "
              "Use NFC, never NFKC, on Portuguese text. Unicode only classified º/° as "
              "confusable in the 18.0 beta (2026-08-06), so tools on 17.0 will not detect the "
              "substitution. A citation matcher must treat n.º / nº / n.o / n.° / no alike."),
        unicode_ranges=((0x0020, 0x024F),),
        # Without this the Latin default applies and `language` stays "English" — which is
        # right about the alphabet and wrong about the statute. Language of Source is the
        # column criterion C1c is marked on, and it would have reported every Timorese law as
        # English; the grading prompt would also have been told the wrong snippet language.
        # Both official languages are used for legislation, often for the same instrument
        # (mj.gov.tl ships the Constitution as ConstituicaoRDTL_Portugues.pdf AND
        # ConstituicaoRDTL_tetum.pdf), so detection must run per document. Portuguese is named
        # here because that is what the operative text is drafted in.
        language="Portuguese",
    ),
    "LA": LangProfile(
        script="Lao", rapidocr=None, paddle=None, tesseract="lao", azure=None,
        preferred=(TESSERACT, GOOGLE, VLM), validated=False,
        note=("WEAKEST COVERAGE OF ANY TARGET ECONOMY. No Lao model in PaddleOCR, RapidOCR, "
              "EasyOCR or docTR. Azure Document Intelligence cannot read Lao. Tesseract's lao "
              "traineddata is the only offline option and has NO published accuracy of any kind. "
              "Google Cloud Vision is the only production service covering Lao. On real documents "
              "the best VLM scored ~64.5 NED (~35% error) while scoring 79 on synthetic Lao — "
              "treat any vendor Lao claim resting on synthetic data as unproven. Additional "
              "hazard: legacy Lao fonts map characters into upper-ASCII with no standard, so even "
              "text-layer extraction can yield garbage. Also: ໝ (U+0EDD), which opens the "
              "chapter marker ໝວດທີ, has a <compat> decomposition, so NFC will not merge it "
              "and NFD will not split it — government HTML emits the precomposed form while "
              "OCR emits the decomposed one, so a single-form regex loses every chapter "
              "heading from one of the two ingestion paths. Match both forms."),
        unicode_ranges=((0x0E80, 0x0EFF),), spaces_between_words=False,
        stacking_marks=True, legacy_encoding_risk=True, segmenter="laonlp",
    
        language="Lao",
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


def is_latin_script(economy: str | None) -> bool:
    """True when this economy's statutes are written in Latin script.

    Used well outside OCR: the cross-encoder reranker, the mock grader's keyword logic and
    the LLM prompt all behave differently once the provision text is not Latin. India counts
    as Latin — its statutes are enacted and published in English; the Devanagari note in its
    profile is about Hindi gazette editions, not the authoritative text.
    """
    return profile_for(economy).script.startswith("Latin")


def is_english_text(economy: str | None) -> bool:
    """True when the AUTHORITATIVE statute text is in English.

    Script and language answer different questions, and conflating them was a real defect.
    `is_latin_script` is the right test for TOKENISATION — Vietnamese and Indonesian are Latin
    and do tokenise as words. It is the wrong test for the CROSS-ENCODER, which is an English
    model: ms-marco-MiniLM scoring Vietnamese is the same category of noise as ms-marco
    scoring Chinese, and it is fused into the ranking at the same weight as BM25. Before this
    split, Viet Nam and Indonesia — two of the nine — took the English reranker purely because
    their alphabet has the same letters.
    """
    return profile_for(economy).language == "English"


def needs_segmentation(economy: str | None) -> str | None:
    """Word segmenter required before whitespace tokenisation, or None.

    Thai, Lao and Chinese are written without inter-word spaces. Splitting them on whitespace
    yields "words" that are whole sentences, so BM25 indexes almost nothing matchable and
    keyword retrieval quietly collapses — with perfect OCR and no error anywhere to see.
    """
    p = profile_for(economy)
    return None if p.spaces_between_words else p.segmenter


def script_validity(text: str, economy: str | None, sample: int = 4000) -> float:
    """Fraction of letter-ish characters that fall inside the expected script ranges.

    This is the defence against the failure the CER gate structurally cannot catch: a PDF
    carrying a text layer encoded with a legacy non-Unicode font. Lao is the known case —
    the language never adopted an 8-bit standard, so fonts such as Saysettha map Lao letters
    into the upper-ASCII range with no agreed convention. Extraction then "succeeds", the
    density check passes, OCR never runs, and the provision text is mojibake. Measuring OCR
    accuracy cannot see this, because no OCR happened.

    Returns 1.0 when nothing is checkable (no ranges configured, or no letters found), so a
    caller can treat "low score" as a genuine signal rather than a default.
    """
    ranges = profile_for(economy).unicode_ranges
    if not ranges or not text:
        return 1.0
    letters = [c for c in text[:sample] if c.isalpha()]
    if not letters:
        return 1.0
    ok = sum(1 for c in letters if any(lo <= ord(c) <= hi for lo, hi in ranges))
    return ok / len(letters)


def looks_mojibake(text: str, economy: str | None, floor: float = 0.5) -> bool:
    """True when extracted text is mostly outside the economy's script. Advisory only."""
    return script_validity(text, economy) < floor
