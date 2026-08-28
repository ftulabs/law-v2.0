"""Pydantic data schemas — the single source of truth for every record that
flows through the pipeline and lands in CSV/JSON exports and the audit store.

Design rule: a mapping is only as trustworthy as its evidence, so EvidenceMapping
carries the verbatim snippet, article ref, source URL and raw retrieval context
right alongside the model's rationale and score.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────── enums ───────────────────────────
class Economy(str, Enum):
    SG = "SG"   # Singapore      — mandatory, every round
    AU = "AU"   # Australia      — mandatory, every round
    MY = "MY"   # Malaysia       — mandatory, every round
    CN = "CN"   # China          — final-round list
    IN = "IN"   # India          — final-round list
    ID = "ID"   # Indonesia      — final-round list
    LA = "LA"   # Lao PDR        — final-round list
    MN = "MN"   # Mongolia       — final-round list
    RU = "RU"   # Russian Fed.   — final-round list
    TH = "TH"   # Thailand       — final-round list
    TL = "TL"   # Timor-Leste    — final-round list (carries the difficulty bonus)
    VN = "VN"   # Viet Nam       — NOT on the panel's list; see below
    KZ = "KZ"   # Kazakhstan     — NOT on the panel's list; see below


# The panel's published country list, verified 2026-08-27 against
# `Finalist Orientation/Finalist Orientation_Slide.pdf` ("Final Round Countries list — Select
# at least 3 from 8 countries above, in addition to 3 mandatory countries: Australia Malaysia
# Singapore") and `Meeting notes.docx` ("Teams choose at least 3 from 8 newly listed countries
# … Timor-Leste carries a small bonus if covered, due to its added difficulty").
FINAL_ROUND_LIST = ("CN", "IN", "ID", "LA", "MN", "RU", "TH", "TL")

# Mandatory in every round, and NOT part of the choice above.
ROUND1_ECONOMIES = ("SG", "AU", "MY")

# What the sealed live test on 15 October can actually name: "Draw from the listed economies
# (any pillar) — announced at the start of the hour", so the mandatory three are in scope too.
# Eleven, not nine.
LIVE_TEST_POOL = ROUND1_ECONOMIES + FINAL_ROUND_LIST

# Viet Nam and Kazakhstan appear on NO list the panel published, and have no sheet in either
# RDTII database. They were added on 2026-08-21 by a `LIVE_TEST_NINE` constant whose comment
# quoted "final-round instructions" that exist in no document in this repo — the orientation
# material is gitignored, so it was never opened, and the list was inferred instead. That cost
# both of them a portal lane, a language profile and an OCR entry, while Timor-Leste — which IS
# on the list, and carries a bonus — had none of the three.
#
# They stay resolvable rather than being deleted: the lanes work, someone may still want to run
# them, and a user typing "Vietnam" should get Viet Nam and not a stack trace. What they must
# never be again is ADVERTISED as economies the live test can name.
NOT_ON_PANEL_LIST = ("VN", "KZ")

# An economy being DECLARABLE and an economy being READY are different claims, and the README
# asks us to state which is which per economy. Appearing above buys resolvability, a language
# profile and an OCR path; it does not buy a verified portal or a measured run.
# `backend/providers/engine_profile.py` reports the difference rather than papering over it.

# Official UN member-state names required by the submission template
# (https://www.unescap.org/about/member-states). The CSV must use these, not codes.
# Spelling is load-bearing and the instructions call two of them out by name: "Viet Nam"
# (two words, no circumflex) and "Lao People's Democratic Republic", never "Laos".
ECONOMY_UN_NAME = {"SG": "Singapore", "AU": "Australia", "MY": "Malaysia",
                   "CN": "China", "IN": "India", "MN": "Mongolia",
                   "TH": "Thailand", "VN": "Viet Nam", "ID": "Indonesia",
                   "KZ": "Kazakhstan", "LA": "Lao People's Democratic Republic",
                   "RU": "Russian Federation", "TL": "Timor-Leste"}

# value the user may type → Economy. Includes codes, UN names and common variants.
# NOTE "in"/"cn"/"mn" are 2-letter keys matched EXACTLY; the substring fallback in
# resolve_economy() ignores aliases of 3 chars or fewer, so they cannot swallow a longer
# input ("india" must not resolve via the "in" key).
_ECONOMY_ALIASES = {
    "sg": Economy.SG, "singapore": Economy.SG, "sgp": Economy.SG,
    "au": Economy.AU, "australia": Economy.AU, "aus": Economy.AU, "commonwealth of australia": Economy.AU,
    "my": Economy.MY, "malaysia": Economy.MY, "mys": Economy.MY,
    "cn": Economy.CN, "china": Economy.CN, "chn": Economy.CN,
    "prc": Economy.CN, "people's republic of china": Economy.CN, "peoples republic of china": Economy.CN,
    "in": Economy.IN, "india": Economy.IN, "ind": Economy.IN, "bharat": Economy.IN,
    "republic of india": Economy.IN,
    "mn": Economy.MN, "mongolia": Economy.MN, "mng": Economy.MN,
    "th": Economy.TH, "thailand": Economy.TH, "tha": Economy.TH,
    "kingdom of thailand": Economy.TH, "siam": Economy.TH,
    "vn": Economy.VN, "viet nam": Economy.VN, "vietnam": Economy.VN, "vnm": Economy.VN,
    "socialist republic of viet nam": Economy.VN,
    "id": Economy.ID, "indonesia": Economy.ID, "idn": Economy.ID,
    "republic of indonesia": Economy.ID,
    "kz": Economy.KZ, "kazakhstan": Economy.KZ, "kaz": Economy.KZ,
    "republic of kazakhstan": Economy.KZ,
    # "Lao PDR" is how the panel writes it; the UN name is longer. Both must land here, and
    # so must "laos", which is what a user will actually type.
    "la": Economy.LA, "lao": Economy.LA, "laos": Economy.LA, "lao pdr": Economy.LA,
    "lao people's democratic republic": Economy.LA,
    "lao peoples democratic republic": Economy.LA, "lao pdr.": Economy.LA,
    "ru": Economy.RU, "russia": Economy.RU, "rus": Economy.RU,
    "russian federation": Economy.RU, "the russian federation": Economy.RU,
    # Timor-Leste answers to three names in practice: its own (Portuguese) form, the
    # Tetum/Indonesian "Timor Leste" without the hyphen, and the English "East Timor".
    "tl": Economy.TL, "timor-leste": Economy.TL, "timor leste": Economy.TL,
    "tls": Economy.TL, "east timor": Economy.TL, "timor": Economy.TL,
    "democratic republic of timor-leste": Economy.TL,
    "republica democratica de timor-leste": Economy.TL,
}

_SUPPORTED = ", ".join(ECONOMY_UN_NAME.values())


def resolve_economy(value: str) -> Economy:
    """Map free-text user input to an Economy, tolerating case, codes and MIS-SPELLINGS
    (rubric: 'handles inputs you did not anticipate — mis-spelt country'). 'Singapor',
    'austrlia', 'MALAYSIA ' all resolve. Raises ValueError only when nothing is close."""
    import difflib
    key = " ".join((value or "").strip().lower().split())
    if not key:
        raise ValueError(f"No economy given. Supported: {_SUPPORTED}.")
    if key in _ECONOMY_ALIASES:
        return _ECONOMY_ALIASES[key]
    # Containment BEFORE fuzzy. An exact contained name is far stronger evidence than an
    # edit-distance neighbour, and with the Round-2 economies added the reverse order started
    # resolving "Republic of Singapore" to INDIA: difflib scores it 0.70+ against
    # "republic of india" (the shared "republic of " prefix dominates) and returned before the
    # substring pass could see "singapore" sitting inside the input.
    for name in sorted(_ECONOMY_ALIASES, key=len, reverse=True):
        if len(name) > 3 and (name in key or key in name):
            return _ECONOMY_ALIASES[name]
    # Fuzzy last, and only on a CLOSE match. At the old 0.7 cutoff "indonesia" scores 0.71
    # against "india" and resolved silently to the wrong economy — bad on its own, and worse
    # because Indonesia is itself an ESCAP economy we may add. Real typos still clear 0.8
    # comfortably ("austrlia" 0.94, "Mongolla" 0.88, "malaysa" 0.93).
    near = difflib.get_close_matches(key, _ECONOMY_ALIASES.keys(), n=1, cutoff=0.8)
    if near:
        return _ECONOMY_ALIASES[near[0]]
    raise ValueError(f"Unknown economy '{value}'. Supported: {_SUPPORTED}.")


class DiscoveryTag(str, Enum):
    KNOWN = "KNOWN"   # in the provided sample/reference dataset
    NEW = "NEW"       # surfaced by the crawler, outside the sample set


class ReviewStatus(str, Enum):
    AUTO_ACCEPTED = "auto_accepted"     # confidence >= auto threshold
    PENDING_REVIEW = "pending_review"   # in the human band
    QUARANTINED = "quarantined"         # below review floor
    APPROVED = "approved"               # human approved
    REJECTED = "rejected"               # human rejected
    CORRECTED = "corrected"             # human edited the mapping


class DocFormat(str, Enum):
    HTML = "html"
    PDF_TEXT = "pdf_text"
    PDF_SCANNED = "pdf_scanned"
    TEXT = "text"


# ─────────────────────────── reference data ───────────────────────────
class Indicator(BaseModel):
    """An RDTII 2.1 indicator we try to find legal evidence for."""
    indicator_id: str                         # e.g. "P7-I1"
    pillar: int                               # 6 or 7
    title: str
    description: str
    legal_test: str                           # what makes a provision *legally* (not just semantically) relevant
    scope: str = "national"                   # national | sectoral — guards against scope confusion
    query_terms: list[str] = Field(default_factory=list)


# ─────────────────────────── zone 1: discovery ───────────────────────────
class SourceConfig(BaseModel):
    """A legal portal we crawl."""
    economy: Economy
    name: str
    base_url: str
    search_url_template: Optional[str] = None   # {query} placeholder
    notes: str = ""


class DiscoveredDoc(BaseModel):
    doc_id: str
    economy: Economy
    title: str
    source_url: str
    portal: str
    fmt: DocFormat
    relevance_score: float = 0.0
    discovery_tag: DiscoveryTag = DiscoveryTag.NEW
    amendment_date: Optional[str] = None        # ISO date if detectable
    law_number: Optional[str] = None            # official act/law number, e.g. "Act 709"
    # The statute's own name, when the portal states it separately from the document title.
    # Set it ONLY when the two genuinely differ: India Code publishes one record per SECTION,
    # so a document's title has to carry the section (otherwise live-mode dedup collapses every
    # section of an Act into one) while the Law Name column must read "The Digital Personal
    # Data Protection Act, 2023" and nothing else. Left None, extraction derives the name from
    # the title as before.
    law_name: Optional[str] = None
    local_path: Optional[str] = None            # cached file
    raw_text: Optional[str] = None              # filled by extraction


# ─────────────────────────── zone 2: extraction ───────────────────────────
class OCRMetrics(BaseModel):
    used: bool = False
    provider: str = "none"
    mean_confidence: Optional[float] = None     # 0..1
    pages: int = 0
    chars: int = 0
    low_conf_pages: list[int] = Field(default_factory=list)
    cer: Optional[float] = None                 # measured Character Error Rate vs ground-truth
                                                # sidecar (raster-OCR engines only); None if no
                                                # reference is available. Rubric bar: < 0.05.
    notes: Optional[str] = None                 # e.g. "js_app_shell" when an HTML page was an
                                                # unrendered SPA (no extractable law text)


class Provision(BaseModel):
    """A single extracted legal provision (article/section)."""
    provision_id: str
    doc_id: str
    economy: Economy
    law_name: str
    law_number: Optional[str] = None            # official act/law number
    article_section: str                        # e.g. "Section 26" / "Art. 13"
    verbatim_snippet: str                       # EXACT wording — never paraphrased
    source_url: str
    amendment_date: Optional[str] = None
    location_ref: Optional[str] = None          # "p. 14" (PDF) or "§ Section 26" (HTML)
    source_pdf_path: Optional[str] = None        # local retrieved file (JSON/audit only)
    char_span: Optional[tuple[int, int]] = None # offsets into raw_text for audit
    ocr: OCRMetrics = Field(default_factory=OCRMetrics)


# ─────────────────────────── zone 2: mapping ───────────────────────────
class ConfidenceBreakdown(BaseModel):
    retrieval_score: float = 0.0      # how well the provision was retrieved for the indicator
    legal_match: float = 0.0          # model's judgement the provision satisfies the legal test
    snippet_grounding: float = 0.0    # is the cited snippet actually present in source text
    scope_alignment: float = 0.0      # national vs sectoral alignment with indicator.scope
    final: float = 0.0
    explanation: str = ""


class EvidenceMapping(BaseModel):
    """The core auditable record: a provision mapped to an RDTII indicator."""
    mapping_id: str
    run_id: str
    economy: Economy
    pillar: int
    indicator_id: str
    law_name: str
    law_number: Optional[str] = None
    last_amended: Optional[str] = None          # "Month Year" when verified, else "Year" (judges' QnA)
    article_section: str
    location_ref: Optional[str] = None
    verbatim_snippet: str
    source_url: str
    mapping_rationale: str
    confidence_score: float
    discovery_tag: DiscoveryTag
    coverage: Optional[str] = None              # "Horizontal" | "Sectoral" (template field)
    notes: Optional[str] = None                 # OCR/scope/bilingual flags
    # The ORIGINAL language of the document, never the language we translated into. Left None
    # to mean "use the economy's authoritative statute language"; set explicitly only where a
    # document departs from it, which bilingual portals genuinely do — Malaysia's AGC serves
    # Malay and English editions of the same Act, and Kazakhstan serves Kazakh and Russian.
    language_of_source: Optional[str] = None
    review_status: ReviewStatus

    # ── Zone 3 (optional scoring layer) — RDTII Raw Score for THIS measure ──
    # raw_score ∈ {0, 0.5, 1}: compliance-cost / restrictiveness grade per the methodology
    # scoring criteria (backend/rdtii/scoring_rubric.py). None when scoring is disabled. For
    # 7.1/7.2 the polarity is INVERTED (a horizontal framework scores 0). `impact` is the
    # Database's "Impact or comments" column — the one-sentence justification for the score.
    raw_score: Optional[float] = None
    impact: Optional[str] = None

    # ── working translation (reviewer aid, never a citation) ──
    # Six of the nine live-test economies legislate in a script the reviewer cannot read, and
    # the two columns carrying the finding — Law Name and Verbatim Snippet — are the statute's
    # own words by definition. These hold a machine translation of each, so the result can be
    # CHECKED rather than trusted. They are separate fields on purpose: `verbatim_snippet` is
    # what the panel verifies the citation against, so a translation written into it would be
    # a false citation. `translation_target` records the language actually produced, because a
    # cell whose language is inferred from the economy is wrong the moment the target changes.
    law_name_translated: Optional[str] = None
    snippet_translated: Optional[str] = None
    translation_target: Optional[str] = None

    # technical / audit extras (JSON export, not CSV)
    provision_id: str
    source_pdf_path: Optional[str] = None         # local retrieved file
    raw_context: str = ""                         # retrieval window the LLM actually saw
    raw_context_before: str = ""                  # source text immediately before the snippet
    raw_context_after: str = ""                   # source text immediately after the snippet
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    ocr: OCRMetrics = Field(default_factory=OCRMetrics)
    model_version: str = ""
    retrieval_log: list[str] = Field(default_factory=list)
    scope_flag: Optional[str] = None              # e.g. "SECTORAL_NOT_NATIONAL"
    human_note: Optional[str] = None


# ─────────────────────────── run envelope ───────────────────────────
class OCRReport(BaseModel):
    """Per-document OCR/extraction quality — surfaced at run level so the scanned-PDF
    proof (provider, pages, measured CER vs reference) is visible even when none of the
    document's provisions end up in the mapped output. Persisted inside RunMeta."""
    doc_id: str
    title: str
    source_url: str
    fmt: str
    ocr_used: bool = False
    provider: str = "none"
    pages: int = 0
    mean_confidence: Optional[float] = None
    cer: Optional[float] = None              # measured CER vs ground-truth (raster OCR); else None
    cer_under_5pct: Optional[bool] = None    # rubric pass/fail when CER was measured


class RunMeta(BaseModel):
    run_id: str
    economy: Economy
    pillars: list[int]
    started_at: str
    finished_at: Optional[str] = None
    processing_time_seconds: float = 0.0
    docs_discovered: int = 0
    # How many bodies this pass pulled over the network. The live-test template requires a
    # second pass to report ZERO here, so it is measured rather than inferred from
    # docs_discovered — a cache hit is a discovery but not a fetch.
    docs_fetched: int = 0
    # The exact documents this pass worked on, so a second pass can be handed the same set
    # instead of crawling again and hoping the portal answers identically.
    documents: list[DiscoveredDoc] = Field(default_factory=list)
    provisions_extracted: int = 0
    mappings_produced: int = 0
    ocr_provider: str = "mock"
    llm_provider: str = "mock"
    model_version: str = ""
    ocr_reports: list[OCRReport] = Field(default_factory=list)   # per-doc OCR/CER proof
    notes: str = ""
    # Measured cost for this run, produced by backend/metering.py as the run spends —
    # per component and per engine. `total_is_complete` is False when any component has no
    # price on file, in which case the total is a floor rather than the answer.
    cost: dict = Field(default_factory=dict)


class RunResult(BaseModel):
    meta: RunMeta
    mappings: list[EvidenceMapping] = Field(default_factory=list)


# OFFICIAL submission columns — EXACT name + order of OUTPUT_TEMPLATE_FINAL_ROUND.xlsx
# ("Output Data" sheet). Instructions: "Do not rename columns. Column names and order
# must match this template exactly. The secretariat validates against them." Do NOT add,
# rename, or reorder. Extra fields (pillar, coverage, OCR/CER, etc.) live in the JSON.
#
# The final round changed exactly one thing, and the Instructions sheet says so in as many
# words: "The thirteen Round 1 columns are unchanged, in the same order. Your exporter should
# still work." — plus a fourteenth, Language of Source, which drives criterion C1c.
#
# There is a FIFTEENTH column in the workbook, "Pillar (auto — do not edit)". We do not write
# it and must not: rows 9 onward already carry a formula deriving it from the Indicator ID,
# and the Coverage Matrix sheet reads that formula's output. Writing a literal there would
# overwrite the formula and silently empty the coverage counts.
SUBMISSION_COLUMNS = [
    "Economy",
    "Law Name",
    "Law Number / Ref",
    "Last Amended",
    "Indicator ID",
    "Article / Section",
    "Discovery Tag",
    "Location Reference",
    "Verbatim Snippet",
    "Mapping Rationale",
    "Source URL",
    "Confidence",
    "Notes",
    "Language of Source",
]

#: Reviewer-facing translation columns, appended AFTER the mandatory ones. The judges' Q&A
#: permits extra columns in that position (it is the same allowance MASTER_EXTRA_COLUMNS uses
#: for RDTII_Raw_Score), so the first 14 columns still match the template exactly, by name and
#: by position. The headers say MACHINE TRANSLATION in full: a reviewer must never mistake one
#: of these cells for the statute's own words, which is what the Verbatim Snippet column is.
TRANSLATION_COLUMNS = [
    "Law Name (machine translation)",
    "Verbatim Snippet (machine translation)",
]

# Statuses that belong in a submission (exclude rejected/quarantined by default)
SUBMITTABLE_STATUSES = {"auto_accepted", "approved", "corrected", "pending_review"}
