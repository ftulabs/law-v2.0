# VeriTrade — AI Tool for Digital Trade Regulatory Analysis

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **ftulabs** | Round: 1
Last updated: 2026-06-04

> **Round 1 requirement:** the **Quick Start** below lets a reviewer set up and run the
> tool in under 10 minutes. It runs fully offline by default (no API key needed).

---

## What This Tool Does

VeriTrade is an **auditable legal evidence extraction pipeline** (not a chatbot). It
automates the two RDTII tasks:

**Task 1 — Automated Evidence Discovery**
Given an economy and a pillar, it retrieves the relevant legislation (HTML, text PDF,
and scanned PDF), and extracts clean, structured, article-level text — no manual steps.
Document extraction defaults to **Microsoft MarkItDown**.

**Task 2 — Intelligent Mapping & Categorization**
Each provision is mapped to a specific **RDTII 2.1 indicator** with an exact
article-level citation, a **verbatim** snippet, a Discovery Tag (**NEW**/**KNOWN**), a
**confidence score**, and a mapping rationale. Closely-related indicators are
disambiguated by showing the model every sibling indicator in the pillar and asking for
the single best fit. Low-confidence and sector-scope mappings are routed to human review.

**Mandatory scope:** Pillar 6 (Cross-border Data Flows) and Pillar 7 (Domestic Data Protection)
**Economies covered:** Singapore, Australia, Malaysia

---

## Quick Start

⏱ **Required for Round 1.** Works offline with the bundled sample corpus — no key needed.

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
python main.py --economy Singapore --pillar 6
```
**Output:** `outputs/SG_P6_<timestamp>.csv` and `outputs/SG_P6_<timestamp>.json`

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
│     └─ ranks laws, tags KNOWN / NEW            │
│  2. Document Processor                          │
│     └─ MarkItDown extraction (HTML/PDF/scanned)│
│     └─ article/§ structural parsing (verbatim) │
└──────────────────────────────────────────────┘
        │  clean structured provisions
        ▼
┌──────────────────────────────────────────────┐
│  TASK 2 — Mapping & Categorization             │
│  3. Retrieval (BM25, FAISS-ready)              │
│  4. LLM Mapping (provider-agnostic)            │
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
| Discovery | `backend/pipeline/discovery.py` | Sample corpus + live-crawler skeleton; KNOWN/NEW tagging |
| OCR / Extraction | `backend/pipeline/ocr.py`, `backend/providers/ocr_*.py` | MarkItDown (default), Tesseract, PaddleOCR, Azure, mock |
| Provision parser | `backend/pipeline/extraction.py` | Splits text into article/§ chunks, verbatim |
| Retrieval | `backend/pipeline/retrieval.py` | BM25 indicator-grounded retrieval |
| Mapper | `backend/pipeline/mapping.py`, `backend/rdtii/indicators.py` | RDTII indicators + best-fit disambiguation prompt |
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
| **MarkItDown** (default) | `markitdown` | Microsoft; PDF/Office/HTML → Markdown; high-fidelity text |
| Tesseract | `tesseract` | Free, open-source; image OCR (needs Tesseract + poppler) |
| PaddleOCR | `paddleocr` → `paddle` | Good multilingual; self-hosted |
| Azure Document Intelligence | `azure` | Best on scanned/image PDFs; needs endpoint + key |
| Mock | `mock` | Offline sidecar; no binaries |

Change `OCR_PROVIDER` in `.env` or pick it in the dashboard — no code changes.
For image-only/scanned PDFs, use `azure` (or set MarkItDown's `docintel_endpoint`).

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

| Pillar 6 — Cross-border Data Flows | Pillar 7 — Domestic Data Protection |
| :---- | :---- |
| P6-I1 General prohibition / restriction | P7-I1 Legal basis for processing |
| P6-I2 Adequacy standard | P7-I2 Purpose limitation |
| P6-I3 Contractual safeguards | P7-I3 Data subject rights |
| P6-I4 Consent exception | P7-I4 Data breach notification |
| P6-I5 Other exceptions | P7-I5 Enforcement & penalties |

IDs/titles/questions follow the official RDTII 2.1 reference. The `legal_test`/
`query_terms` in `backend/rdtii/indicators.py` are our interpretation to drive mapping.

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
- **Live crawling** is a skeleton (`discover_live`); the primary path is the curated
  offline sample corpus. JS-rendered portals would need Playwright.
- **Image-only / scanned PDFs**: MarkItDown extracts text layers, not raster images.
  Use `OCR_PROVIDER=azure` (Document Intelligence) or `tesseract` for true OCR.
- **Mock grader** is lexical (offline) and can mislabel closely-related indicators — use
  a real LLM (OpenRouter/Claude) for production-grade mapping accuracy.
- **Indicator `legal_test`/`query_terms`** are our interpretation of the official RDTII
  reference; review mappings (especially `pending_review` rows) before submission.
- **Confidence** scores are relative, not calibrated probabilities; <0.85 → human review,
  <0.60 → quarantine.

---

## Running the Test Suite
```bash
pytest tests/
```

| Test file | What it tests |
| :---- | :---- |
| `tests/test_output.py` | CSV header == official template; submission excludes quarantined |
| `tests/test_mapper.py` | Known mappings (consent→P7-I1, breach→P7-I4); P6 needs transfer context; sectoral never auto-accepts |
| `tests/test_ocr.py` | MarkItDown is default + extracts the bundled PDF |

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

| Role | Name | Responsibility |
| :---- | :---- | :---- |
| Technical Lead | _[fill in]_ | AI architecture, OCR, pipeline |
| Substantive Lead | _[fill in]_ | Legal/policy analysis, output QA |

Contact: minhtc.ftu@gmail.com

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
