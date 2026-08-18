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
- A regulatory pillar (6 = Cross-border Data Policies; 7 = Domestic Data Protection and Privacy)

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

**RDTII = Regional Digital Trade Integration Index** (NOT "Regulatory"). Full framework (ESCAP, 2025) has **12 pillars**; VeriTrade targets **pillars 6 and 7 only** (9 indicators total). Official pillar names: Pillar 6 = "Cross-border data policies"; Pillar 7 = "Domestic data protection **and privacy**".

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

### Pillar 7: Domestic Data Protection and Privacy (framework & cybersecurity)

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
| **Corpus (precompute)** | `backend/corpus/` | L0 catalogue → L1 fetch → L2 extract → L3 split, stored per LAW VERSION. `store.py` `catalogue.py` `build.py` `version.py` `cli.py`. Stops at L3 — candidate selection (L4) and grading (L5) are not wired yet. See `docs/precompute-corpus.md` |
| **Evaluation** | `backend/eval/` | Labels from the judges' Database (`ground_truth.py`), law linkage, stratified eval corpus, retrieval metrics (`harness.py`), sweepable ranker (`rank_lab.py`), grader/confidence experiment (`grader_eval.py`). See `docs/retrieval-redesign.md` |
| **CLI** | `main.py`, `backend/cli.py` | Command-line interface |
| **Frontend** | `frontend/app.py` | Streamlit dashboard — shell, sidebar, tabs, exports |
| **Results surface** | `frontend/matrix.py` + `components/matrix/` | Coverage matrix: laws × 9 indicators; press a cell for the evidence |
| **Run surface** | `frontend/runview.py` | The live run as five stages + counters, not a log |
| **Engine surface** | `frontend/enginebench.py` | OCR/LLM chosen on the main screen, each card stating purpose, readiness, cost, where the document goes |

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
✅ **Three portal defects found and fixed (2026-08-15)** — all were SILENT, all cost whole Acts:
  (1) `legislation.gov.au` publishes large Acts as **multi-volume** compilations and 404s on the
  single-file PDF URL — the Telecommunications (Interception and Access) Act 1979 was yielding
  **1 provision instead of 618**, and the Telecommunications Act 1997 **0 instead of 1,377**;
  fixed via `discovery._au_compilation_pdf_urls` + per-volume splitting in `corpus/build.py`.
  (2) `lom.agc.gov.my` now **AES-GCM-encrypts** its catalogue JSON (key published in its own
  page); the shipped MY adapter was silently returning **0 Acts** — see `pipeline/portal_crypto.py`.
  (3) `sso.agc.gov.sg` **ignores `CurrentPage`**, so its index is enumerated by sort-window union.
❌ **10 of 37 laws the judges cite are outside our catalogue** — PDPC/OAIC guidance, an IMDA
  licence, AU's Telecommunications Regulations 2021 (an instrument, not an Act), MY sectoral
  Codes of Practice + PDP Standard 2015. **This is the largest remaining coverage gap, and it
  is a discovery problem, not a retrieval one.**  
❌ **No real-world test on final 3 economies** — Thailand/China/India/Indonesia/Russia/Lao/Mongolia/Timor-Leste are for Finals; Round 1 is SG/AU/MY only  
❌ **Mock grader is lexical only** — can confuse closely-related indicators (P6-I1 vs P6-I4, P7-I1 vs P7-I2) without a real LLM  
❌ **Manual review UI** — confidence routing flags rows for review, but the review workflow is minimal (data structure exists, UI not built)  
✅ **Scoring (Zone 3) is implemented** — each mapped measure gets an RDTII Raw Score (0/0.5/1) + Coverage + Impact per the official scoring criteria (`backend/rdtii/scoring_rubric.py`); a separate scored CSV mirrors the answer-key Database shape (the mandatory 13-col submission CSV is left untouched). ⚠ Polarity is INVERTED for 7.1/7.2 (a comprehensive/dedicated horizontal framework scores 0); indicator roll-up takes MIN for those, MAX otherwise. See `backend/pipeline/scoring.py`, toggle via `SCORING_ENABLED`.  

---

## 5. FRONTEND DESIGN REQUIREMENTS

**Requirement (2026-08-14):** All UI/UX/CSS/frontend work must go through the **`ui-ux-pro-max`** skill
(https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), installed at `.claude/skills/`. Invoke it with
the Skill tool *before* writing interface code — it ships searchable local data (styles, palettes, font
pairings, UX guidelines, chart types, per-stack notes) that the design decisions below should be checked
against. Companion skills installed alongside it: `design`, `design-system`, `ui-styling`, `brand`,
`slides`, `banner-design`.

Reinstall or update with `npx ui-ux-pro-max-cli@latest init --ai claude` from the repo root. The skill
directory is gitignored (tooling, not a deliverable), so a fresh clone runs that command once.

**Superseded:** `taste-skill` and the built-in `frontend-design` skill are both retired for this project;
do not pull or apply either. The design decisions already made below still stand as project constraints —
`ui-ux-pro-max` informs *new* work, it does not license a redesign of the shipped dashboard.

### Design-system plumbing (2026-08)
Two files, one palette, and they must stay in sync:
- **`.streamlit/config.toml`** styles Streamlit's **native** widgets. It defines BOTH `[theme.light]` and `[theme.dark]` (plus Inter/IBM Plex Mono via the `"Name:URL"` font form). Defining only one base was why light mode kept inheriting dark chrome.
- **`frontend/theme.py`** styles **our own** markup, from the same hex values.

Light/dark: the visible toggle (`theme.theme_toggle()`) writes **Streamlit's own** preference — `localStorage["stActiveTheme-<pathname>-v2"] = "Light"|"Dark"|"System"` — then reloads, which is exactly what its Settings dialog does. The app then *follows* `st.context.theme.type`.

**Never give the app its own theme flag** (e.g. `session_state["dark"]`). That was the original bug: a private flag repainted only our markup while native widgets kept the config theme. One source of truth — Streamlit's — or the two halves drift apart again.

### Design Direction: "Clear Research Tool" (2026-07 redesign)
**Audience-first.** The users are **policy researchers (non-technical)**, who found the earlier "Legal Dossier" aesthetic hard to use. The dashboard now prioritises **clarity and ease of use over editorial style**: a public-sector / trust-first posture (low visual variance, minimal motion, plain language, progressive disclosure).
- **Background:** clean white (#ffffff light) / deep slate (#0b1120 dark). No parchment, no grain.
- **Typography:** **Inter** (sans-serif) for everything; **IBM Plex Mono** for citations, IDs, URLs, numbers only. No serif (Fraunces/Newsreader were removed).
- **Accent:** single trustworthy blue (#2563eb light / #4f9cff dark).
- **Confidence traffic-light** (semantic, kept as a documented exception to one-accent):
  - **Green (#15803d / #34d399):** high confidence — auto-accepted (≥0.85)
  - **Amber (#b45309 / #fbbf24):** needs a check (0.60–0.85)
  - **Red (#dc2626 / #f87171):** low confidence — set aside (<0.60)
- **RDTII restrictiveness score:** neutral **grey** chip (a different axis from confidence — never the traffic-light colours).

**Usability rules (why the redesign exists):**
- **Plain language, no metaphor jargon.** "Run analysis" not "Commission a run"; "Needs review" not "Verdict queue"; "Text-extraction quality" not "OCR forensics"; "Results/Details/Download" tabs, "Country/Topic" controls. A first-time researcher should never have to decode a metaphor.
- **Progressive disclosure.** The sidebar is a 3-step flow — Country → Topic → Run — on smart defaults. **All** engine/LLM/OCR/model/key/scoring controls live inside a collapsed **"Advanced settings"** expander.
- **Guided empty state** (3-step welcome) + a **plain-language confidence legend** (what green/amber/red mean) on every result page.
- Minimal motion; one corner-radius scale; WCAG-AA contrast in both themes.

**Avoid:** metaphor/editorial jargon, serif for the working surface, dumping technical controls on non-tech users, spectacle over clarity.

### The three working surfaces (2026-08-19 rebuild)
The dashboard was rebuilt around what a policy researcher actually asks, after feedback that
block-by-block panels were clear but not usable enough. `docs/redesign.html` is the
interactive demo these were agreed from — open it directly, or at
`/app/static/redesign.html` while the app is running.

1. **Results = coverage matrix** (`frontend/matrix.py`). Laws down the side, the nine
   indicators across the top. A gap is an empty column with a red zero under it; a law
   meeting several indicators is one row crossing several columns; an amber result is
   found by eye. The evidence panel leads with the indicator's `legal_test`, then the
   verbatim quote, and only then the confidence — so the mapping can be *judged*, not
   taken on trust. It is a real bidirectional component because `st.markdown` is
   write-only and a clicked cell must reach Python.
   **Column widths are measured, not guessed** — the Results column runs ~1050px, so the
   matrix is sized to clear 660px with all nine indicators visible; header labels may not
   contain a word longer than nine characters or the ninth indicator scrolls off.
2. **Run = five stages, not a log** (`frontend/runview.py`). It consumes the `log()`
   strings the pipeline already emits, so the pipeline needs no change and the two cannot
   drift. Add a new log prefix → add it to `STAGES` there. The raw log still runs, into a
   collapsed expander.
3. **Engines on the main screen** (`frontend/enginebench.py`). Provider-swappability is
   scored, so it is no longer two dropdowns inside a collapsed expander. Every figure on a
   card is measured in this repo or a plain fact; where nothing was measured the card says
   *"not measured here"* rather than inventing a number. The sidebar only reads the choice
   back — two widgets writing the same choice is how they drift apart.

**Current state:** `frontend/app.py` and `.streamlit/config.toml` implement this. When adding UI, preserve this clean, plain-language, progressive-disclosure system — do NOT reintroduce the parchment/serif dossier look.

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

### Retrieval parameters are MEASURED — do not hand-tune them
`hybrid_alpha=0.65`, `retrieve_max_top_k=300`, `retrieve_per_law_k=1`, `dense_recall_extra=0`
were derived by sweeping against the judges' own Round-1 Database on a 383-law / 36.6k-provision
corpus (provision recall 0.833 → **1.000**). Two results are counter-intuitive and are recorded
so they are not re-litigated: a **law-level prefilter makes recall worse** at every budget, and
`retrieve_per_law_k=3` degenerates into one-provision-per-law (breadth without depth) on a
multi-hundred-law corpus. Re-run `tools/sweep_retrieval.py` + `tools/validate_retrieval.py`
before changing any of them. Full write-up: `docs/retrieval-redesign.md`.

### Retrieval Stack
- **Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2` (multilingual, covers Malay, Thai, Chinese, Russian…)
- **Cross-encoder reranker:** `ms-marco-MiniLM-L-6-v2` for Latin-script economies;
  `BAAI/bge-reranker-v2-m3` (`cross_encoder_model_multilingual`) for non-Latin. A non-Latin
  economy NEVER falls back to the English model — if the multilingual one is unavailable the
  reranker is switched OFF, because an English cross-encoder on Chinese text contributes noise
  to the fusion at the same weight as BM25.
- **Query terms:** English in `indicators.py`, PLUS native statutory phrases per language in
  `backend/rdtii/query_terms_i18n.py` (additive, lexical side only — the dense query stays
  English because the embedding model is cross-lingual by construction).
- **Tokenisation is script-aware** (`retrieval._tok`): no-space scripts (Han/kana/Thai/Lao/
  Khmer/Myanmar) are indexed as character BIGRAMS; ASCII keeps the exact Round-1 `[a-z0-9]+`
  path so the measured parameters below still hold; other scripts tokenise as words.

### Round 2 — China, India, Mongolia (see `docs/round2-expansion.md`)
The English-only assumption was load-bearing well beyond the LLM. The worst breakage was
`_TOKEN = [a-z0-9]+`, which returns NO tokens for 不得向境外提供 — so every Chinese provision
scored a flat 0.0 on BM25 (65% of the hybrid score) with nothing in any log to show it. That is
the shape of every bug in this expansion: **nothing throws**; the run completes and reports "No
provision found", which is indistinguishable from an economy that has no such law.

**Prompting strategy for non-English provisions:** English instructions + the provision fed
UNCHANGED + `<SNIPPET_LANGUAGE>` naming the language + a step-8 rule that output
(`operative_rule`, `rationale`) must be ENGLISH while the snippet is never rewritten. Translating
the snippet is not an option — the Verbatim Snippet column IS the statute's text, so a translated
snippet is a false citation. A Chinese worked example (PIPL art.40 → 6.2, the panel's own answer)
is placed first in SYSTEM to demonstrate the rule rather than describe it.

⚠ **Round-2 portals are all `verified: false`** and no CN/IN/MN corpus has been built yet, so
none of this is measured. Mongolian native terms are a SEED vocabulary (agglutinative: BM25
indexes "дамжуулахыг", so the stem "дамжуулах" may never fire) — validate with
`tools/audit_native_terms.py --economy MN --suggest` before trusting them.

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
| Accounts / sessions | `backend/auth/service.py` · docs: `docs/AUTH_AND_DATABASE.md` |
| Landing + sign-in screen | `frontend/auth_ui.py` (the app's signed-out state) |
| Design system (shared) | `frontend/theme.py` + `.streamlit/config.toml` |
| Storage engine / schema | `backend/storage/engine.py` (SQLAlchemy; `DATABASE_URL` → Postgres) |
| Bypass login for a demo | `AUTH_ENABLED=false` in `.env` |
| Run sample (offline) | `python main.py --economy Singapore --pillar 6` |
| Run live | `python main.py --economy Singapore --pillar 6 --live --llm openrouter` |
| Dashboard | `streamlit run frontend/app.py` |
| Change LLM | Edit `.env`: `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...` |
| Change OCR | Edit `.env`: `OCR_PROVIDER=rapidocr` or `paddle` |
| Change retriever | Edit `.env`: `RETRIEVER=auto` (default) or `hybrid` or `lightrag` |
| Run tests | `pytest tests/` |
| Enumerate an economy's whole corpus | `python -m backend.corpus.cli catalogue --economy MY` |
| Fetch/extract/split it | `python -m backend.corpus.cli build --economy MY` |
| Corpus contents | `python -m backend.corpus.cli stats` |
| Rebuild eval labels | `python -m backend.eval.ground_truth` · `python -m backend.eval.linkage` |
| Ground-truth reference (6 economies) | `python tools/build_reference_dataset.py` → `data/ground_truth/rdtii_reference_p67.csv` |
| Check native retrieval terms | `python tools/audit_native_terms.py --economy MN --suggest` |
| Re-measure retrieval | `python tools/sweep_retrieval.py --stage final` |
| Verify shipped retrieval | `python tools/validate_retrieval.py` |
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
2026-08-19 — Round-2 expansion (CN/IN/MN): multilingual retrieval, script-aware extraction, language-aware grading prompt. See `docs/round2-expansion.md`.
2026-06-07  
Claude Code auto-memory + consolidated from project memory files + README + code inspection.
