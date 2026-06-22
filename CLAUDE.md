# VeriTrade — CLAUDE.md (Hackathon Context & Technical Guide)

**Project:** VeriTrade (Team FTU)  
**Hackathon:** UN ESCAP Global Hackathon on AI for Digital Trade Regulatory Analysis (RDTII 2.1)  
**Deadline:** 20 July 2026 (Round 1)  
**Contact:** minhtc@ftu.edu.vn

---

## 1. HACKATHON MISSION & SCORING CRITERIA

### The Core Challenge
Automate the manual legal-data-collection workflow: **given an economy + regulatory topic → autonomously find and extract ALL relevant legal text** without anyone telling the system where to look.

**Scoring pillar:** The judges test the app by giving it:
- An economy (SG/AU/MY mandatory for Round 1; later: Thailand/China/India/Indonesia/Russia/Lao/Mongolia/Timor-Leste)
- A regulatory pillar (6 = Cross-border Data Policies; 7 = Domestic Data Protection)

The app must, with zero seed URLs:
1. **Discover** relevant laws on official government portals (live, real-time, not a baked corpus)
2. **Extract** clean, article-level text from HTML, text PDFs, and scanned/image PDFs
3. **Map** each provision to a specific RDTII indicator with a verbatim snippet and citation
4. **Output** a CSV matching the official submission template exactly

Both **Zone 1 (discovery/fetching)** and **Zone 2 (OCR/extraction)** are mandatory every submission.  
Both **Pillar 6** and **Pillar 7** are mandatory.  
Zone 3 (scoring/quality gates) is optional — and now IMPLEMENTED (Raw Score 0/0.5/1 + scored CSV; see §4 Known Gaps).

**Do NOT:**
- Hardcode law names or seed URLs as the "answer" to (economy, pillar)
- Submit a baked corpus or static seed list
- Miss scanned PDFs (CER must be <5%)

### Key Resources
- **Official database:** `ESCAP-RDTII-2.1_ Round 1 Database.xlsx` (repo root) — source of truth for indicator definitions, verified answer key by economy
- **Output template:** `OUTPUT_TEMPLATE_31MAY.xlsx` (repo root) — defines the 13-column CSV format (Economy, Law Name, Law Number/Ref, Last Amended, Indicator ID, Article/Section, Discovery Tag, Location Reference, Verbatim Snippet, Mapping Rationale, Source URL, Confidence, Notes)
- **Sample portals CSV:** a judges' reference document listing the official portals for each economy — judges use this to verify your discovery, not as a seed corpus for you to ship

---

## 2. RDTII 2.1 INDICATORS — OFFICIAL DEFINITIONS

### Pillar 6: Cross-border Data Policies (data localisation)
All indicators are **extraction scope** (not "binding commitments" / P6-I5, which is non-regulatory).

| ID | Title | Legal Test |
|---|---|---|
| **P6-I1** | Ban and local processing | Law outright BANS cross-border transfer OR requires data to be PROCESSED locally. Most restrictive. |
| **P6-I2** | Local storage requirements | Law requires personal data to be STORED in a database/facility located IN-COUNTRY. |
| **P6-I3** | Infrastructure requirements | Law requires LOCAL SERVERS / DATA CENTRES / INFRASTRUCTURE as a condition to supply a service. |
| **P6-I4** | Conditional flow regimes | Cross-border transfer ALLOWED ONLY IF conditions are met (consent, adequacy, contract, approval, evaluation). |

**Key distinctions:**
- P6-I1 = ban (no conditions)
- P6-I4 = conditional (conditions can be met to enable transfer)
- P6-I2 = storage location
- P6-I3 = infrastructure mandate

### Pillar 7: Domestic Data Protection (framework & cybersecurity)

| ID | Title | Legal Test |
|---|---|---|
| **P7-I1** | Comprehensive data-protection framework | Law establishes a general data-protection FRAMEWORK (not just a sectoral rule). |
| **P7-I2** | **Dedicated CYBERSECURITY framework** | Law includes a DEDICATED CYBERSECURITY framework/law (e.g., Cybersecurity Act 2018). **NOT** "purpose limitation" or GDPR terms. |
| **P7-I3** | Minimum data-retention requirements | Law specifies MINIMUM duration data must be RETAINED (e.g., "retain for 5 years"). |
| **P7-I4** | DPO / DPIA requirements | Law requires a Data Protection Officer (DPO) or Data Protection Impact Assessment (DPIA). |
| **P7-I5** | Government access to personal data | Law grants government access to personal data (e.g., law enforcement, tax, emergency). |

**Key distinction:** P7-I2 is **cybersecurity**, not a generic "protection framework" — look for dedicated cybersecurity legislation.

### Verification Against Official Answer Key (Singapore example)
- 6.1 ← PDPA (no ban)
- 6.2 ← Companies Act §199
- 6.4 ← PDPA §26 (conditional transfer)
- 7.1 ← PDPA
- 7.2 ← **Cybersecurity Act 2018** (dedicated cybersecurity, not PDPA)
- 7.3 ← PDPA §25 / Telecom / Income Tax / Companies Act §199
- 7.4 ← PDPA §11(3) DPO
- 7.5 ← Criminal Procedure Code §39-40 (police access)

**GOTCHA:** `OUTPUT_TEMPLATE_31MAY.xlsx` "Indicator Reference" sheet mislabels P7-I2 as "purpose limitation" (GDPR term) — **ignore it**. The scored answer key above is correct. Your submission CSV must match the "Output Data" sheet (13 columns), not the mislabeled "Indicator Reference" sheet.

**Coded definitions live in:** `backend/rdtii/indicators.py` (Indicator.legal_test for each)

---

## 3. PROJECT ARCHITECTURE

### Two Execution Paths (by design)
1. **`--live`** (scored path) — crawls live government portals, fetches docs, no seed URLs
2. **Default (sample)** — runs offline on bundled sample corpus (`data/samples/SG`, `data/samples/AU`, `data/samples/MY`)

Both paths use **identical extraction → mapping → confidence → export code**; only the document *source* differs. A successful sample run is an honest preview of the live run.

### Data Pipeline
```
Input: (economy, pillar)
  ↓
┌─────────────────────────────────────────────────┐
│ ZONE 1 — Discovery & Document Fetch             │
│  • sample corpus (offline) OR                    │
│  • web search (site: scoped) + live portal crawl │
│  • tags KNOWN (sample) vs NEW (crawled)          │
│  • TLS-spoofing browser (Scrapling) for WAF      │
└─────────────────────────────────────────────────┘
  ↓ [HTML, PDF text-layer, PDF image scans]
┌─────────────────────────────────────────────────┐
│ ZONE 2 — OCR & Extraction                       │
│  • MarkItDown (text PDFs) — default              │
│  • RapidOCR or PaddleOCR (scanned PDFs)         │
│  • auto-detects "secretly scanned" PDFs         │
│  • measures CER (Character Error Rate < 5%)     │
│  • splits into article/§ chunks (verbatim)      │
└─────────────────────────────────────────────────┘
  ↓ [clean, article-level provisions]
┌─────────────────────────────────────────────────┐
│ ZONE 2 — Retrieval & Mapping                    │
│  • BM25 + dense MiniLM + cross-encoder rerank  │
│  • surfaces top-k provisions per indicator      │
│  • LLM maps provision → best-fit indicator      │
│  • shows model all sibling indicators (no ambig)│
│  • generates confidence score (4 signals)       │
└─────────────────────────────────────────────────┘
  ↓ [mappings with confidence + verbatim snippets]
┌─────────────────────────────────────────────────┐
│ Output Formatting & Review Routing              │
│  • CSV (13 columns, official template)          │
│  • JSON (full trace, audit trail)               │
│  • SQLite (review database)                     │
│  • confidence < 0.85 → pending_review            │
│  • confidence < 0.60 → quarantine                │
└─────────────────────────────────────────────────┘
```

### Key Modules

| Module | File(s) | Responsibility |
|---|---|---|
| **Discovery** | `backend/pipeline/discovery.py`, `zone1.py` | Sample corpus indexing + live web-search/crawler skeleton |
| **OCR** | `backend/pipeline/ocr.py`, `backend/providers/ocr_*.py` | Detects text layer, routes to MarkItDown/RapidOCR/Paddle/Azure/Tesseract; CER measurement |
| **Extraction** | `backend/pipeline/extraction.py` | Splits into article/§ chunks; verbatim preservation |
| **Retrieval** | `backend/pipeline/retrieval.py`, `retrieval_lightrag.py` | BM25 + MiniLM embeddings + cross-encoder; LightRAG fallback for scale |
| **Mapping** | `backend/pipeline/mapping.py` | LLM decision logic (best-fit indicator + siblings) |
| **Indicators** | `backend/rdtii/indicators.py` | RDTII definitions (legal_test, query_terms per indicator) |
| **Confidence** | `backend/pipeline/confidence.py` | 4-signal scoring (model confidence, retrieval quality, rarity flag, scope flag) |
| **Export** | `backend/export/csv_export.py`, `json_export.py` | Official CSV template (13 cols) + JSON trace |
| **Orchestrator** | `backend/pipeline/orchestrator.py` | End-to-end run, SQLite audit trail |
| **CLI** | `main.py`, `backend/cli.py` | Command-line interface |
| **Frontend** | `frontend/app.py` | Streamlit dashboard (pick economy, pillar, LLM, OCR engine) |

### LLM Providers (vendor-agnostic)
- **OpenRouter** (default, free models) — `meta-llama/llama-3.3-70b-instruct:free` with auto-failover
- **Anthropic Claude** — `claude-opus-4-8` or other models
- **OpenAI** — `gpt-4o`
- **Gemini** (experimental)
- **Local Ollama** — no keys
- **Mock** (offline, deterministic) — for reproducible demos

Register new providers in `backend/providers/llm_factory.py`.

### OCR Engines
- **MarkItDown** (default, text PDFs) — Microsoft's text-layer extraction, high fidelity
- **RapidOCR** (pip-only, scanned) — ONNX-based, CER ≈ 1%, Jetson-friendly
- **PaddleOCR** (scanned, multilingual) — PP-OCRv5, CER ≈ 0%, ~1 GB overhead
- **Tesseract** — free, open-source image OCR
- **Azure Document Intelligence** — strongest on noisy real-world gazette scans
- **Mock** (offline sidecar)

---

## 4. IMPLEMENTATION STATUS & KEY DECISIONS

### Completed
✅ **Core pipeline** — discovery, OCR (MarkItDown + RapidOCR + Paddle), extraction, mapping, confidence routing  
✅ **RDTII indicator definitions** — all 9 indicators (P6-I1..I4, P7-I1..I5) coded with legal_test + query_terms  
✅ **Output format** — CSV 100% matches official template; JSON with audit trail  
✅ **LLM abstraction** — OpenRouter/Claude/OpenAI/Gemini/local Ollama swappable via config  
✅ **Frontend dashboard** — Streamlit app (pick economy/pillar/LLM/OCR)  
✅ **Sample corpus** — SG, AU, MY with bundled sample documents  
✅ **Offline reproducibility** — `--live` vs default for demo stability  
✅ **SQLite audit store** — review database for human-in-the-loop  
✅ **CER measurement** — scanned PDF quality grading (< 5% pass)  
✅ **Discovery tagging** — KNOWN (sample) vs NEW (crawled) labels  
✅ **Confidence routing** — auto-accept (≥0.85) / review (0.60–0.85) / quarantine (<0.60)  

### In Progress / Near-Complete
⚠️ **Live crawling (Zone 1)** — web-search + Scrapling browser fetch functional; SG (token-AJAX) + MY (DataTables) need Playwright escalation testing  
⚠️ **Retriever selection** — hybrid (BM25 + dense + rerank) default; LightRAG fallback for large corpora (≥40 provisions) when LLM key is available  
⚠️ **Multilingual retrieval** — embed = multilingual MiniLM; cross-encoder = English-only (mitigated by grade-all policy for small corpora)  

### Known Gaps
❌ **Live crawl not wired to SG/MY portals yet** — discovery skeleton is ready; Playwright auto-escalation for JS-heavy sites (DataTables, token auth) needs QA  
❌ **No real-world test on final 3 economies** — Thailand/China/India/Indonesia/Russia/Lao/Mongolia/Timor-Leste are for Finals; Round 1 is SG/AU/MY only  
❌ **Mock grader is lexical only** — can confuse closely-related indicators (P6-I1 vs P6-I4, P7-I1 vs P7-I2) without a real LLM  
❌ **Manual review UI** — confidence routing flags rows for review, but the review workflow is minimal (data structure exists, UI not built)  
✅ **Scoring (Zone 3) is implemented** — each mapped measure gets an RDTII Raw Score (0/0.5/1) + Coverage + Impact per the official scoring criteria (`backend/rdtii/scoring_rubric.py`); a separate scored CSV mirrors the answer-key Database shape (the mandatory 13-col submission CSV is left untouched). ⚠ Polarity is INVERTED for 7.1/7.2 (a comprehensive/dedicated horizontal framework scores 0); indicator roll-up takes MIN for those, MAX otherwise. See `backend/pipeline/scoring.py`, toggle via `SCORING_ENABLED`.  

---

## 5. FRONTEND DESIGN REQUIREMENTS

**Requirement:** All UI/CSS/frontend work **must use the `frontend-design` skill**.

### Design Direction: "Legal Dossier"
The dashboard should evoke a refined editorial aesthetic—like reviewing an evidence file or legal brief:
- **Background:** Parchment (#f4f1ea light / #0a1024 dark) with faint grain texture
- **Typography:**
  - **Display/masthead:** Fraunces (serif, distinctive)
  - **Body text:** Newsreader (serif, readable)
  - **Code/citations:** IBM Plex Mono (monospace)
- **Color system ("verdict" palette):**
  - **Forest (#3ddc84 dark / #2f5d3a light):** auto-accept (confidence ≥0.85)
  - **Ochre (#f3b34a dark / #a9742a light):** review (0.60–0.85)
  - **Oxblood (#ff6b6b dark / #7c2d2d light):** quarantine (<0.60)

**Avoid:**
- Generic AI aesthetics (Inter, Roboto, purple-gradients-on-white)
- Spectacle; data is the drama
- Light sans-serif for long-form legal text

**Current state:** `frontend/app.py` has the design system defined; colors and fonts are set. When adding new UI elements, preserve this aesthetic.

---

## 6. RUNNING & TESTING

### Quick Start (Offline Sample)
```bash
python main.py --economy Singapore --pillar 6
```
Outputs CSV + JSON to `outputs/`. Uses sample corpus, no LLM key, reproducible.

### Live Crawl (Scored Path)
```bash
python main.py --economy Singapore --pillar 6 --live --llm openrouter
```
Discovers laws from live portals, fetches, extracts, maps.

### Dashboard
```bash
streamlit run frontend/app.py
```
Pick economy, pillars, LLM, OCR engine in sidebar.

### Batch Run
```bash
python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7
```

### Test Suite
```bash
pytest tests/
```
- `test_output.py` — CSV template validation
- `test_mapper.py` — Known indicator mappings
- `test_ocr.py` — MarkItDown extraction
- `test_scanned_ocr.py` — RapidOCR CER <5% on bundled scan
- `test_zone2_retriever.py` — Retriever selection (hybrid/LightRAG fallback)
- `test_scrapling_fetch.py` — Browser fetch + WAF bypass
- `test_input.py` — Economy code/UN name/typo tolerance

### Cost Measurement
```bash
python tools/cost_logger.py --pdf data/samples/AU/privacy_act.pdf --economy Australia --pillar 6
```
Logs wall-clock, token cost (if applicable) to `logs/cost_report.json`.

### Discovery Evaluation
```bash
python evaluate.py --economy Singapore
```
Reports KNOWN (sample-kit) vs NEW (crawled) provisions, coverage by indicator.

---

## 7. MULTILINGUAL & RETRIEVAL STRATEGY

### Retrieval Stack
- **Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2` (multilingual, covers Malay, Thai, Chinese, Russian…)
- **Cross-encoder reranker:** `ms-marco-MiniLM-L-6-v2` (English-only; weak on non-English text)
- **Query terms:** English keywords in `indicators.py`; weak lexical match on non-English law

### Why This Works for Round 1
Round 1 is SG/AU/MY (English/Malay, both covered by multilingual embed). Non-English weakness is low-risk now.

### Mitigation: Grade-All Policy
When corpus ≤80 provisions, **every provision is graded by the LLM against every indicator** → retrieval is just a signal, not a gate. The grading LLM is multilingual (gpt-oss/Gemini), so the decision is robust even if retrieval ranking is imperfect. Only large live crawls (hundreds of provisions) fall back to a shortlist, where a multilingual reranker (e.g., `BAAI/bge-reranker-v2-m3`) would help.

**How to apply:** For Finals (China, Russia, Lao, Mongolia), if non-English retrieval is weak, either:
- Swap cross-encoder to a multilingual model (set `CROSS_ENCODER_MODEL`)
- Increase `grade_all_max_provisions` to ensure all provisions are graded

---

## 8. KNOWN LIMITATIONS & HONESTY STATEMENT

The tool is built to be auditable, not hidden:

1. **Live crawling** is functional but needs Playwright auto-escalation for SG/MY token-auth and JS-heavy sites (DataTables).
2. **Scanned/image PDFs** are handled by real raster OCR (RapidOCR/Paddle), measured CER on bundled sample is 1.11% (PASS <5%).
3. **Mock grader** is lexical (offline) and can confuse P6-I1/P6-I4, P7-I1/P7-I2 without a real LLM → always use a real LLM (OpenRouter/Claude) for submission.
4. **Indicator `legal_test`** are our interpretation of the RDTII methodology; review pending_review rows before submission.
5. **Confidence scores** are relative, not calibrated probabilities.
6. **Multilingual retrieval** is general-domain, not legal-domain; for non-English, rely on grade-all policy.

---

## 9. JUDGING CRITERIA & SELF-EVALUATION CHECKLIST

Use this as if you're a judge reviewing VeriTrade for the RDTII hackathon:

### **Technical Completeness (What we submit must do)**
- [ ] **Zone 1 mandatory:** Autonomous discovery from live gov portal (no seed URLs), no hardcoded law names
  - [ ] SG: sso.agc.gov.sg works (token-AJAX or direct fetch)
  - [ ] AU: legislation.gov.au works (JSON API confirmed)
  - [ ] MY: lom.agc.gov.my works (DataTables-AJAX, may need Playwright)
  - [ ] Crawl is live, reproducible with current portal state, not a baked corpus
- [ ] **Zone 2 mandatory:** OCR + extraction
  - [ ] Text-layer PDFs work (MarkItDown)
  - [ ] Scanned/image PDFs work (RapidOCR or Paddle, CER <5%)
  - [ ] Article/§ structural parsing preserves verbatim snippets and citations
- [ ] **Both Pillars 6 & 7:** submitted CSV includes P6-I1..I4 and P7-I1..I5 mappings
- [ ] **Output format:** CSV matches template exactly (13 columns, order, headers)
- [ ] **Indicators mapped correctly:** sample check against answer key (SG PDPA→7.1, Cybersecurity Act→7.2, etc.)

### **Robustness**
- [ ] Sample run (offline) is reproducible, < 10 min, no keys
- [ ] Live run tolerates portal downtime gracefully (fallback to sample or error message)
- [ ] CER is measured and reported in JSON (`ocr_quality.cer`)
- [ ] Verbatim snippets are exact (not paraphrased)
- [ ] All mappings have article-level citations (not vague page refs)

### **Code Quality**
- [ ] No hardcoded economy/law names in discovery logic
- [ ] Provider abstraction works (swap LLM/OCR via config, no code changes)
- [ ] Audit trail (SQLite, JSON export) captures decision rationale
- [ ] Tests pass locally and in CI

### **Demonstration Quality (for Round 1 judges)**
- [ ] Lead demo with `--live` (not sample) to show autonomous discovery
- [ ] Show OCR quality: run the bundled scanned PDF, display CER measurement
- [ ] Show the dashboard (Streamlit) picking economy/pillar, real-time run
- [ ] Explain the CSV output, compare to answer key

---

## 10. IMPROVEMENT PRIORITIES FOR FINALS (IF SHORTLISTED)

### High Priority (confidence for score boost)
1. **Playwright auto-escalation for SG/MY** — ensure token-AJAX and DataTables sites resolve without manual intervention
2. **Multilingual cross-encoder reranker** — swap to `BAAI/bge-reranker-v2-m3` for Finals (China, Russia, Lao, Mongolian text)
3. **Manual review UI** — build the workflow.py skeleton into a functional reviewer dashboard (flag low-confidence, allow edit/accept/reject, export amended CSV)
4. **CER calibration** — validate CER measurement on real gazette scans (not just the bundled sample) using Azure Document Intelligence as a ground-truth baseline

### Medium Priority (robustness)
5. **Batch job scheduler** — for judges to run multiple economies in one command with progress tracking
6. **Caching strategy** — cache crawled documents per URL, avoid re-fetching same law across multiple pillar runs
7. **Error recovery** — if one document fails OCR, mark it and continue (don't stall the whole run)
8. **Confidence calibration** — collect feedback on low/high confidence rows to tune the 4-signal model

### Low Priority (polish, if time permits)
9. **Multi-language UI** — Vietnamese translation for FTU team demos
10. **Docker image baking** — HuggingFace model weights baked into the image for offline deployment

---

## 11. QUICK REFERENCE: FILE PATHS & CONFIG

| Task | Command / File |
|---|---|
| Run sample (offline) | `python main.py --economy Singapore --pillar 6` |
| Run live | `python main.py --economy Singapore --pillar 6 --live --llm openrouter` |
| Dashboard | `streamlit run frontend/app.py` |
| Change LLM | Edit `.env`: `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...` |
| Change OCR | Edit `.env`: `OCR_PROVIDER=rapidocr` or `paddle` |
| Change retriever | Edit `.env`: `RETRIEVER=auto` (default) or `hybrid` or `lightrag` |
| Run tests | `pytest tests/` |
| View audit trail | `logs/run_<timestamp>.log` or SQLite: `backend/storage/*.db` |
| Output files | `outputs/<Economy>_P<pillar>_<timestamp>.csv/json` |
| Indicator definitions | `backend/rdtii/indicators.py` |
| Sample corpus | `data/samples/<Economy>/` |
| Config reference | `backend/config.py` |

---

## 12. CONTACT & DOCUMENTATION

- **Team email:** minhtc@ftu.edu.vn
- **Hackathon:** https://www.eng.kmitl.ac.th/digitaltradehack2026/ (KMITL)
- **Repo:** VeriTrade, FTU
- **License:** Apache 2.0

---

## Last Updated
2026-06-07  
Claude Code auto-memory + consolidated from project memory files + README + code inspection.
