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
    SG = "SG"   # Singapore      — Round 1 (mandatory)
    AU = "AU"   # Australia      — Round 1 (mandatory)
    MY = "MY"   # Malaysia       — Round 1 (mandatory)
    CN = "CN"   # China          — Round 2
    IN = "IN"   # India          — Round 2
    MN = "MN"   # Mongolia       — Round 2


# Official UN member-state names required by the submission template
# (https://www.unescap.org/about/member-states). The CSV must use these, not codes.
ECONOMY_UN_NAME = {"SG": "Singapore", "AU": "Australia", "MY": "Malaysia",
                   "CN": "China", "IN": "India", "MN": "Mongolia"}

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
    review_status: ReviewStatus

    # ── Zone 3 (optional scoring layer) — RDTII Raw Score for THIS measure ──
    # raw_score ∈ {0, 0.5, 1}: compliance-cost / restrictiveness grade per the methodology
    # scoring criteria (backend/rdtii/scoring_rubric.py). None when scoring is disabled. For
    # 7.1/7.2 the polarity is INVERTED (a horizontal framework scores 0). `impact` is the
    # Database's "Impact or comments" column — the one-sentence justification for the score.
    raw_score: Optional[float] = None
    impact: Optional[str] = None

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
    provisions_extracted: int = 0
    mappings_produced: int = 0
    ocr_provider: str = "mock"
    llm_provider: str = "mock"
    model_version: str = ""
    ocr_reports: list[OCRReport] = Field(default_factory=list)   # per-doc OCR/CER proof
    notes: str = ""


class RunResult(BaseModel):
    meta: RunMeta
    mappings: list[EvidenceMapping] = Field(default_factory=list)


# OFFICIAL submission columns — EXACT name + order of OUTPUT_TEMPLATE_31MAY.xlsx
# ("Output Data" sheet). Instructions: "Do not rename columns. Column names and order
# must match this template exactly. Judges validate programmatically." Do NOT add,
# rename, or reorder. Extra fields (pillar, coverage, OCR/CER, etc.) live in the JSON.
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
]

# Statuses that belong in a submission (exclude rejected/quarantined by default)
SUBMITTABLE_STATUSES = {"auto_accepted", "approved", "corrected", "pending_review"}
