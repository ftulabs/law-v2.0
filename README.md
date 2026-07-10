# VeriTrade — AI Tool for Digital Trade Regulatory Analysis

**Team FTU · UN ESCAP Global Hackathon (RDTII 2.1) · Round 1: Singapore, Australia, Malaysia**

Given an **economy** and a **regulatory pillar**, the tool autonomously:

1. **Discovers** relevant laws on official government portals — live, no seed URLs, no hardcoded law names
2. **Fetches & extracts** article-level text from HTML, text PDFs, and scanned/image PDFs (OCR, CER < 5%)
3. **Maps** each provision to an RDTII indicator with a verbatim snippet, citation, and confidence score
4. **Exports** the official 13-column submission CSV (+ JSON audit trail, + consolidated master sheet)

Pillars: **6** — Cross-border Data Policies (P6-I1…I4) · **7** — Domestic Data Protection (P7-I1…I5).

---

## Setup

```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0

# Python 3.10+
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Configure the LLM (needed for the scored live path; skip for the offline check):

```bash
cp .env.example .env
```
```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...                  # funded key — openrouter.ai/keys
OPENROUTER_MODEL=deepseek/deepseek-v4-flash   # default; ~$0.07 per full economy run
```

> 🔐 No key is committed to this repository. `.env` is gitignored; a deployed instance
> reads the key from the platform's Secrets. Without any key the pipeline still runs
> end-to-end using a deterministic offline mock grader.

---

## Run

### Live crawl — the scored path

```bash
python main.py --economy Singapore --pillar 6 --live --llm openrouter
python main.py --economy Malaysia  --pillar all --live --llm openrouter
# equivalent reviewer alias: python run.py --country SG --pillar 6 --live
```

### All three economies + consolidated master sheet (submission file)

```bash
python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7 --live --llm openrouter
```

Writes per-economy CSV/JSON plus **`outputs/VeriTrade_MASTER_<ts>.csv/.json`** — one sheet
combining every economy and pillar (the 13 mandatory columns, then custom columns
`Pillar`, `RDTII Raw Score`, `Coverage` appended at the end).

### Dashboard (GUI)

```bash
streamlit run frontend/app.py
```

Pick economy, pillar, LLM and OCR engine in the sidebar, press **Run pipeline**, and watch
the live log. Results render as a reviewable dossier with per-indicator scores.

### Offline sample — reproducible check, no network/key

```bash
python main.py --economy Singapore --pillar 6
```

Runs the identical extraction → mapping → export code on a small bundled corpus.

### Scanned-PDF OCR demo (CER measurement)

```bash
python main.py --economy Singapore --pillar 6 --ocr rapidocr --llm mock
```

`data/samples/SG/mas_notice_655.pdf` is a genuine image-only PDF; the run reports
`CER=1.11% PASS<5%` against a shipped ground-truth sidecar.

---

## Output

`outputs/<Economy>_P<pillar>_<timestamp>.csv` — the official 13-column template, exactly:

| # | Column | Notes |
|---|--------|-------|
| 1 | Economy | official UN name |
| 2 | Law Name | full statute name |
| 3 | Law Number / Ref | e.g. "Act 26 of 2012" |
| 4 | Last Amended | "Month Year" when verified, else year |
| 5 | Indicator ID | e.g. `P6-I1` |
| 6 | Article / Section | exact article, e.g. "Section 26" |
| 7 | Discovery Tag | `NEW` (found autonomously) / `KNOWN` (in sample kit) |
| 8 | Location Reference | PDF page / HTML anchor |
| 9 | Verbatim Snippet | exact text, never paraphrased |
| 10 | Mapping Rationale | why this provision satisfies the indicator |
| 11 | Source URL | direct link on the official portal |
| 12 | Confidence | 0.00–1.00 |
| 13 | Notes | scope flags, OCR provenance, bilingual sources |

Also produced per run:

- **`*.json`** — full audit trail (retrieval log, confidence breakdown, OCR metrics incl. CER, model version)
- **`*_scored.csv`** — optional Zone-3 RDTII raw scores (0 / 0.5 / 1) per measure
- **Indicators with no evidence get an explicit "No evidence" placeholder row** — never left blank
- Malaysian rows note the bilingual source and link the authoritative Malay text

---

## How It Works

```
(economy, pillar)
   │  ZONE 1 — Discovery: web search scoped to the official portal (SG), the portal's
   │           OData API (AU), or the portal's own acts catalogue (MY). No seed URLs.
   │  ZONE 1 — Fetch: Scrapling (real-browser TLS fingerprint, beats WAFs) → httpx
   │           fallback; polite per-host delay; content-addressed cache.
   │  ZONE 2 — Extraction: MarkItDown for text PDFs/HTML; RapidOCR/PaddleOCR for
   │           scanned PDFs with measured CER; splits into verbatim article/§ chunks.
   │  ZONE 2 — Mapping: BM25 + multilingual dense embeddings + cross-encoder retrieve
   │           candidates; the LLM grades each (provision, indicator) pair seeing all
   │           sibling indicators; 4-signal confidence score.
   │  Routing: ≥0.85 auto-accept · 0.60–0.85 review · <0.60 quarantine (excluded)
   ▼
CSV + JSON + SQLite audit store
```

Small corpora are graded exhaustively (every provision × every indicator), so retrieval
ranking is a signal, not a gate — this keeps non-English recall robust.

---

## Configuration

Everything is swappable via `.env` — no code changes:

| Variable | Default | Options |
|----------|---------|---------|
| `LLM_PROVIDER` | `openrouter` | `anthropic`, `openai`, `gemini`, `local` (Ollama), `mock` |
| `OPENROUTER_MODEL` | `deepseek/deepseek-v4-flash` | any paid OpenRouter model id |
| `OCR_PROVIDER` | `markitdown` | `rapidocr`, `paddle`, `tesseract`, `azure`, `mock` |
| `RETRIEVER` | `hybrid` | `auto`, `lightrag` |
| `SERPER_API_KEY` | — | optional; reliable Google results for SG discovery |
| `FETCH_TTL_HOURS` | `24` | reuse fetched bodies without re-downloading; `0` = always re-fetch |
| `RESULT_CACHE_ENABLED` | `true` | identical inputs return the stored result instantly |

### Caching & fresh runs

Three layers make repeat runs fast without changing results: fetched documents (24 h TTL),
provision embeddings (persistent, byte-identical), and full run results.
**The first run of any (economy, pillar) is always live.** To force a full live re-run —
e.g. when demonstrating autonomous discovery — use:

```bash
python main.py --economy Singapore --pillar 6 --live --fresh
```

or tick **"Fresh run"** in the dashboard, or delete `cache/_results/`.

---

## Cost

Measured with `deepseek/deepseek-v4-flash` at $0.09 / $0.18 per 1M prompt/completion
tokens (OpenRouter, verified 2026-07-09):

| Scope | LLM calls | Cost |
|-------|-----------|------|
| One grading call (provision × indicator) | 1 | ~$0.0002 |
| One document (~64 calls) | ~64 | ~$0.012 |
| **One economy, both pillars (P6+P7)** | ~360 | **~$0.07** |
| Round 1 — all 3 economies | ~1 100 | **~$0.21** |
| Offline mock mode | 0 | $0.00 |

OCR, retrieval and embeddings run locally at zero marginal cost. The result/fetch/embedding
caches mean repeat runs cost $0. Re-measure per document with:

```bash
python tools/cost_logger.py --pdf data/samples/AU/privacy_act.pdf --economy Australia --pillar 6
```

---

## Tests

```bash
pytest tests/
```

Covers: CSV template compliance, known indicator mappings (PDPA→P7-I1, Cybersecurity
Act→P7-I2, …), MarkItDown extraction, scanned-PDF OCR CER < 5%, retriever selection,
browser fetch, input tolerance.

---

## Known Limitations

1. Confidence scores are relative signals, not calibrated probabilities — rows routed to
   `pending_review` deserve human eyes before submission.
2. The offline mock grader is lexical; use a real LLM for submission-quality mapping.
3. Cross-encoder reranking is English-only; mitigated by exhaustive grading on small
   corpora and a multilingual embedding model (swap via `CROSS_ENCODER_MODEL` for finals).
4. Live crawling depends on portal availability; the bundled sample corpus is the fallback
   if a portal is down during evaluation.

---

## Team

**FTU (Foreign Trade University, Vietnam)** · contact: minhtc@ftu.edu.vn
License: Apache 2.0
