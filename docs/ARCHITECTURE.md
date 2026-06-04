# VeriTrade — Architecture

> Auditable legal evidence extraction for UNESCAP RDTII 2.1 (Pillars 6 & 7) across
> Singapore, Australia, Malaysia. Built audit-first: every output row traces back
> to verbatim source text, retrieval logs, OCR metrics, and reviewer decisions.

---

## 1. System architecture

Three zones over one audit store. Each stage is a pure-ish function persisted to
SQLite, so any export is reconstructable from the database.

```
                         ┌──────────────────────── ZONE 1 · DISCOVERY ────────────────────────┐
  official portals ─────▶│ crawler (samples | live httpx/Playwright)                           │
  (SSO, FRL, AGC MY)     │ indicator-specific query · relevance rank · KNOWN/NEW tagging       │
                         └──────────────────────────────┬─────────────────────────────────────┘
                                                        │ DiscoveredDoc[]
                         ┌──────────────────────── ZONE 2 · EXTRACTION & MAPPING ──────────────┐
                         │ text acquisition:  HTML strip │ PDF text layer │ scanned→OCR         │
                         │ OCR provider (pluggable): mock | tesseract | paddle | azure          │
                         │ provision extraction: article/section split, VERBATIM snippets       │
                         │ retrieval: BM25 (indicator query → candidate provisions)             │
                         │ mapping: LLM grades legal-vs-semantic + scope, grounded on snippet   │
                         │ confidence: 4-signal weighted score → route                          │
                         └──────────────────────────────┬─────────────────────────────────────┘
                                                        │ EvidenceMapping[]
        ┌────────── confidence router ──────────┐       │
        │ ≥0.85 auto · 0.60–0.84 review · <0.60 │◀──────┘
        │ quarantine  (scope flag caps at 0.55) │
        └───────────────┬───────────────────────┘
                        ▼
   HITL review (approve/reject/correct) ──▶ CSV (reviewers) · JSON (technical) · SQLite audit log
```

**Shared services**
- `config.py` — env-driven settings, safe defaults, no provider hardcoded.
- `storage/db.py` — SQLite audit store: runs, documents, provisions, mappings, review_log.
- `providers/` — interchangeable OCR + LLM behind small interfaces (factory pattern).

**Design principles**
1. *Grounding before generation.* The LLM only ever sees retrieved verbatim
   snippets and is forbidden from asserting law it wasn't given. Law text, article
   numbers, and URLs are **carried from extraction, never generated**.
2. *Every score is explainable.* Confidence is a transparent weighted blend stored
   on the mapping (`confidence_breakdown`).
3. *Scope safety.* A national-scope indicator can't be satisfied by a sectoral
   instrument — the mapper flags `SECTORAL_NOT_NATIONAL` and the score is capped.
4. *Offline-first demo.* `mock` providers make the whole pipeline reproducible with
   no keys/network; real providers activate when configured.

---

## 2. Folder structure

```
veritrade/
├── README.md                     quickstart + CLI cheat-sheet
├── requirements.txt              core deps + optional provider extras (commented)
├── .env.example                  every knob, all defaulted
├── backend/
│   ├── config.py                 Settings (pydantic-settings)
│   ├── schemas.py                pydantic models — single source of truth
│   ├── main.py                   FastAPI surface
│   ├── cli.py                    Typer CLI
│   ├── rdtii/indicators.py       RDTII 2.1 indicators (Pillar 6 & 7) + legal tests
│   ├── providers/
│   │   ├── ocr_base.py  ocr_{tesseract,paddle,azure}.py  ocr_factory.py (+ MockOCR)
│   │   └── llm_base.py  llm_{anthropic,openai}.py        llm_factory.py (+ MockLLM)
│   ├── pipeline/
│   │   ├── discovery.py          Zone 1 (samples + live skeleton)
│   │   ├── ocr.py                text acquisition + OCR routing
│   │   ├── extraction.py         provision splitting (verbatim)
│   │   ├── retrieval.py          BM25 indicator-grounded retrieval
│   │   ├── mapping.py            provision → indicator grading
│   │   ├── confidence.py         scoring + HITL routing
│   │   └── orchestrator.py       end-to-end run
│   ├── review/workflow.py        approve / reject / correct + audit log
│   ├── storage/db.py             SQLite audit store
│   └── export/{csv_export,json_export}.py
├── frontend/app.py               Streamlit reviewer dashboard
├── data/
│   ├── sources.yaml              live portal configs + selectors
│   └── samples/                  offline reference corpus + manifest.yaml
├── docs/{ARCHITECTURE,DEMO,PITCH}.md  +  examples/
└── outputs/                      run DB + CSV/JSON exports
```

---

## 3. Data schemas (pydantic — `backend/schemas.py`)

| Model | Role |
|---|---|
| `Indicator` | RDTII target: `indicator_id, pillar, title, legal_test, scope, query_terms` |
| `DiscoveredDoc` | Zone 1 output: `title, source_url, fmt, relevance_score, discovery_tag, amendment_date` |
| `Provision` | Extracted clause: `law_name, article_section, verbatim_snippet, source_url, char_span, ocr` |
| `OCRMetrics` | `used, provider, mean_confidence, pages, chars, low_conf_pages` |
| `ConfidenceBreakdown` | `retrieval_score, legal_match, snippet_grounding, scope_alignment, final, explanation` |
| `EvidenceMapping` | **The auditable record** (see CSV/JSON below) |
| `RunMeta` / `RunResult` | run envelope: timings, counts, provider versions |

---

## 4. CSV schema — OFFICIAL submission template (policy judge)

`outputs/veritrade_<run>.csv` matches the UNESCAP RDTII submission template **exactly**
(column names + order — judges validate programmatically). One row per
provision×indicator, **verbatim wording preserved**, `utf-8-sig` for Excel. By default
only submittable rows are written (rejected/quarantined excluded, so a sectoral mis-map
never enters a national-indicator submission); pass `submission_only=False` to dump all.

| # | Column (exact) | Req. | Source in pipeline |
|---|---|---|---|
| 1 | `Economy` | ✓ | official UN member-state name (SG→Singapore, …) |
| 2 | `Law Name` | ✓ | statute title + year |
| 3 | `Law Number / Ref` | opt | from manifest/discovery (e.g. `Act 709`) |
| 4 | `Last Amended` | ✓ | **year** of `amendment_date` |
| 5 | `Indicator ID` | ✓ | RDTII code in `P6-I1` form |
| 6 | `Article / Section` | ✓ | extracted clause label |
| 7 | `Discovery Tag` | ✓ | `KNOWN` / `NEW` |
| 8 | `Location Reference` | opt | `p. N` (PDF/OCR) or `#sec26` anchor (HTML) |
| 9 | `Verbatim Snippet` | ✓ | exact statutory wording (never paraphrased) |
| 10 | `Mapping Rationale` | opt | templated "This [§] [verb] [what]. Maps to [id] because …" (≤300 chars) |
| 11 | `Source URL` | ✓ | official portal URL |
| 12 | `Confidence` | opt | 2-dp 0.00–1.00 |
| 13 | `Notes` | opt | OCR/scope/bilingual flags |

> **Before submitting:** confirm each `Indicator ID` against the authoritative RDTII 2.1
> codebook (the bundled indicators are illustrative). NEW provisions score highest, so
> review the `NEW`-tagged rows carefully.

See [examples/example_SG.csv](examples/example_SG.csv). `review_status` and all technical
metadata live in the JSON (§5), not the submission CSV.

---

## 5. JSON schema (technical reviewers)

`outputs/veritrade_<run>.json` — adds everything the CSV omits:

```jsonc
{
  "run": { "run_id", "economy", "pillars", "processing_time_seconds",
           "docs_discovered", "provisions_extracted", "mappings_produced", ... },
  "provider_versions": { "ocr_provider", "llm_provider", "model_version" },
  "summary": { "total", "by_status": { ... } },
  "mappings": [{
     "...all CSV fields...",
     "confidence_breakdown": { "retrieval_score","legal_match","snippet_grounding",
                               "scope_alignment","final","explanation" },
     "scope_flag": "SECTORAL_NOT_NATIONAL | null",
     "raw_context": "the retrieval window the model actually saw",
     "ocr_metrics": { "used","provider","mean_confidence","pages","low_conf_pages" },
     "model_version": "...",
     "retrieval_log": ["indicator=... query=...", "bm25_raw=... normalised=..."],
     "human_note": "reviewer note | null"
  }]
}
```

See [examples/example_SG.json](examples/example_SG.json).

---

## 6. OCR pipeline (`pipeline/ocr.py` + `providers/ocr_*`)

```
DiscoveredDoc.fmt ──► html        → BeautifulSoup strip → text
                  ──► pdf_text    → pdfplumber/pypdf text layer
                  │                 └─ if layer < 200 chars → reclassify scanned
                  ──► pdf_scanned → OCRProvider.ocr_pdf() → text + per-page confidence
```

- **Interchangeable** via `OCR_PROVIDER` (`mock|tesseract|paddle|azure`); selected by
  `ocr_factory.get_ocr_provider()`. Heavy imports are deferred so unused providers
  never need to be installed.
- **Quality captured**: `mean_confidence`, per-page confidence, `low_conf_pages`
  flow into `OCRMetrics` and propagate to every mapping for audit.
- **Mock provider** reads a `*.ocr.txt` sidecar (sample "scanned" docs ship ground
  truth) and simulates content-derived page confidence — the scanned branch and
  confidence routing run with no binaries.

---

## 7. Retrieval pipeline (`pipeline/retrieval.py`)

- Builds a query per indicator from `title + query_terms`.
- Ranks candidate provisions with **BM25** (`rank_bm25`, transparent pure-Python
  fallback if absent). Scores normalised to 0–1; `retrieval_log` records the query
  and per-provision raw/normalised scores.
- The mapper only sees provisions surfaced here → mappings stay citation-bound.
- **Extensible**: drop a dense FAISS/Chroma stage behind `retrieve()` (hybrid
  BM25+vector with RRF fusion) without changing callers — see the v1 retrieval notes.

---

## 8. Mapping logic (`pipeline/mapping.py`)

For each (indicator, retrieved provision):

1. Build a structured prompt carrying the indicator's **legal test**, scope, query
   terms, and the **verbatim snippet** only.
2. The LLM returns `{relevant, legal_match, scope_alignment, scope_flag, rationale}`
   — judging *only the snippet*, distinguishing **legal** relevance (a binding rule
   of the right scope) from **semantic** relevance (same topic).
3. Sectoral language against a national indicator ⇒ `scope_flag=SECTORAL_NOT_NATIONAL`
   and lowered `scope_alignment`. *(Example: MAS Notice 655 must not map to "national
   cybersecurity framework" P7.5 — see the bundled sample.)*
4. Law name, article number, URL, OCR metrics come from extraction — **not** the LLM.

Swap `LLM_PROVIDER=anthropic|openai` for real reasoning; the deterministic `mock`
grader uses transparent lexical signals so the logic is reproducible in a demo.

---

## 9. Confidence scoring (`pipeline/confidence.py`)

```
final = 0.25·retrieval_score        how strongly retrieved for the indicator
      + 0.40·legal_match            model judgement vs the legal test
      + 0.20·snippet_grounding      is the cited snippet actually in the source text
      + 0.15·scope_alignment        national vs sectoral fit
   capped at 0.55 if scope_flag set (a sectoral mapping can never auto-accept)
```

`snippet_grounding` is the anti-hallucination check: exact substring → 1.0, else
token-overlap partial credit. Every component is stored in `confidence_breakdown`
with a human-readable `explanation`.

---

## 10. Human-in-the-loop (`review/workflow.py`)

| `final` | route | reviewer action |
|---|---|---|
| ≥ 0.85 | `auto_accepted` | spot-check |
| 0.60–0.84 | `pending_review` | **approve / reject / correct** |
| < 0.60 | `quarantined` | re-open if needed |

Thresholds configurable (`CONF_AUTO_ACCEPT`, `CONF_REVIEW_FLOOR`). Every action
writes an immutable `review_log` row with reviewer, note, timestamp, and
before/after JSON — the human decision trail is itself auditable. `correct()` can
edit indicator, pillar, article, snippet, rationale, or scope flag.

---

## 11. Extensibility / production path

- **New economy / indicator** → add rows to `rdtii/indicators.py` and
  `data/sources.yaml`; the whole pipeline picks them up.
- **Live crawling** → implement portal selectors in `discover_live()` or drop in
  Playwright/Scrapy behind the same `DiscoveredDoc` interface.
- **Dense retrieval** → add FAISS/Chroma + embeddings (see v1 note: generate
  article-level embeddings at ingest, fuse with BM25 via RRF).
- **Real OCR/LLM** → set provider env vars; uninstall-safe deferred imports.
