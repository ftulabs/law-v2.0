# VeriTrade — Pitch Deck Content

> Content pack for the ESCAP/KMITL pitch-deck template (13 slides). Hand this whole file to
> Claude to design the deck. Every number here is measured from the real system — keep them.
> `‹FILL›` marks the only spots that need human input (names, screenshots, final metrics).
>
> **Editorial rule for this deck:** never say "we use AI/OCR/RAG" without immediately saying
> *which mechanism* and *which measured number*. Every team in the room has "AI + OCR + RAG".
> Only we have "the portal's own DataTables JSON, a TLS-fingerprint fetcher, font-glyph heading
> detection, and a sibling-penalty reranker" — the deck must sound like that.

**Design brief for the deck:** ESCAP/KMITL template — light blue header band, white body, ESCAP +
KMITL logos top-right on every slide. Clean, professional, government/UN tone. One idea per slide,
generous whitespace, sans-serif. Use VeriTrade's accent blue (#2f7fe6). Prefer a diagram or a small
table over a wall of text. Slides 7–8 (Backend Logic) can be denser (technical judges).

---

## Slide 1 — Project Title & Team

**Project name:** VeriTrade — Autonomous Evidence Discovery & Regulatory Mapping for Digital Trade

**Tagline (one line under the title):** *Find the law, prove the clause — automatically.*

**Team:** FTU (Foreign Trade University, Vietnam)
- ‹FILL› Technical Lead — name — AI architecture, discovery/OCR/RAG pipeline
- ‹FILL› Substantive Lead — name — legal/policy analysis, RDTII mapping, output QA
- ‹FILL› additional members + roles
- Contact: minhtc@ftu.edu.vn

**Visual:** VeriTrade wordmark centered; ESCAP + KMITL logos; "UN Global Hackathon on AI for
Digital Trade Regulatory Analysis · Round 1 · Singapore · Australia · Malaysia".

---

## Slide 2 — Executive Summary (one slide)

**One-liner:** Given only an **economy** and a **pillar**, VeriTrade autonomously finds the laws on
the official portals, reads them (including scanned PDFs), and returns each provision mapped to its
RDTII indicator — with a verbatim quote, an article-level citation, a source URL, and a confidence
score. **No seed URLs. No hardcoded law names. Every row auditable.**

**Four points (use as four columns/icons) — lead with the mechanism, not the buzzword:**
1. **Problem** — RDTII compilation is manual legal research across bespoke, bot-protected,
   multilingual portals. It doesn't scale and a second reviewer can't reproduce it.
2. **Discovery that adapts per portal** — full-text web search where the portal is indexed (SG),
   the official OData API where full-text search is broken (AU), and the portal's **own catalogue
   JSON** where Google can't see it at all (MY). One framework, three verified entry strategies.
3. **Extraction that survives real documents** — TLS-fingerprint fetching clears WAFs; OCR is
   **measured** (CER 1.11% vs ground truth); AU section headings are detected **by font weight**
   because their PDFs never say "Section".
4. **Mapping a keyword classifier can't do** — the LLM grades each (provision × indicator) pair
   while seeing every *sibling* indicator's legal test, so "conditional transfer" (P6-I4) is never
   confused with "ban" (P6-I1). Unsure ⇒ human review, never silent acceptance.

**Headline metrics (stat row):** 3 economies · 9 indicators · **CER 1.11%** (bar: 5%) ·
**~$0.07 / economy** LLM cost · **$0.00** on an open-weight stack · CPU-only.

---

## Slide 3 — Problem Statement

**The regulatory challenge:** The UN RDTII index scores every economy on dozens of digital-trade
indicators. Building it means a human researcher must, for each (economy, indicator), *find* the
right statute, *read* the operative clause, *interpret* whether it satisfies the indicator, and
*cite* it precisely. Today this is manual and does not scale to 40+ economies on a regular refresh.

**Why it's hard — each obstacle below is one we hit and solved on the Round-1 portals:**
- **Every portal is different, and none is friendly.** Singapore's search is token/JS-gated.
  Malaysia's `lom.agc.gov.my` is **barely indexed by Google** (a `site:` query returns the homepage).
  Australia's is an Angular single-page app whose law text **doesn't exist in the HTML** a crawler sees.
- **Bot-protected.** WAFs fingerprint the TLS handshake itself — a plain Python crawler gets HTTP
  403 before sending a single request header.
- **Australia's full-text search is broken.** The official OData API's `$search` returns errors —
  so title-only search is a *forced constraint*, and finding topically-relevant laws needs a
  separate content lane.
- **Mixed formats & languages.** HTML, text PDFs, scanned gazettes; Malaysia publishes bilingually
  (Malay authoritative, English reference); Finals add Thai, Chinese, Russian, Lao.
- **The evidence is scattered.** P7-I5 (government access) lives in criminal procedure, telecom,
  and tax law — not the privacy statute. A title-keyword search never finds the Companies Act's
  record-storage clause (P6-I2).
- **Verification burden.** A citation is only trustworthy if the quoted text truly appears in the
  official source — the core anti-hallucination requirement.

**Impact:** slow index refreshes, inconsistent coverage, results a second reviewer can't reproduce.

---

## Slide 4 — Objective of the Project

**Goal:** Automate the professional legal researcher's workflow end-to-end, reproducibly, on a
standard CPU, with no vendor lock-in.

**The system is designed to:**
1. **Discover** — autonomously locate relevant primary legislation on official portals, live, with
   no seed URLs and no hardcoded law names. All queries are *country-agnostic* concept phrases and
   naming conventions ("companies act", "data localisation") — never a specific answer.
2. **Resolve versions** — collapse the many URLs of one law to a single identity (statute number),
   keep only the **in-force consolidated** text, and read the "Last Amended" date from each
   portal's *own* revision timeline (not guessed from the title).
3. **Extract** — parse article-level text from HTML, text PDFs, and scanned PDFs (real raster OCR
   with a measured Character Error Rate < 5%), preserving **verbatim** wording with character
   spans back into the source.
4. **Map** — assign each provision to the correct RDTII indicator (P6-I1…I4 / P7-I1…I5) using
   LLM legal reasoning that sees every sibling indicator to avoid look-alike confusion.
5. **Verify & deliver** — attach a 100%-verbatim snippet, article citation, source URL, and a
   4-signal confidence score; route low-confidence rows to human review; output the exact official
   13-column CSV + a machine-auditable JSON.

**Design principles:** auditable over opaque · reproducible over one-off · swappable components
(LLM/OCR) over lock-in · precision with an explicit human-review safety net.

---

## Slide 5 — System Architecture / Overview

**High-level data flow (render as a left-to-right or top-down diagram):**

```
   INPUT: (Economy, Pillar)
        │
        ▼
┌─────────────────────── ZONE 1 · DISCOVERY & FETCH ───────────────────────┐
│  Discovery (no seed URLs — per-portal strategy)                           │
│   • SG → full-text web search, portal-scoped (Serper → keyless fallback)  │
│   • AU → official OData API (title lane) + full-text content lane,        │
│          every hit re-verified in-force against the register              │
│   • MY → the portal's OWN acts-catalogue JSON (~880 in-force acts,        │
│          bilingual titles) + sectoral Codes of Practice (pdp.gov.my)      │
│  Version resolution: dedup by statute identity → keep in-force            │
│          consolidated → read "Last Amended" from the portal's timeline    │
│  Fetch (bot-resistant): TLS/JA3 browser impersonation → stealth browser   │
│          escalation → httpx fallback · content-addressed cache            │
└──────────────────────────────────────────────────────────────────────────┘
        │  raw documents: HTML · text PDF · scanned PDF
        ▼
┌─────────────────────── ZONE 2 · EXTRACT & MAP ───────────────────────────┐
│  Extract (per-country profiles)      Retrieve (5-signal hybrid)           │
│   • text-density scan detector        • BM25 (lexical)                    │
│   • MarkItDown / RapidOCR (CER        • multilingual dense embeddings     │
│     measured vs ground truth)         • phrase bonus + sibling penalty    │
│   • SG/MY numbered §, AU font-        • cross-encoder rerank              │
│     marked headings; statistical     Map (LLM legal reasoning)            │
│     page-chrome stripping             • grades (provision × indicator)    │
│   • verbatim chunks + char spans      • sees ALL sibling legal tests      │
│                                       • grade-all when corpus ≤ 80        │
└──────────────────────────────────────────────────────────────────────────┘
        │  mappings + verbatim snippets + 4-signal confidence
        ▼
   Confidence routing:  ≥0.85 auto-accept · 0.60–0.85 review · <0.60 quarantine
        │
        ▼
   OUTPUT:  CSV (13 cols) · scored CSV (Zone 3) · JSON audit trail · SQLite
```

**Caption:** Two execution paths share identical extraction→mapping→export code — a live path
(scored) and an offline sample path (reproducible fallback) — so a sample run is an honest preview
of the live run.

---

## Slide 6 — Technology Solution / Innovative Feature

**Not "we use AI" — here is exactly what runs (icon + one line each):**
- **Per-portal discovery adapters** — SG: portal-scoped full-text web search. AU: official OData
  `contains(name,…)` because the API's `$search` full-text is *broken* — verified live. MY: the
  DataTables JSON behind the portal's own acts grid (~880 acts), because Google doesn't index it.
  The *framework* is shared; only the entry strategy per portal differs. Zero law names hardcoded.
- **TLS-fingerprint fetching** — WAFs block on the TLS/JA3 handshake signature, not the headers;
  tier 1 impersonates a real Chrome handshake (no browser needed), tier 2 escalates to a stealth
  browser (Camoufox) that clears JS challenges.
- **JS-shell detection** — AU's site is an Angular SPA; a naive crawler "succeeds" and extracts
  navigation menus as law text. VeriTrade detects the unrendered app shell and resolves the real
  authorised-compilation PDF via the OData documents feed instead. Result: **0 garbage provisions**.
- **Measured OCR** — text-density detector routes "secretly scanned" PDFs to raster OCR
  (RapidOCR/Paddle); CER is measured against a ground-truth sidecar: **1.11%** (bar: 5%). Engines
  that would score a circular 0% are excluded from the metric — honesty by construction.
- **Font-aware, per-country extraction** — SG/MY statutes number sections at the margin
  ("11.—(1)"); AU headings carry *no keyword at all* and are detected by **bold-glyph ratio** in
  the PDF font data. Running headers/footers are stripped *statistically* (a line recurring in the
  page-edge band on ≥¼ of pages is chrome). Keyword forms like "Section 26" in SG/MY bodies are
  cross-references — treating them as boundaries would shred provisions; we don't.
- **5-signal hybrid retrieval** — BM25 + multilingual dense embeddings + literal phrase bonus +
  **sibling penalty** (down-ranks provisions dominated by a confusable indicator's vocabulary) +
  cross-encoder rerank, with a dense-recall floor so a paraphrased provision can't be silently lost.
- **Sibling-aware LLM grading** — each (provision, indicator) call includes every sibling's legal
  test; conservative default (unsure ⇒ reject to review).

**Tech stack & licensing compliance (all permissive — Apache-2.0 project):**

| Layer | Library | License |
| :--- | :--- | :--- |
| Crawl / fetch | Scrapling (curl_cffi/Camoufox), httpx, BeautifulSoup | BSD / BSD / MIT |
| OCR / extract | MarkItDown, RapidOCR, PaddleOCR, pdfplumber, pypdfium2 | MIT / Apache-2.0 |
| Retrieval | sentence-transformers, rank_bm25 | Apache-2.0 |
| App / core | Streamlit, pydantic, SQLite | Apache-2.0 / MIT / public domain |
| LLM (default) | deepseek-v4-flash via OpenRouter (swappable: Claude/GPT/Gemini/Ollama/mock) | API |

---

## Slide 7 — Backend Logic (1 of 2): Discover → Fetch → Extract

**Step 1 — Discover (the part the rubric scores hardest):**
- Queries are built from the indicator definitions, in two lanes: **name fragments** (shared
  naming conventions — "privacy act", "computer crimes act") and **obligation phrases** ("data
  must be stored in", "consent before transfer"). Obligation phrases only fire at portals with
  working full-text search — at a title-only API they can never match and waste the query budget.
- **SG:** search engine scoped `site:sso.agc.gov.sg` (the engine indexed the law *bodies*).
  **AU:** OData title lane + a content lane whose every hit is re-verified **in-force** by
  register title-id (bills, repealed acts, point-in-time compilations dropped). **MY:** filter the
  portal's own bilingual catalogue; English title identified by its "As At" currency marker.
- **Version resolution:** all URL variants of one law collapse to a statute identity (SG SL
  number, MY act number, AU title-id); ranking prefers in-force > principal > consolidated >
  newest. "Last Amended" comes from the portal's own timeline data (SG embeds it as a
  .NET-serialised JSON blob; MY as `data-log-type` events; AU via the compilation feed) — never
  guessed from a year in the title.

**Step 2 — Fetch:** TLS/JA3 impersonation → stealth-browser escalation → httpx fallback; polite
per-host delay; content-addressed cache (same bytes never fetched twice); a landing page that
embeds a PDF viewer is resolved to the actual PDF.

**Step 3 — Extract (chunking strategy — per-country, not one regex):**
- Text-density detector (avg chars/page) catches "secretly scanned" PDFs → raster OCR, CER measured.
- **SG/MY profile:** split on margin-numbered sections ("11.—(1)", "20. (1)"); keyword forms are
  cross-references and deliberately *not* boundaries. **AU profile:** headings detected by
  bold-glyph ratio (≥60% bold on a number-led line), because AU drafting has no "Section" keyword.
- Statistical page-chrome stripping + AU table-continuation dedup + SG consolidation-stamp removal
  → every chunk is **verbatim** with a character span back into the source for re-verification.

---

## Slide 8 — Backend Logic (2 of 2): Retrieve → Map → Verify + Example

**Retrieval — per indicator, five fused signals (semantic + keyword hybrid):**
1. **BM25** — query = the indicator's title + description + *legal test* (whose "distinguish
   from X" notes inject discriminative vocabulary at the cheapest stage).
2. **Dense embeddings** (multilingual MiniLM) — catches paraphrase and cross-language matches; the
   law name is deliberately *excluded* from the embedding so every PDPA section doesn't smell like
   a P7-I1 hit.
3. **Phrase bonus** (+0.10 per literal indicator phrase, cap 0.30).
4. **Sibling penalty** (−0.07 per excess sibling-phrase hit, cap 0.20) — catches P6-I1↔I4 and
   P7-I1↔I2 confusion *before* spending an LLM call.
5. **Cross-encoder rerank** on the shortlist (precision), blended 50/50 — plus a dense-recall
   floor: the strongest pure-semantic matches are re-admitted even if the reranker buried them.
- **Coverage policy:** corpus ≤ 80 provisions → **grade-all** (every provision × every indicator;
  retrieval is a signal, not a gate — this is what protects non-English recall). Larger corpora →
  a shortlist of 20–40 per indicator with **per-law reserved slots**, so a short on-point act
  (My Health Records s77) is never crowded out by a 485-section act. 1,200 provisions ⇒ ~360 LLM
  calls, not 10,800.

**Mapping — LLM-based reasoning (not a black-box classifier):** each (provision, target) call
carries the target's legal test, scope, and **every sibling's** legal test; explicit steps —
operative rule → satisfies target? → better sibling? → relevant? Unsure ⇒ reject to the review
queue, never silently accepted or dropped.

**Anti-hallucination — the citation matches the source 100% by construction:**
1. The verbatim snippet is **copied from the fetched source text** — the LLM never writes it.
2. A **grounding check** confirms the snippet occurs in the source document.
3. A **topical guard** flags snippets with none of the pillar's concept vocabulary (score capped).
4. The **source URL** is the official portal page; the JSON keeps surrounding context
   (`raw_context_before/after`) for one-click human verification.
5. **Confidence gate:** < 0.85 → human review, < 0.60 → quarantined.

**Example input → output (real row):** `economy = Singapore, pillar = 6`

| Field | Value |
| :--- | :--- |
| Law Name | Personal Data Protection Act 2012 (Act 26 of 2012) |
| Indicator ID | **P6-I4** (conditional cross-border flow) |
| Article / Section | Section 26 |
| Verbatim Snippet | "An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act…" |
| Mapping Rationale | "Transfer is permitted subject to prescribed requirements → conditionally allowed, not banned." |
| Source URL | https://sso.agc.gov.sg/Act/PDPA2012 · Confidence 0.82 (review) |

> It maps to **P6-I4 (conditional)**, not P6-I1 (ban) — the sibling-aware prompt makes exactly the
> distinction a keyword classifier gets wrong. ‹FILL› optionally swap for a NEW-tagged row.

---

## Slide 9 — Evaluation Metrics / Performance

**What we measure (and current numbers):**

| Metric | How measured | Result |
| :--- | :--- | :--- |
| **OCR quality (CER)** | edit distance vs ground-truth sidecar on the bundled scanned PDF; sidecar-reading engines excluded (would score a circular 0%) | **1.11%** (PASS < 5%) |
| **Indicator-mapping correctness** | mappings checked against the official RDTII answer key (SG: PDPA→P7-I1, Cybersecurity Act→P7-I2, Companies Act §199→P6-I2, CPC→P7-I5) | ‹FILL› N correct / N checked |
| **Discovery precision** | share of surfaced laws in-force & on-topic (AU content lane re-verified against the register) | AU P6: 14 laws, **0 junk** |
| **Garbage-extraction guard** | AU SPA shell detected & suppressed instead of mapping nav chrome | **0 bogus provisions** |
| **Citation fidelity** | snippet-grounding check: snippet must occur in source | 100% verbatim by construction |
| **Coverage / no-blanks** | every indicator gets a row or an explicit "No evidence" placeholder | 9/9 indicators populated |
| **Wall-clock profile** | measured per stage on a live crawl (CPU-only) | extract 44% · embed 37% · LLM 14%; embed disk-cache ⇒ **16×** faster repeats |
| **Cost** | token-metered per grading call | ~$0.07/economy · $0 open-weight |
| **Multilingual robustness** | multilingual embeddings + grade-all ⇒ non-English recall doesn't depend on English reranking | MY bilingual handled |

**Honesty note (keep — judges reward transparency):** the LLM grader is stochastic, so borderline
*definitional* clauses can flip between runs; the review queue is the safety net, and a chosen run
is frozen via the result cache for a reproducible submission.

---

## Slide 10 — Demo / Preview

**Demo storyboard (screenshots or 60–90s screen recording):**
1. **Dashboard** — pick *Singapore · Pillar 6*, press Run (defaults are sane; engine choices live
   under Advanced settings). ‹FILL› screenshot of the sidebar.
2. **Live log** — watch discovery find laws on `sso.agc.gov.sg`, fetch + OCR, then map. ‹FILL›
   screenshot (`[discovery] … [ocr] … CER=1.11% PASS<5% … [done]`).
3. **Results** — per-indicator cards with verbatim snippet, confidence traffic-light, clickable
   source URL; low-confidence rows flagged for review. ‹FILL› screenshot.
4. **Output** — open `outputs/…csv` (13 columns) + the consolidated `VeriTrade_MASTER` sheet +
   the supplementary scored CSV. ‹FILL› screenshot.
5. **Scanned-PDF proof** — run the bundled image-only gazette with RapidOCR, show CER 1.11%.
6. **The trap, caught** — show the AU run: the SPA page a naive crawler would "read" vs the
   authorised compilation PDF VeriTrade actually extracts.

> Tip for the live demo: tick **"Fresh run"** (or clear `cache/_results/`) so judges see a genuine
> live crawl, not a cached replay.

---

## Slide 11 — Innovation & Competitive Advantage

**What sets VeriTrade apart (each point is a mechanism, not a slogan):**
- **Discovery by content and by the portal's own data — not a baked corpus.** The obligation-phrase
  lane finds laws by what their *clauses say* (that's how the Companies Act's record-storage clause
  surfaces for P6-I2); the MY adapter reads the catalogue the portal itself renders from. No seed
  URLs, no hardcoded law names — new economy = one portal domain + one entry strategy.
- **It survives the portals as they actually are.** Broken `$search` (AU), unindexed portal (MY),
  TLS-fingerprint WAFs, Angular shells serving no text, "secretly scanned" PDFs, bilingual
  catalogues — each has a specific, tested countermeasure. Most pipelines demo on clean HTML;
  ours demos on the real thing.
- **Verifiable by design.** 100%-verbatim snippets with character spans + grounding checks +
  official source URLs + a transparent 4-signal confidence + full JSON audit trail. A second
  reviewer can reproduce and check every row.
- **Legal reliability encoded.** Sibling-aware prompting implements the RDTII "distinguish-from"
  rules; the sibling *penalty* implements them again at retrieval; conservative defaults + a human
  review queue prevent confident-but-wrong mappings; repealed/bill hits are dropped against the
  official register.
- **Zone 3 scoring, polarity included.** Each measure gets the official 0/0.5/1 raw score — and
  the system correctly handles the *inverted* polarity of 7.1/7.2 (a strong horizontal framework
  scores 0 restrictiveness), with MIN roll-up for inverted indicators vs MAX otherwise. A detail
  most teams will miss.
- **No vendor lock-in, runs anywhere.** LLM and OCR swap via one config value (OpenRouter/
  Anthropic/OpenAI/Gemini/local Ollama/mock; MarkItDown/RapidOCR/Paddle/Tesseract/Azure). CPU-only;
  ~$0.07/economy; $0 open-weight; 3-tier caching makes repeat runs free and instant.

---

## Slide 12 — Scalability & Future Development

**Scaling out — what's already generic vs what each new economy needs:**
- **Already generic:** the framework (query lanes, dedup, version resolution, confidence, export),
  multilingual embeddings (Thai/Chinese/Russian covered), grade-all coverage, the indicator layer
  (data-driven — new pillars = new definitions, no pipeline changes).
- **Per-economy work (by design, pluggable):** one discovery entry strategy (like SG/AU/MY each
  got) + one extraction profile for the drafting convention ("Điều 5", "第五条", "มาตรา ๕") —
  the same adapter pattern already proven three times.
- **Planned upgrades:** multilingual cross-encoder (`BAAI/bge-reranker-v2-m3`, one config line);
  per-page scan detection for mixed text/scan gazettes; dual-engine translation cross-check with
  bilingual snippet tracking; scheduled re-crawls diffing cached results to flag amendments
  automatically (real-time monitoring).

**Value created:**
- **ESCAP** — faster, reproducible, auditable RDTII refreshes at a fraction of the manual cost.
- **Governments & businesses** — quicker access to authoritative, cited digital-trade rules;
  reduced compliance-research burden.
- **Researchers** — a transparent, swappable, open-source base to extend.

**Expected outcomes:** improved access to primary-source regulatory evidence · faster index updates ·
consistent cross-country coverage · lower cost and effort per economy.

---

## Slide 13 — References

**Legal data sources (official portals):**
- Singapore Statutes Online — https://sso.agc.gov.sg
- Federal Register of Legislation (Australia) + OData API — https://www.legislation.gov.au ·
  https://api.prod.legislation.gov.au
- Laws of Malaysia (AGC) — https://lom.agc.gov.my · Personal Data Protection Dept — https://pdp.gov.my
- UN ESCAP RDTII 2.1 Methodology & Round-1 Database (provided by organisers)

**AI models:**
- LLM: DeepSeek V4 Flash via OpenRouter (default; vendor-swappable)
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`

**Open-source libraries:** Scrapling · httpx · BeautifulSoup · MarkItDown · RapidOCR · PaddleOCR ·
pdfplumber · sentence-transformers · rank_bm25 · Streamlit · pydantic · pypdfium2

**Search:** Serper.dev (Google results API) · DuckDuckGo / Mojeek (keyless fallback)

**Repository:** github.com/ftulabs/law-v2.0 · License: Apache-2.0

---

### Appendix — Cost (measured, for the Q&A / cost-optimization question)

| Scope | LLM (deepseek-v4-flash) | Serper discovery | Total |
| :--- | :--- | :--- | :--- |
| Per grading call | ~$0.0002 | — | — |
| Per document (~64 calls) | ~$0.012 | discovery is per-run | ~$0.012 |
| Per economy, both pillars | ~$0.07 (~360 calls) | 90 (SG/AU) or 5 (MY) queries | — |
| **Full Round 1 (3 economies)** | ~$0.21 | 185 queries (within 2,500 free credits ⇒ $0) | **~$0.40 paid / ~$0.21 free-tier** |
| **Open-weight swap** (Ollama + Tesseract + DuckDuckGo) | $0.00 | $0.00 | **$0.00** |

Pricing: deepseek-v4-flash $0.09/$0.18 per 1M input/output tokens; Serper 1 credit/query, 2,500 free
then $1/1k. OCR, embeddings, retrieval run locally at $0. Caches make repeat runs free.

### Appendix — Likely judge questions, one-line answers

- *"How do you know your crawl isn't a baked corpus?"* — Every doc is tagged KNOWN/NEW; live mode
  never falls back to samples; the AU/MY adapters query the portal's live API/catalogue at run time.
- *"What if the portal changes?"* — Each portal-specific parser has a graceful fallback (title-year
  date, regex path, httpx) and failures surface as explicit discovery errors, never silent blanks.
- *"Why not fine-tune a classifier?"* — 9 indicators × few examples = no training set; the legal
  tests change with the methodology; prompted reasoning + answer-key validation is auditable.
- *"How do you handle a law in Malay/Thai/Chinese?"* — multilingual embeddings + grade-all (LLM
  grades every provision, retrieval is only a hint) + planned multilingual reranker for Finals.
