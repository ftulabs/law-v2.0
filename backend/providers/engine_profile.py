"""What this economy should run on, and why — one resolved answer per economy.

Three separate final-round requirements turn out to be the same question asked three ways:

  * the run must be fast enough for a sixty-minute live test, and English and non-English
    documents do not behave alike in the parts that cost time;
  * the evidence workbook now carries `Language of Source`, so the language of a document is a
    reportable fact rather than an internal detail;
  * criterion C4b wants engines swappable, and the Word template's Section 5 asks for the
    *known weaknesses of each engine on legal text* — a preference we cannot state unless we
    have written down what we prefer and on what basis.

So the answer is one object per economy: which OCR engine, which reranker, which retrieval lane,
which language model, and for each of those a REASON and an EVIDENCE class. Nothing here
overrides a human — every field is a default the interface can change — but the default is
recorded rather than emergent, and a default nobody can explain is a default nobody should ship.

`evidence` is the field that keeps this honest:

    MEASURED   a number produced in this repository, quoted in the reason
    DOCUMENTED a property of the tool stated by its maintainers (a model's language list)
    ASSUMED    a reasonable default nobody has yet tested — say so, and it stays visible

Read it with `profile_for("CN")`, or on the command line:

    python -m backend.providers.engine_profile
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .ocr_languages import LangProfile, is_english_text, is_latin_script, profile_for as _lang


class Evidence(str, Enum):
    MEASURED = "measured"
    DOCUMENTED = "documented"
    ASSUMED = "assumed"


@dataclass(frozen=True)
class Choice:
    """One resolved setting, with the reason it was chosen and how strong that reason is."""
    value: str | None
    reason: str
    evidence: Evidence = Evidence.ASSUMED

    def __str__(self) -> str:
        return f"{self.value or '(none)'} — {self.reason} [{self.evidence.value}]"


@dataclass(frozen=True)
class EngineProfile:
    economy: str
    language: str
    script: str
    lane: str                 # "english" | "non_english"
    ocr: Choice
    reranker: Choice
    llm: Choice
    notes: list[str] = field(default_factory=list)

    @property
    def is_english(self) -> bool:
        return self.lane == LANE_ENGLISH

    @property
    def language_of_source(self) -> str:
        """What the Language of Source column reports for this economy — read from the same
        registry the OCR and reranker choices come from, so the column can never claim a
        language the pipeline did not actually assume."""
        return self.language


# ── the two lanes ────────────────────────────────────────────────────────────────────
#
# The split is not cosmetic. Measured on this machine, the parts that differ are:
#
#   reranking   English ms-marco-MiniLM-L-6-v2 runs 245 pairs/s. The multilingual
#               bge-reranker-v2-m3 runs 9.9 — 568M parameters against 22M. The first full
#               China run spent 40,462 seconds inside retrieval for 268 provisions, where
#               Singapore spent 100 seconds for 3,218. Turning the reranker off for non-Latin
#               brought that run to 30 seconds, a 35x speed-up.
#
#   tokenising  Han and kana have no inter-word spaces, so BM25 indexes character bigrams
#               instead of words. Latin keeps the exact Round-1 tokeniser, because the
#               retrieval parameters were swept against it and are only valid for it.
#
#   grading     the prompt names the snippet language and requires English output, while the
#               snippet itself is never rewritten — a translated snippet is a false citation.
#
#
# The lane is keyed on LANGUAGE, not script. Indonesia and Timor-Leste write in Latin letters and
# still need the non-English lane: the cross-encoder is an English model, and its score is
# fused into the ranking at the same weight as BM25, so applying it to Bahasa degrades the
# result rather than merely failing to improve it. Keying on script put both economies on the
# English lane for no better reason than a shared alphabet.
LANE_ENGLISH = "english"
LANE_NON_ENGLISH = "non_english"
LANE_NON_LATIN = LANE_NON_ENGLISH        # the name this lane had while it was keyed on script

# Two measurements decide this, and they point the same way.
#
# QUALITY. Asked to rank five PIPL/CSL articles against the 6.2 legal test, ms-marco-MiniLM
# put the correct one (art. 40, "store personal data within the territory") LAST of five:
# order [2,3,1,4,0]. bge-reranker-v2-m3 put it first: [0,3,1,4,2]. So an English cross-encoder
# on Chinese is not merely uninformative, it is INVERTED — which is why a non-Latin economy
# must never fall back to it. That was an assumption until it was measured; now it is not.
#
# COST. bge-reranker-v2-m3 is 568M parameters against 23M, and runs 4.2 pairs/s here against
# 72.7 — an order of magnitude, and it turned one China pillar into an 11-hour run.
#
# ALTERNATIVES, tried and rejected on this machine, not on reputation:
#   Alibaba-NLP/gte-multilingual-reranker-base (306M) — IndexError inside its custom modelling
#     code under the installed sentence-transformers.
#   jinaai/jina-reranker-v2-base-multilingual (278M) — needs a transformers API that the pinned
#     version no longer exports (create_position_ids_from_input_ids). Downgrading transformers
#     is not free: the deploy host pins torch 2.2.2, which already constrains it.
# So bge-m3 is not merely the chosen multilingual reranker, it is the only one that RUNS here.
#
# What "off" actually costs is also measured, and it is not what one would guess: with the
# reranker off, retrieval_score goes UP (0.514 against 0.303 on the SG sample, +0.053 on final
# confidence) and the shortlist was IDENTICAL — 20 of 20 rows. The blend is
# 0.5*hybrid + 0.5*sigmoid(cross), and ms-marco's logits on legal text are strongly negative,
# so the reranker was dragging scores down. Nothing is dropped for want of a rerank score.
_RERANK_OFF_REASON = (
    "no reranker: an English cross-encoder ranks the correct Chinese provision LAST (measured), "
    "and the multilingual one is an order of magnitude slower (4.2 pairs/s against 72.7) — it turned "
    "one China pillar into an 11-hour run for 268 provisions. BM25 + multilingual embeddings "
    "return the same run in 30 seconds. Re-enable with cross_encoder_multilingual_enabled if "
    "a GPU is available")
_RERANK_ON_REASON = (
    "ms-marco-MiniLM-L-6-v2: 245 pairs/s here, and the retrieval parameters in CLAUDE.md were "
    "swept with it in place — provision recall 1.00 on SG and AU, 0.875 on MY")

# Language models. We do not yet have a bake-off, so these are stated as assumptions and will be
# replaced by measurements before the engines are declared on 30 September — a declaration is
# frozen after that date and cannot be revised, so an unmeasured preference is a liability.
_LLM_DEFAULT = Choice(
    None, "no per-economy preference yet — the two declared engines are chosen by a bake-off "
          "against data/ground_truth/rdtii_reference_p67.csv, not per country",
    Evidence.ASSUMED)


def _ocr_choice(code: str, lang: LangProfile) -> Choice:
    """The OCR engine that would ACTUALLY run here, and why.

    Deliberately resolved through the factory rather than read off the registry's preference
    list. The registry states what the engine family supports; the factory knows what is
    installed on this machine, and the two disagree — Mongolian resolves to a 'cyrillic' model
    that the packaged `rapidocr_onnxruntime` build does not ship. This table goes into the
    README and the Word submission, where a stated preference that does not survive contact
    with the machine is worse than an admitted gap.
    """
    from .ocr_factory import UnavailableOCR, get_ocr_provider
    from .ocr_languages import ocr_code

    try:
        provider = get_ocr_provider(economy=code)
    except Exception as exc:                        # never let a table crash a run
        return Choice(None, f"could not resolve an OCR engine: {type(exc).__name__}",
                      Evidence.DOCUMENTED)

    if isinstance(provider, UnavailableOCR):
        return Choice(None, f"no OCR engine installed here reads {lang.script}. Text-layer "
                            f"documents are unaffected; a scanned page in this script fails "
                            f"loudly rather than returning empty text", Evidence.MEASURED)

    model = ocr_code(provider.name, code)
    substituted = getattr(provider, "substituted_for", None)
    prefix = (f"{provider.name} (substituted for {substituted}, which has no model for "
              f"{lang.script})" if substituted else provider.name)
    if lang.validated:
        return Choice(provider.name, f"{prefix} with the '{model}' model — CER measured on a "
                                     f"bundled scan for this script", Evidence.MEASURED)
    return Choice(provider.name, f"{prefix} with the '{model}' model — the engine ships a model "
                                 f"for {lang.script}, but no document-level accuracy has been "
                                 f"measured here", Evidence.DOCUMENTED)


#: What `ocr` says when nobody asked the machine. Distinct from `Choice(None, ...)`, which is
#: the answer "no engine here can read this script" — a real finding. This is "not asked".
_OCR_NOT_PROBED = Choice(None, "engines were not probed for this call", Evidence.ASSUMED)


def profile_for(economy: str | None, probe_ocr: bool = True) -> EngineProfile:
    """The resolved engine profile for an economy. Never raises; unknown codes get the Latin
    default, which is also the safest thing to do with an economy we have not met.

    `probe_ocr=False` skips resolving the engine through the factory. That resolution
    CONSTRUCTS the provider — which loads PP-OCRv5 detection and recognition weights — so a
    caller that only wants the language, lane or reranker pays 1.3s per economy for a field it
    never reads. The dashboard's readiness globe was doing exactly that for twelve economies
    before it could paint: 15.7s measured, on a machine whose models were already downloaded.
    """
    code = (economy or "").upper()
    lang = _lang(code)
    latin = is_latin_script(code)
    english = is_english_text(code)
    notes: list[str] = []

    if not lang.validated:
        notes.append(f"OCR accuracy for {lang.script} is unvalidated here — the engine has a "
                     f"model, but no CER figure exists that we could cite.")
    if not lang.spaces_between_words:
        notes.append(f"{lang.language} is written without inter-word spaces, so BM25 indexes "
                     f"character bigrams. Word-level term statistics do not apply.")
    if lang.legacy_encoding_risk:
        notes.append(f"{lang.language} PDFs can carry a legacy non-Unicode text layer that "
                     f"extracts as mojibake with no OCR involved — script validity is checked.")

    return EngineProfile(
        economy=code,
        language=lang.language,
        script=lang.script,
        lane=LANE_ENGLISH if english else LANE_NON_ENGLISH,
        ocr=(_ocr_choice(code, lang) if probe_ocr else _OCR_NOT_PROBED),
        reranker=(Choice("cross-encoder/ms-marco-MiniLM-L-6-v2", _RERANK_ON_REASON,
                         Evidence.MEASURED) if english
                  else Choice(None, _RERANK_OFF_REASON, Evidence.MEASURED)),
        llm=_LLM_DEFAULT,
        notes=notes,
    )


def summary_table(codes: list[str] | None = None) -> str:
    """The table that goes into the README and the Word submission, generated rather than typed
    so it cannot drift from what the code actually does."""
    from ..schemas import ECONOMY_UN_NAME
    codes = codes or list(ECONOMY_UN_NAME)
    rows = ["| Economy | Language of Source | Lane | OCR engine | Reranker |",
            "| :--- | :--- | :--- | :--- | :--- |"]
    for c in codes:
        p = profile_for(c)
        rows.append(f"| {ECONOMY_UN_NAME.get(c, c)} | {p.language} | {p.lane} | "
                    f"{p.ocr.value or '—'} | {p.reranker.value or 'off'} |")
    return "\n".join(rows)


if __name__ == "__main__":
    from ..schemas import ECONOMY_UN_NAME

    for c in ECONOMY_UN_NAME:
        p = profile_for(c)
        print(f"\n=== {ECONOMY_UN_NAME[c]} ({c}) — {p.language} / {p.script} · lane={p.lane} ===")
        print(f"  OCR      : {p.ocr}")
        print(f"  reranker : {p.reranker}")
        print(f"  LLM      : {p.llm}")
        for n in p.notes:
            print(f"  note     : {n}")
