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
    SG = "SG"   # Singapore
    AU = "AU"   # Australia
    MY = "MY"   # Malaysia


# Official UN member-state names required by the submission template
# (https://www.unescap.org/about/member-states). The CSV must use these, not codes.
ECONOMY_UN_NAME = {"SG": "Singapore", "AU": "Australia", "MY": "Malaysia"}


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
    last_amended: Optional[str] = None          # YEAR only, per template
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
