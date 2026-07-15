# VeriTrade — AI Tool for Digital Trade Regulatory Analysis

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **FTU (Foreign Trade University, Vietnam)** | Round: **1**
Last updated: 2026-07-12

---

## What This Tool Does

Automates the two RDTII tasks, end-to-end, with no manual steps.

**Task 1 — Automated Evidence Discovery.** Given an economy and a pillar, VeriTrade crawls
official government legal portals live (no seed URLs, no hardcoded law names), fetches the
relevant legislation — including scanned/image PDFs — and extracts clean, article-level text.

**Task 2 — Intelligent Mapping & Categorization.** Each provision is mapped to a specific
RDTII indicator with an exact article citation, a verbatim snippet, a confidence score, and a
Discovery Tag (NEW = found independently, KNOWN = matches a sample-kit example).

**Mandatory scope:** Pillar 6 (Cross-border Data Policies) and Pillar 7 (Domestic Data Protection)
**Economies covered:** Singapore, Australia, Malaysia

---

## 🌐 Hosted Instance (for judges — no setup, no API keys)

**https://veritrade.ftu.fyi** — the full dashboard, live, with our LLM/OCR keys pre-configured
in platform secrets (never in this repository). Pick a country and topic, press *Run analysis*,
and download the submission CSV. This instance runs the exact code in this repository and will
remain live through the end of the evaluation period. If it is briefly unreachable, retry after
a minute (the tunnel self-heals) or fall back to the local Quick Start below.

---

## Quick Start

⏱ A reviewer with basic Python should run this in under 10 minutes with the steps below.

### 1. Clone the repository
```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0
```

### 2. Set up the environment
```bash
# Python 3.10+ required
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API keys
```bash
cp .env.example .env
```
Open `.env` and set:
```env
LLM_PROVIDER=openrouter                        # or: anthropic, openai, gemini, local (Ollama), mock
OPENROUTER_API_KEY=sk-or-...                    # funded key — openrouter.ai/keys
OPENROUTER_MODEL=deepseek/deepseek-v4-flash     # see "Swapping the LLM"
OCR_PROVIDER=markitdown                         # or: rapidocr, paddle, tesseract, azure, mock
SERPER_API_KEY=...                              # OPTIONAL — reliable Google results (free without it)
```
> 🔐 No key is committed. `.env` is gitignored; a deployed instance reads keys from platform
> Secrets. With **no key at all**, the tool still runs end-to-end using an offline mock grader.

### 4. Run the tool
```bash
python main.py --economy Singapore --pillar 6 --live
```
**Output:** `outputs/SG_P6_<timestamp>.csv` and `outputs/SG_P6_<timestamp>.json`

---

## Full Usage

```bash
python main.py \
  --economy Malaysia \
  --pillar all \          # 6, 7, or all
  --live \                # crawl live portals (omit for the offline sample corpus)
  --llm openrouter \
  --format both           # csv, json, or both
```

### Run all three economies → one consolidated submission sheet
```bash
python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7 --live --llm openrouter
```
Writes per-economy files plus **`outputs/VeriTrade_MASTER_<ts>.csv/.json`** — the single sheet
combining every economy and pillar. Custom columns (confirmed acceptable by the judges' Q&A)
come **after** the 13 mandatory columns:
- `Pillar` — 6 or 7, for filtering the consolidated sheet
- `RDTII_Raw_Score` — the optional Zone-3 RDTII Raw Score (0 / 0.5 / 1) for the measure
- `Coverage` — the measure's coverage label (e.g. Horizontal / sector name)

`Last Amended` carries the month and year from the portal's own revision history; a law the
portal positively shows as never amended reads **"Original"** (per the judges' Q&A). Indicators
with no matching provision get a "No provision found" row with Verbatim Snippet
"No evidence found" and `N/A` in Confidence and Discovery Tag.

### Other modes
```bash
python main.py --economy Singapore --pillar 6 --pdf path/to/law.pdf   # process one local PDF
python main.py --economy Singapore --pillar 6                         # offline sample (no key/network)
python main.py --economy Singapore --pillar 6 --live --fresh          # ignore caches, re-crawl live
streamlit run frontend/app.py                                         # web dashboard (GUI)
```

---

## Architecture Overview

```
Input: Economy + Pillar
  │
  ▼  TASK 1 — Evidence Discovery
  │   1. Discovery — web search scoped to the official portal (SG), the portal's OData API
  │      (AU), or the portal's own acts catalogue (MY). Live, no seed URLs.
  │   2. Fetch + Process — Scrapling (real-browser TLS, beats WAFs) → httpx fallback;
  │      MarkItDown for text PDFs/HTML, RapidOCR/PaddleOCR for scanned PDFs (measured CER);
  │      structural parsing into verbatim article/§ chunks.
  ▼  TASK 2 — Mapping & Categorization
  │   3. Retrieval (RAG) — BM25 + multilingual dense embeddings + cross-encoder rerank.
  │   4. LLM Mapping — grades each (provision, indicator) pair against all sibling indicators;
  │      emits verbatim snippet, citation, Discovery Tag, 4-signal confidence.
  ▼
Output: CSV / JSON — 13 fields per provision (+ audit trail, + master sheet)
```
Small corpora are graded exhaustively (every provision × every indicator), so retrieval is a
signal, not a gate — keeping non-English recall robust.

### Key modules

| Module | File | Description |
| :---- | :---- | :---- |
| Discovery / Crawler | `backend/pipeline/discovery.py`, `fetch.py`, `scrapling_fetch.py` | Live portal discovery, bot-resistant fetch, caching |
| OCR / Extraction | `backend/pipeline/ocr.py`, `extraction.py`, `providers/ocr_*.py` | Scanned-PDF OCR + CER, article-level parsing |
| Retrieval | `backend/pipeline/retrieval.py` | BM25 + dense embeddings + cross-encoder rerank |
| Mapper | `backend/pipeline/mapping.py` | LLM provision→indicator mapping + confidence |
| LLM abstraction | `backend/providers/llm_*.py`, `llm_factory.py` | Vendor-agnostic provider interface |
| Output Writer | `backend/export/csv_export.py`, `json_export.py` | 13-column CSV, JSON, master sheet |
| Orchestrator | `backend/pipeline/orchestrator.py` | End-to-end run + SQLite audit trail |

---

## Swapping the LLM

Required by the rubric (**No Vendor Lock-in**). Change one config value — no code changes.
The interface is abstracted in `backend/providers/llm_factory.py`.

```env
LLM_PROVIDER=openrouter    # OpenRouter (default) — any model id in OPENROUTER_MODEL
LLM_PROVIDER=anthropic     # ANTHROPIC_API_KEY + ANTHROPIC_MODEL=claude-...
LLM_PROVIDER=openai        # OPENAI_API_KEY + OPENAI_MODEL=gpt-4o
LLM_PROVIDER=gemini        # GEMINI_API_KEY
LLM_PROVIDER=local         # self-hosted Ollama/vLLM — LOCAL_LLM_BASE_URL, no key
LLM_PROVIDER=mock          # deterministic offline grader, $0, no key
```
**Self-hosted example (zero cost):** `ollama pull llama3 && ollama serve`, then set
`LLM_PROVIDER=local`, `LOCAL_LLM_MODEL=llama3`. To add a provider, implement one class in
`backend/providers/` and register it in `llm_factory.py`.

---

## Swapping the OCR Engine

Change `OCR_PROVIDER` in `.env` — no code changes.

| Engine | Config value | Notes |
| :---- | :---- | :---- |
| MarkItDown | `markitdown` | Default; text-layer PDFs / HTML / Office, $0 |
| RapidOCR | `rapidocr` | Scanned PDFs, ONNX, no system binary, CER ≈ 1% |
| PaddleOCR | `paddle` | Scanned, strong multilingual (PP-OCRv5) |
| Tesseract | `tesseract` | Free, open-source image OCR |
| Azure Document Intelligence | `azure` | Best on noisy gazette scans; needs endpoint + key |
| Mock | `mock` | Offline sidecar, $0 |

---

## Supported Economies & Portals

| Economy | Official Portal(s) | Language | Notes |
| :---- | :---- | :---- | :---- |
| Singapore | sso.agc.gov.sg | English | Web-search discovery; PDF full text |
| Australia | legislation.gov.au | English | OData API (title lane) + full-text content lane, both verified in-force |
| Malaysia | lom.agc.gov.my, pdp.gov.my | English / Malay | Portal's own acts catalogue + registered sectoral Codes of Practice; mixed scanned/digital |

Adding an economy = add its portal domain to `websearch.OFFICIAL_PORTAL`; discovery generalises.

---

## Output Format

### CSV (`outputs/<economy>_P<pillar>_<timestamp>.csv`)
Exact 13-column order — judges validate programmatically; do not rename or reorder.

| # | Column | Required | Description |
| :---- | :---- | :---- | :---- |
| 1 | Economy | Required | Official UN country name |
| 2 | Law Name | Required | Full official statute name and year |
| 3 | Law Number / Ref | Required | Official act/law number (e.g. Act 709) |
| 4 | Last Amended | Required | "Month Year" when verified, else year |
| 5 | Indicator ID | Required | RDTII code (e.g. P6-I1, P7-I3) |
| 6 | Article / Section | Required | Exact article/section (e.g. Section 26) |
| 7 | Discovery Tag | Required | NEW = independent find; KNOWN = sample kit |
| 8 | Location Reference | Optional | PDF page number / HTML anchor |
| 9 | Verbatim Snippet | Required | Exact quoted text — no paraphrasing |
| 10 | Mapping Rationale | Optional | ≤300 chars: why this provision maps here |
| 11 | Source URL | Required | Direct link on the official portal |
| 12 | Confidence | Optional | Model certainty 0.00–1.00 |
| 13 | Notes | Optional | Scope flags, OCR provenance, bilingual sources |

Indicators with no evidence get an explicit **"No evidence found"** row (never left blank).

### JSON (`outputs/<economy>_P<pillar>_<timestamp>.json`)
Same fields plus: `ocr_quality.cer`, `processing_time_seconds`, `raw_context_before/after`,
`pdf_is_scanned`, `retrieval_log`, `confidence` breakdown, `model_version`.

---

## Actual Cost Per Document

Measured, not estimated. Two paid services are used; everything else runs locally at $0.

**Measured 2026-07-12** · benchmark: one ~50-page Act (~64 grading calls) · deepseek-v4-flash
at $0.09/$0.18 per 1M input/output tokens (OpenRouter, verified) · Serper at $1.00/1k queries.

| Component | Engine | Cost |
| :---- | :---- | :---- |
| OCR | MarkItDown / RapidOCR (local) | $0.000 |
| Embedding + Retrieval | MiniLM + BM25 (local) | $0.000 |
| LLM mapping | deepseek-v4-flash | **~$0.012 / document** (~$0.0002 × 64 calls) |
| Discovery search | Serper (optional) | **per run, not per doc** — see below |
| **Total (current stack)** | | **~$0.012 / document** + discovery |
| **Total (open-weight swap)** | Ollama Llama 3 + Tesseract + DuckDuckGo | **$0.00 / document** |

### Discovery (Serper) cost — measured per run

Serper is **optional**: without a key, discovery falls back to DuckDuckGo/Mojeek (free). With a
key it costs **1 credit per query** (2,500 credits free, then $1.00/1k → $0.30/1k at volume):

| Run | Serper queries | Cost @ $1/1k |
| :---- | :---- | :---- |
| Singapore, both pillars | 90 | ~$0.09 |
| Australia, both pillars | 90 | ~$0.09 |
| Malaysia, both pillars | 5 | ~$0.005 |
| **Full Round 1 (3 economies)** | **185** | **~$0.19** (within the 2,500 free credits → **$0**) |

### Full Round-1 submission — total measured cost

| | LLM | Serper | Total |
| :---- | :---- | :---- | :---- |
| Current stack | ~$0.21 | ~$0.19 (free tier: $0) | **~$0.40** (or ~$0.21 within free tier) |
| Open-weight swap | $0.00 | $0.00 | **$0.00** |

Caches (result / fetch / embedding) make repeat runs cost **$0**. Re-measure with:
```bash
python tools/cost_logger.py --pdf data/samples/AU/privacy_act.pdf --economy Australia --pillar 6
```

---

## Known Limitations

Honest transparency for judges:

- **Confidence is a relative signal, not a calibrated probability.** Rows routed to
  `pending_review` deserve human eyes before submission.
- **Confidence ≠ RDTII Raw Score.** Confidence asks "trust this citation?"; the optional
  Zone-3 Raw Score (0/0.5/1, `_scored.csv`) asks "how restrictive is this law?" — independent.
- **Offline mock grader is lexical** — use a real LLM for submission-quality mapping.
- **Cross-encoder rerank is English-only** — mitigated by exhaustive grading on small corpora
  and a multilingual embedding model (`CROSS_ENCODER_MODEL` swappable for finals).
- **Live crawling depends on portal availability** — the bundled sample corpus is the fallback.

---

## Running the Test Suite

```bash
pytest tests/
```

| Test file | What it tests |
| :---- | :---- |
| `tests/test_discovery.py` | Live discovery + in-force filtering |
| `tests/test_ocr.py`, `test_scanned_ocr.py` | OCR extraction + CER < 5% on a real scanned PDF |
| `tests/test_mapper.py` | Indicator mapping against known examples |
| `tests/test_output.py` | 13-column CSV schema validation |
| `tests/test_zone2_retriever.py` | Retriever selection (hybrid / LightRAG) |

---

## Reproducing the Sample Kit Results

```bash
python evaluate.py --economy Singapore
```
Reports KNOWN (sample-kit) vs NEW (independently discovered) provisions and coverage by indicator.

---

## Team

| Role | Responsibility |
| :---- | :---- |
| Technical Lead | AI architecture, OCR, discovery/RAG pipeline |
| Substantive Lead | Legal/policy analysis, RDTII mapping, output QA |

Foreign Trade University (FTU), Vietnam · contact: minhtc@ftu.edu.vn

---

## License

Released under the **Apache License 2.0** per the hackathon submission requirements.
See [LICENSE](LICENSE) for the full text.
