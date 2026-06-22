# VeriTrade — AI Tool for Digital Trade Regulatory Analysis

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **VeriTrade** (Foreign Trade University) | Round: 1
Last updated: 2026-06-11

> **Two ways to run, by design:**
> **① Live crawl (`--live`) — the scored path.** This is what the rubric grades:
> autonomous discovery + retrieval + OCR straight from the official portals, no seed URLs.
> **② Offline sample (default) — the safe fallback.** Deterministic, no key, no network —
> so a reviewer can reproduce a full run in under 10 minutes even if a portal is down.
> The two paths share the *same* extraction → mapping → confidence → export code; only the
> document source differs. **Demo and screen-recording should lead with `--live`.**

---

## What This Tool Does

VeriTrade is an **auditable legal evidence extraction pipeline** (not a chatbot). It
automates the two RDTII tasks:

**Task 1 — Automated Evidence Discovery**
Given an economy and a pillar, it **discovers** the relevant legislation on the official
portal itself (no seed URLs — `site:`-scoped web search whose queries are round-robined
across every indicator so no law type is starved), **fetches** it past bot-protection,
**OCRs** scanned/image pages (measuring Character Error Rate), and **extracts** clean,
article-level provisions with their **verbatim** text. Document extraction defaults to
**Microsoft MarkItDown**; the provision parser is **country-specific** — each economy
drafts statutes differently, so SG, AU and MY each have their own structural rules and
their own page-furniture/table-of-contents cleanup (see *Per-Country Extraction* below).

**Task 2 — Intelligent Mapping & Categorization**
Each provision is mapped to a specific **RDTII 2.1 indicator** with an exact
article-level citation, a **verbatim** snippet, a Discovery Tag (**NEW**/**KNOWN**), a
**confidence score**, and a mapping rationale. A hybrid retriever shortlists the
best-matching provisions per indicator (bounded, per-law-diverse — see *Zone 2
Retrieval*); the LLM then disambiguates closely-related indicators by seeing every sibling
indicator in the pillar and choosing the single best fit, grading candidates in parallel.
Low-confidence and sector-scope mappings are routed to human review.

**Mandatory scope:** Pillar 6 (Cross-border Data Flows) and Pillar 7 (Domestic Data Protection)
**Economies covered:** Singapore, Australia, Malaysia

---

## ▶ Live Crawl — the scored path

This is the run the judges grade: give it **only an economy and a pillar**; it discovers the
legislation on the official portal itself (no seed URLs), fetches it past bot-protection,
OCRs scanned pages, extracts provisions, and maps each to an RDTII 2.1 indicator.

```bash
# end-to-end, live, real LLM — nothing pre-downloaded
python main.py --economy Singapore --pillar 6 --live --llm openrouter
python main.py --economy Malaysia  --pillar all --live --llm openrouter --ocr rapidocr
```

- **Zone 1 fetch:** Scrapling (real-browser TLS impersonation) is the default fetcher, so
  gov portals that 403 a plain HTTP client still resolve; httpx is the fallback.
- **No seed list:** discovery is `site:`-scoped web search over the portal in
  `data/sources.yaml`, not a hardcoded URL per law. Queries come from country-agnostic
  keyword packs (`backend/rdtii/keywords.py`) describing each indicator's **law type** and
  **regulatory obligation** — never a specific law title — so the system finds the law
  objectively rather than being told where to look.
- **Breadth without starvation:** queries are **round-robined across indicators** (each
  indicator's Nth term before any indicator's N+1th) and results collected round-robin
  across queries, so a niche law type (e.g. P7-I5 government-access acts) is never crowded
  out by the abundant data-protection results. A **circuit breaker** stops hammering a
  search engine once it rate-limits (so a run never hangs); a free **`SERPER_API_KEY`**
  (serper.dev) makes discovery fully reliable.
- **Same code as the sample path** — only the document *source* changes, so a green sample
  run is an honest preview of the live run.

> A live run depends on the portal being reachable at demo time. If you need a guaranteed
> reproducible run (offline, no key, ~10 min) — e.g. for the Round-1 setup check — use the
> **sample Quick Start** below; it exercises the identical pipeline on a bundled corpus.

---

## Quick Start (offline sample — safe fallback)

⏱ **Reproducible setup check for Round 1.** Works offline with the bundled sample corpus —
no key, no network. For the *scored* demo use **`--live`** (above).

### 1. Clone the repository
```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0
```

### 2. Set up the environment
```bash
# Python 3.10+ required
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. (Optional) Configure providers
The tool runs **offline by default** (MarkItDown + a deterministic mock grader) with no
key. To use a real LLM, copy the env file and add a key:
```bash
cp .env.example .env
```
```env
LLM_PROVIDER=openrouter          # or: anthropic, openai, mock
OPENROUTER_API_KEY=sk-or-...     # get a free key at https://openrouter.ai/keys
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
OCR_PROVIDER=markitdown          # or: tesseract, paddle, azure, mock
```
> 🔐 **Never commit real keys.** `.env` is gitignored. For a deployed web app, put
> `OPENROUTER_API_KEY` in the platform's **Secrets** (see *Deploying* below) — not in code.

### 4. Run the tool
```bash
# canonical entry point (hackathon reviewer script)
python run.py --country SG --pillar 6                    # offline sample (this Quick Start)
python run.py --country SG --pillar 6 --live             # the scored path — crawl live

# also available (alias)
python main.py --economy Singapore --pillar 6 --live --llm openrouter
```
**Output:** `outputs/SG_P6_<timestamp>.csv`, `outputs/SG_P6_<timestamp>_scored.csv` and `outputs/SG_P6_<timestamp>.json`

### Demonstrate scanned/image-PDF OCR (Technical-Resilience rubric)
The bundled `data/samples/SG/mas_notice_655.pdf` is a **genuine image-only PDF** (no text
layer). Run it through real raster OCR and the pipeline measures the Character Error Rate
against the shipped ground-truth sidecar:
```bash
python main.py --economy Singapore --pillar 6 --ocr rapidocr --llm mock
# [ocr] MAS Notice 655 ... via rapidocr conf=0.99 pages=1 CER=1.11% PASS<5%
```
The measured CER is written to the JSON (`ocr_reports[].cer` and `ocr_quality.cer`), so a
technical reviewer can verify the < 5% bar without rerunning. Regenerate the scanned
sample from any text with `python tools/make_scanned_pdf.py <in.txt> <out.pdf>`.

### Or launch the reviewer dashboard
```bash
streamlit run frontend/app.py
```
Pick the economy, pillars, **OCR engine and LLM** right in the sidebar.

---

## Full Usage

```bash
python main.py \
  --economy "Malaysia" \
  --pillar all \           # 6, 7, or all
  --output-dir outputs/ \
  --format both \          # csv, json, or both
  --llm openrouter --ocr markitdown
```

### Run on multiple economies
```bash
python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7
```

### Run on a provided PDF (bypass crawler)
```bash
python main.py --economy Singapore --pillar 6 --pdf path/to/law.pdf
```

---

## Architecture Overview

```
Input: Economy + Pillar
        │
        ▼
┌──────────────────────────────────────────────┐
│  TASK 1 — Evidence Discovery                   │
│  1. Discovery (sample corpus | live crawler)   │
│     └─ round-robin web search, circuit breaker │
│     └─ resolve portal PDF, tag KNOWN / NEW     │
│  2. Document Processor                          │
│     └─ MarkItDown / OCR (HTML/PDF/scanned, CER)│
│     └─ PER-COUNTRY structural parsing (verbatim)│
│        strips page furniture + TOC; SG/AU/MY   │
└──────────────────────────────────────────────┘
        │  clean structured provisions
        ▼
┌──────────────────────────────────────────────┐
│  TASK 2 — Mapping & Categorization             │
│  3. Retrieval — hybrid (BM25 + dense + rerank) │
│     └─ bounded, per-law-diverse shortlist/ind. │
│  4. LLM Mapping (provider-agnostic, parallel)  │
│     └─ best-fit indicator vs all pillar siblings│
│     └─ verbatim snippet + article citation     │
│     └─ Discovery Tag + 4-signal confidence     │
│  5. Confidence routing → human-in-the-loop     │
└──────────────────────────────────────────────┘
        │
        ▼
Output: CSV (official template) + JSON (full trace) + SQLite audit store
```

### Key modules

| Module | File | Description |
| :---- | :---- | :---- |
| Discovery | `backend/pipeline/discovery.py`, `backend/pipeline/websearch.py` | `site:`-scoped web search round-robined across indicators with a circuit breaker; per-portal PDF resolution (AU OData API, SG SSO `ViewType=Pdf`, MY landing pages); same-law dedup → newest in-force version; KNOWN/NEW tagging |
| OCR engines | `backend/pipeline/ocr.py`, `backend/providers/ocr_*.py` | MarkItDown (default), RapidOCR/PaddleOCR (scanned), Tesseract, Azure, mock; auto-detects "secretly scanned" PDFs; measures CER |
| Provision parser | `backend/pipeline/extraction.py` | **Per-country** structural parsing into verbatim article/§ chunks; strips running headers/footers + "Arrangement of" TOC; SG em-dash, MY space-paren, AU font-marked + schedules/APP |
| Retrieval | `backend/pipeline/retrieval.py`, `backend/pipeline/retrieval_lightrag.py` | Hybrid BM25 + dense MiniLM + cross-encoder rerank; bounded per-law-diverse shortlist; LightRAG graph-RAG fallback at scale |
| Mapper | `backend/pipeline/mapping.py`, `backend/rdtii/indicators.py` | RDTII indicators + best-fit-vs-siblings prompt; parallel grading; grade-all for small corpora |
| Confidence / HITL | `backend/pipeline/confidence.py`, `backend/review/workflow.py` | Scoring + auto/review/quarantine routing |
| LLM clients | `backend/providers/llm_*.py` | OpenRouter / Anthropic / OpenAI / mock |
| Output writer | `backend/export/csv_export.py`, `json_export.py` | CSV (submission) + JSON (technical) |
| Orchestrator | `backend/pipeline/orchestrator.py` | End-to-end run + SQLite audit store |
| Interfaces | `main.py`, `backend/cli.py`, `backend/main.py`, `frontend/app.py` | CLI, API (FastAPI), dashboard (Streamlit) |

---

## Swapping the LLM

No vendor lock-in: change one config value. The LLM interface is abstracted in
`backend/providers/llm_base.py` (`LLMProvider.complete_json`).

### OpenRouter — free models (default)
```env
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
OPENROUTER_API_KEY=sk-or-...
```
Curated free models (auto-fails over if one is rate-limited):
`meta-llama/llama-3.3-70b-instruct:free`, `qwen/qwen3-next-80b-a3b-instruct:free`,
`openai/gpt-oss-120b:free`, `z-ai/glm-4.5-air:free`, `nvidia/nemotron-3-super-120b-a12b:free`.

### Anthropic Claude
```env
LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-opus-4-8
ANTHROPIC_API_KEY=sk-ant-...
```

### OpenAI
```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

### Offline (no key)
```env
LLM_PROVIDER=mock        # deterministic lexical grader for reproducible demos
```

### Adding a new provider
1. Create a class in `backend/providers/` implementing `LLMProvider.complete_json(system, user)`.
2. Register it in `backend/providers/llm_factory.py`.
3. Add it to `LLM_PROVIDERS` in `backend/providers/registry.py`.

---

## Swapping the OCR Engine

| Engine | `OCR_PROVIDER` | Notes |
| :---- | :---- | :---- |
| **MarkItDown** (default) | `markitdown` | Microsoft; PDF/Office/HTML → Markdown; high-fidelity **text-layer** extraction |
| **RapidOCR** (scanned) | `rapidocr` | Pip-only raster OCR (ONNX), no system binary; **CER ≈ 1%** on the bundled scan; fast + Jetson-friendly |
| **PaddleOCR** (PP-OCRv5) | `paddle` | Highest accuracy — **CER ≈ 0%** on the bundled scan; multilingual; heavier (~1 GB). On some Windows/CPU builds set `enable_mkldnn=False` (the provider already defaults to it) |
| Tesseract | `tesseract` | Free, open-source; image OCR (needs Tesseract + poppler) |
| Azure Document Intelligence | `azure` | Strongest on noisy real-world scans; needs endpoint + key |
| Mock | `mock` | Offline sidecar; no binaries |

Change `OCR_PROVIDER` in `.env` or pick it in the dashboard — no code changes.
For image-only/scanned PDFs use `rapidocr` (pip-only, default scanned engine) or `azure`
for the noisiest gazette scans. The pipeline auto-detects a "secretly scanned" text PDF
(empty text layer) and routes it to the OCR engine automatically.

---

## Per-Country Extraction (how Task 1 gets verbatim provisions right)

The hardest, most underrated part of RDTII is turning a raw legal PDF into clean,
**verbatim**, article-level provisions with the *correct* citation. There is no universal
format — **each economy drafts statutes differently** — so `backend/pipeline/extraction.py`
**dispatches by economy** (`_boundaries(text, economy)`) instead of forcing one regex on
all. A wrong split here corrupts the verbatim snippet the judges score, so this is handled
deliberately per country.

| Economy | How sections are written | How we detect them |
| :---- | :---- | :---- |
| **Singapore** (SSO) | "Heading\n**11.—(1)** …" — number + em-dash + subsection; "Section/Regulation N of the Act" is only ever a **cross-reference** | Split on the numbered margin form (`11.—(1)`, `26. Foo`) + Part/Schedule; the keyword forms are *not* boundaries (they're references) |
| **Malaysia** (LOM) | "Heading\n**20. (1)** …" — number + space + subsection | Same numbered profile, space-paren variant |
| **Australia** (legislation.gov.au) | Bold **font-marked** headings ("77 Requirement…"); Schedules renumber from 1; APPs in Schedule 1 | Font-mark detection (`\x1e`) + em-dash structural headings ("Schedule 1—…"); cross-ref markers ignored |

**Shared cleanup applied before splitting** (this is what stops "trích thừa" — junk text —
from polluting a snippet):

- **Page furniture removed.** SSO footers (`Informal Consolidation …`, `S 63/2021 14`), and
  AU footers/headers that vary per page (`356 Privacy Act 1988`, `Section 77A`, the
  right-aligned `… Division 3A` banner) are stripped — even when the bold footer carries a
  stray heading-mark — so a provision that spans pages stays continuous.
- **"Arrangement of Sections/Provisions" table of contents dropped**, so a TOC entry never
  becomes a bogus name-only provision.
- **Heading-extension.** A numbered section's snippet *starts at its margin heading* (e.g.
  "Legally enforceable obligations") and *ends where the next section's heading begins* — no
  previous-section tail, no next heading bleeding in.
- **AU schedules.** A font-marked heading inside Schedule 1 is relabelled `Section 8 → APP 8`
  and captured in full (8.1–8.x); sections in other schedules are scoped (`Schedule 2,
  Section 1`) so their restarted numbering doesn't collide with the main body; an
  "Australian Privacy Principle 8.3" cross-reference is never mistaken for the real APP 8.

> **To add a Finals economy:** add a profile (its section convention + page-furniture
> patterns) rather than widening a shared regex. `tests/test_extraction.py` pins each
> country's behaviour with real-world fixtures.

---

## Zone 2 Retrieval — hybrid or LightRAG graph-RAG

Each RDTII indicator is matched only against provisions a retriever surfaces (never the
whole corpus) — that is what keeps every mapping citation-bound. Two backends, selected by
`RETRIEVER` in `.env`:

| `RETRIEVER` | Engine | When |
| :---- | :---- | :---- |
| `hybrid` **(default)** | BM25 + dense MiniLM + **cross-encoder rerank**, RRF fusion (built-in) | Always available, fast, no LLM needed; the reliable default |
| `lightrag` | [HKUDS **LightRAG**](https://github.com/HKUDS/LightRAG) knowledge-graph retrieval | Live-crawl scale — dozens of laws / hundreds of provisions |
| `auto` | LightRAG when it's installed, an LLM key is set, and the corpus is large (`LIGHTRAG_MIN_PROVISIONS`, default 40); else hybrid | Opt-in best-of-both |

**The shortlist is bounded and per-law-diverse.** For each indicator the hybrid retriever
takes a global top-k **plus** a round-robin reserve of each discovered law's own best
provisions, capped at `RETRIEVE_MAX_TOP_K` (default 40) — so a short, on-point Act (e.g. My
Health Records s77) is still graded even when a 485-section Act would otherwise fill the
top-k, while the total per indicator stays bounded for speed/cost. For small corpora
(≤ `GRADE_ALL_MAX_PROVISIONS`, default 80) **every** provision is graded against every
indicator, so retrieval is a signal, not a gate. Candidates are graded **in parallel**
(`MAPPING_CONCURRENCY`).

**Citations are preserved either way.** LightRAG is used for *retrieval only* (each
provision is tagged so the exact verbatim snippet / article / URL is recovered from the
retrieved context) — it never synthesises an answer. Embeddings reuse the local
sentence-transformers model; the indexing LLM is the pipeline's own provider (no extra key).

> ⚠️ LightRAG's knowledge-graph build makes many entity-extraction LLM calls, so it needs
> an LLM with real budget (a funded OpenRouter/OpenAI key, or a **local Ollama** model via
> `LLM_PROVIDER=local`). On a spend-capped free key the KG build is starved — the pipeline
> detects the empty graph and **falls back to the hybrid retriever automatically**, so a run
> never breaks. Install with `pip install lightrag-hku nest_asyncio`.

---

## Supported Economies & Portals

| Economy | Official Portal | Language | Notes |
| :---- | :---- | :---- | :---- |
| Singapore | sso.agc.gov.sg | English | Machine-readable HTML/PDF |
| Australia | legislation.gov.au | English | Machine-readable PDF |
| Malaysia | lom.agc.gov.my | English / Malay | Mixed scanned and digital |

A curated **offline sample corpus** (`data/samples/`) ships for reproducible runs; live
portal selectors are configured in `data/sources.yaml` (`--live`).

---

## Output Format

Two files per run.

### CSV (`outputs/<Economy>_P<pillar>_<timestamp>.csv`)
Columns match the official RDTII submission template **exactly** (name + order — judges
validate programmatically). Rejected/quarantined rows are excluded by default.

| # | Column | Required | Description |
| :---- | :---- | :---- | :---- |
| 1 | Economy | Required | Official UN country name |
| 2 | Law Name | Required | Full official statute name and year |
| 3 | Law Number / Ref | Optional | Official act/law number (e.g. Act 709) |
| 4 | Last Amended | Required | Year of most recent amendment (blank if never) |
| 5 | Indicator ID | Required | RDTII code (e.g. P6-I1, P7-I3) |
| 6 | Article / Section | Required | Exact article and paragraph |
| 7 | Discovery Tag | Required | NEW = independent find; KNOWN = sample kit |
| 8 | Location Reference | Optional | PDF page (`p. 14`) or HTML anchor (`#sec26`) |
| 9 | Verbatim Snippet | Required | Exact quoted text — no paraphrasing |
| 10 | Mapping Rationale | Optional | ≤300 chars: why it maps to this indicator |
| 11 | Source URL | Required | Direct URL to law on official portal |
| 12 | Confidence | Optional | Model certainty (0.00–1.00) |
| 13 | Notes | Optional | OCR/scope/bilingual flags |

Example: [docs/examples/example_SG.csv](docs/examples/example_SG.csv).

### JSON (`outputs/<Economy>_P<pillar>_<timestamp>.json`)
Same fields plus extended metadata: `confidence_breakdown`, `ocr_quality` (provider,
mean_confidence, pages), `raw_context`, `source_pdf_path`, `retrieval_log`,
`model_version`, `processing_time_seconds`, `scope_flag`. See
[docs/examples/example_SG.json](docs/examples/example_SG.json).

---

## RDTII Indicators (Pillars 6 & 7)

| Pillar 6 — Cross-border Data Policies | Pillar 7 — Domestic Data Protection |
| :---- | :---- |
| P6-I1 Ban and local processing requirements | P7-I1 Comprehensive data-protection framework |
| P6-I2 Local storage requirements | P7-I2 Dedicated cybersecurity framework |
| P6-I3 Infrastructure requirements | P7-I3 Minimum data-retention requirements |
| P6-I4 Conditional flow regimes | P7-I4 DPO / DPIA requirements |
| | P7-I5 Government access to personal data |

These titles, and the `legal_test`/`query_terms` in `backend/rdtii/indicators.py`, follow the
**official "RDTII 2.1 Methodology"** sheet in the Round-1 Database (in repo root) and are
verified against its worked answer key (e.g. Singapore: 6.4 ← PDPA §26 conditional transfer;
7.2 ← Cybersecurity Act 2018; 7.5 ← Criminal Procedure Code §39-40). Pillar 6 has four
extractable indicators — 6.5 ("binding commitments") is a non-regulatory, third-party-sourced
indicator outside crawl scope.

> ⚠️ The `OUTPUT_TEMPLATE_31MAY.xlsx` "Indicator Reference" sheet lists *generic GDPR* names
> (P6-I1 "general prohibition", P7-I2 "purpose limitation"). That sheet conflicts with the
> scored methodology above — we map to the **Database/Methodology** definitions, which the
> answer key uses.

---

## Actual Cost Per Document

Measure with the included logger:
```bash
python tools/cost_logger.py --pdf data/samples/AU/privacy_act.pdf --economy Australia --pillar 6
```
Writes `logs/cost_report.json` (wall-clock, provider, token/cost where available).

### Measured results (default offline stack)

| Component | Engine used | Measured cost |
| :---- | :---- | :---- |
| OCR / extraction | MarkItDown | $0.000 |
| LLM mapping | OpenRouter **free** model / mock | $0.000 |
| Retrieval | BM25 (local) | $0.000 |
| **Total (default stack)** | | **$0.00 per document** |

**Measured on:** 2026-06-04 · **Benchmark:** Privacy Act 1988 (Australia) sample PDF ·
**Wall-clock:** ~1.3 s/document (mock LLM). OpenRouter free models add network latency
but **$0** marginal cost. For paid LLMs (Claude/GPT-4o), re-run the logger to record
token costs.

---

## Known Limitations

Honest by design:
- **Live crawling** (`--live`) is functional: web-search discovery (`site:`-scoped,
  multi-engine with on-disk cache), the Australia OData JSON API, SG SSO PDF resolution,
  and a content-addressed caching fetcher. **Fetching is done by
  [Scrapling](https://github.com/D4Vinci/Scrapling) by default** (`CRAWL_FETCHER=scrapling`):
  its curl_cffi engine impersonates a real browser's TLS fingerprint, so WAF/403 blocks
  that defeat a plain HTTP client don't stop it — and with `CRAWL_BROWSER=true` it escalates
  to a stealth Camoufox browser that executes JS and clears challenges (run `scrapling
  install` first). Scrapling is also the primary web-search engine. httpx remains as an
  automatic fallback (`CRAWL_FETCHER=httpx` flips the order); both share the same cache, so
  switching engines never re-downloads a body.
- **Image-only / scanned PDFs**: handled by real raster OCR (`--ocr rapidocr`, pip-only,
  no system binary) — measured **CER ≈ 1%** on the bundled scanned sample (see below).
  For noisy real-world gazette scans, `--ocr azure` (Document Intelligence) is strongest.
  MarkItDown (default) is for text-layer PDFs/HTML/Office, not raster images.
- **Mock grader** is lexical (offline) and can mislabel closely-related indicators — use
  a real LLM (OpenRouter/Claude) for production-grade mapping accuracy.
- **Indicator `legal_test`/`query_terms`** are our interpretation of the official RDTII
  reference; review mappings (especially `pending_review` rows) before submission.
- **Confidence** scores are relative, not calibrated probabilities; <0.85 → human review,
  <0.60 → quarantine.

---

## Pinned Versions

All runtime dependencies in `requirements.txt` are pinned to exact versions (`==`).
Jetson TX2 constraints: `torch==2.2.2`, `transformers<5`, `numpy<2`.
Open-source / no-key fallback: set `LLM_PROVIDER=mock` and `OCR_PROVIDER=mock` — no packages
beyond the core `pip install -r requirements.txt` required.

---

## Running the Test Suite
```bash
pytest tests/
```

| Test file | What it tests |
| :---- | :---- |
| `tests/test_output.py` | CSV header == official template; submission excludes quarantined |
| `tests/test_extraction.py` | **Per-country** parsing: SG SSO chrome + cross-ref + heading-extension; AU schedules/APP relabel + page-furniture; font-marked sections |
| `tests/test_discovery.py` | Same-law dedup → newest version; round-robin keeps niche law types; circuit breaker stops a blocked engine |
| `tests/test_mapper.py` | Known mappings (consent→P7-I1, breach→P7-I4); P6 needs transfer context; sectoral never auto-accepts |
| `tests/test_mapping_perf.py` | Per-indicator shortlist is hard-capped (no fraction-of-corpus blow-up); short on-point law not crowded out |
| `tests/test_ocr.py`, `tests/test_scanned_ocr.py` | MarkItDown default extracts the bundled PDF; bundled scan is image-only, RapidOCR reads it at CER < 5% (measured + reported) |
| `tests/test_input.py` | Economy input tolerates codes, UN names and mis-spellings; rejects garbage clearly |
| `tests/test_zone2_retriever.py` | Retriever selection (hybrid/lightrag/auto); mapper falls back to hybrid if LightRAG yields nothing |
| `tests/test_scrapling_fetch.py`, `tests/test_js_shell.py` | Scrapling escalation stores bodies + respects the byte cap; AU JS-shell detected and suppressed (no nav-chrome provisions) |

---

## Reproducing the Sample Kit Results
```bash
python evaluate.py --economy Singapore
```
Reports KNOWN provisions matched and NEW provisions discovered, plus routing and
indicator coverage.

---

## Deploying (so judges use the key without it being in the repo)

Deploy the dashboard to **Streamlit Community Cloud** or **Hugging Face Spaces** and set
the key in the platform's **Secrets** (never in code):
```toml
# Secrets (Streamlit Cloud → App → Settings → Secrets)
OPENROUTER_API_KEY = "sk-or-..."
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
```
The dashboard reads `st.secrets` first, then env/`.env`. Locally, copy
`.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` (gitignored).

---

## Team

**Team VeriTrade** — Foreign Trade University (FTU).

| Role | Name | Responsibility |
| :---- | :---- | :---- |
| Technical Lead | Minh Tran | AI architecture, OCR, pipeline |
| Substantive Lead | Vo Minh Ngoc | Legal/policy analysis, output QA |

Contact: minhtc@ftu.edu.vn

---

## License

Released under the **Apache License 2.0** per the hackathon requirements. See [LICENSE](LICENSE).

---

## Key Dates

| Date | Milestone |
| :---- | :---- |
| 20 July 2026 | **Round 1 submission deadline** |
| 31 July 2026 | 20 teams shortlisted |
| 3 August 2026 | Live online pitching (20 teams) |
| 5 August 2026 | 5 finalists announced |
| October 2026 | Grand Finale — Bangkok |

---

## Acknowledgements

Built for the UN Global Hackathon on AI for Digital Trade Regulatory Analysis, organised
by UNESCAP and KMITL.
