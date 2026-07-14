# VeriTrade — Pitch Deck Content

> Content pack for the ESCAP/KMITL pitch-deck template (13 slides). Hand this whole file to
> Claude to design the deck. Every number here is measured from the real system — keep them.
> `‹FILL›` marks the only spots that need human input (names, screenshots, final metrics).

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

**One-liner:** VeriTrade is an end-to-end AI pipeline that, given only an **economy** and a
**regulatory pillar**, autonomously discovers the relevant laws on official government portals,
extracts article-level text (including scanned PDFs), and maps each provision to the exact RDTII
indicator — with a verbatim citation, a confidence score, and a full audit trail.

**Four points (use as four columns/icons):**
1. **Problem** — Compiling the RDTII index is manual, slow, and hard to reproduce: analysts hunt
   across dozens of government portals, in multiple languages and file formats, then hand-map
   clauses to indicators.
2. **Solution** — Two automated tasks: (1) live discovery + extraction, (2) LLM mapping to
   indicators with verbatim evidence. Zero seed URLs, zero hardcoded law names.
3. **Core tech** — Bot-resistant crawling (Scrapling), OCR (MarkItDown/RapidOCR, CER 1.11%),
   hybrid RAG (BM25 + multilingual embeddings + cross-encoder), vendor-agnostic LLM mapping.
4. **Fit for RDTII P6 & P7** — Purpose-built for the 9 mandatory indicators (P6-I1…I4 cross-border
   data; P7-I1…I5 domestic data protection), outputs the exact 13-column submission template.

**Headline metrics (stat row):** 3 economies · 9 indicators · **CER 1.11%** on scanned PDFs ·
**~$0.07 per economy** in LLM cost · **$0.00** on an open-weight stack.

---

## Slide 3 — Problem Statement

**The regulatory challenge:** The UN RDTII index scores every economy on dozens of digital-trade
indicators. Building it means a human researcher must, for each (economy, indicator), *find* the
right statute, *read* the operative clause, *interpret* whether it satisfies the indicator, and
*cite* it precisely. Today this is manual and does not scale to 40+ economies on a regular refresh.

**Why digital-trade law is hard to find, interpret, compare and verify:**
- **Scattered & unindexed.** Each economy has its own portal with its own search (SG's is
  token/JS-gated, MY's `lom.agc.gov.my` is barely indexed by Google, AU's is a JS single-page app).
  No common API.
- **Bot-protected.** Portals apply WAF/TLS fingerprinting that blocks naïve crawlers (HTTP 403).
- **Mixed formats.** HTML, text PDFs, and **scanned/image-only PDFs** (older gazettes) side by side.
- **Multilingual.** Malaysia publishes bilingually (Malay authoritative, English reference);
  finals add Thai, Chinese, Russian, Lao.
- **Buried across many acts.** One indicator (e.g. P7-I5 government access) lives in criminal
  procedure, telecom, and national-security laws — not just the privacy statute.
- **Verification burden.** A citation is only trustworthy if the quoted text truly appears in the
  official source — the core anti-hallucination requirement.

**Impact:** slow index refreshes, inconsistent coverage, and results that are hard for a second
reviewer to reproduce.

---

## Slide 4 — Objective of the Project

**Goal:** Automate the professional legal researcher's workflow end-to-end, reproducibly, on a
standard CPU, with no vendor lock-in.

**The system is designed to:**
1. **Discover** — autonomously locate relevant primary legislation on official portals, live, with
   no seed URLs and no hardcoded law names (generalises to any economy by adding its portal domain).
2. **Extract** — download and parse article-level text from HTML, text PDFs, and scanned PDFs
   (real raster OCR with a measured Character Error Rate < 5%).
3. **Map** — assign each provision to the correct RDTII indicator (P6-I1…I4 / P7-I1…I5) using
   LLM legal reasoning that sees every sibling indicator to avoid confusion.
4. **Verify & cite** — attach a 100%-verbatim snippet, an article-level citation, a source URL,
   and a confidence score; route low-confidence rows to human review.
5. **Deliver** — output the exact official 13-column CSV + a machine-auditable JSON, consolidated
   into one master submission sheet across all economies and pillars.

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
│  Discovery (no seed URLs)          Fetch (bot-resistant)                  │
│   • SG → web search, portal-scoped   • Scrapling (real-browser TLS) →     │
│   • AU → OData API + full-text lane    httpx fallback                     │
│   • MY → portal acts catalogue       • polite per-host delay              │
│         + sectoral Codes of Practice • 3-tier cache (fetch/embed/result)  │
└──────────────────────────────────────────────────────────────────────────┘
        │  raw documents: HTML · text PDF · scanned PDF
        ▼
┌─────────────────────── ZONE 2 · EXTRACT & MAP ───────────────────────────┐
│  Extract                            Retrieve (hybrid RAG)                 │
│   • MarkItDown (text-layer)          • BM25 (lexical)                     │
│   • RapidOCR/PaddleOCR (scanned,     • multilingual MiniLM (dense)        │
│     measured CER)                    • cross-encoder rerank               │
│   • article/§ chunking, verbatim                                         │
│                                     Map (LLM reasoning)                   │
│                                      • grades each (provision×indicator)  │
│                                      • sees all sibling indicators        │
│                                      • 4-signal confidence score          │
└──────────────────────────────────────────────────────────────────────────┘
        │  mappings + verbatim snippets + confidence
        ▼
   Confidence routing:  ≥0.85 auto-accept · 0.60–0.85 review · <0.60 quarantine
        │
        ▼
   OUTPUT:  CSV (13 cols) · JSON (audit trail) · Master sheet · SQLite store
```

**Caption:** Two execution paths share identical extraction→mapping→export code — a live path
(scored) and an offline sample path (reproducible fallback) — so a sample run is an honest preview
of the live run.

---

## Slide 6 — Technology Solution / Innovative Feature

**Core technologies (icon + one line each):**
- **Autonomous discovery** — multi-strategy per portal: keyless/keyed web search (DuckDuckGo →
  Serper), official OData API (AU), and the portal's own acts catalogue (MY). No law names hardcoded.
- **Bot-resistant fetching** — Scrapling's real-browser TLS/JA3 impersonation clears WAFs that
  403 a plain crawler; escalates to a stealth browser for JS-gated pages.
- **OCR** — MarkItDown for text-layer PDFs; RapidOCR/PaddleOCR for scanned PDFs; measured
  Character Error Rate (**1.11%** on the bundled gazette scan, well under the 5% bar).
- **Hybrid RAG** — BM25 (lexical) + `paraphrase-multilingual-MiniLM-L12-v2` (dense, covers Malay/
  Thai/Chinese) + `ms-marco-MiniLM` cross-encoder rerank.
- **LLM legal reasoning** — the model grades one (provision, indicator) pair at a time and is shown
  every sibling indicator's legal test, so it distinguishes look-alikes (ban vs conditional flow,
  framework vs cybersecurity).
- **Confidence + human-in-the-loop** — a 4-signal score routes each row to auto-accept / review /
  quarantine.

**Innovative / differentiating features:**
1. **Content-based discovery, not name-matching** — a full-text "obligation-phrase" lane finds
   laws by *what their clauses say* (e.g. surfaces AU's Consumer Data Right Rules and Digital ID
   Rules that no title match would find), then verifies each hit as in-force via the official API.
2. **100%-verbatim evidence** — the snippet is copied from the source text, never generated by the
   LLM; a grounding check confirms it appears in the fetched document.
3. **Grade-all coverage** — for small corpora every provision is graded against every indicator, so
   retrieval ranking is a signal, not a gate (protects non-English recall).
4. **Reproducibility** — a 3-tier cache (fetched docs / embeddings / full results) makes a chosen
   run replay identically for judging.

**Tech stack & licensing compliance (all permissive — Apache-2.0 project):**

| Layer | Library | License |
| :--- | :--- | :--- |
| Crawl / fetch | Scrapling, httpx, BeautifulSoup | BSD / BSD / MIT |
| OCR / extract | MarkItDown, RapidOCR, PaddleOCR, pypdfium2 | MIT / Apache-2.0 / Apache-2.0 |
| Retrieval | sentence-transformers, rank_bm25 | Apache-2.0 / Apache-2.0 |
| App / core | Streamlit, pydantic, SQLite | Apache-2.0 / MIT / public domain |
| LLM (default) | deepseek-v4-flash via OpenRouter (swappable) | API |

> All dependencies are permissive (MIT/Apache/BSD); the project is Apache-2.0 — compliant with the
> hackathon's open-source requirement. Verify exact versions against `requirements.txt`.

---

## Slide 7 — Backend Logic (1 of 2): Discover → Extract → Retrieve

**Step-by-step workflow:**
1. **Discover** — build indicator-derived queries (concept phrases + short title fragments, all
   country-agnostic — never a specific law title). Fire them at the economy's portal(s); dedup
   candidate laws; drop repealed/bill/non-law hits (AU verified in-force against the OData API).
2. **Fetch** — Scrapling downloads each law's body (real-browser fingerprint), httpx as fallback;
   content-addressed cache dedups identical files; a landing page that embeds a PDF viewer is
   resolved to the actual PDF.
3. **Extract** — detect text-layer vs scanned; MarkItDown reads text PDFs, RapidOCR/PaddleOCR OCRs
   scans (CER measured); country-specific structural parsing splits the text into **verbatim
   article/section chunks** (SG/MY numbered form, AU font-marked headings).

**Identifying the relevant sections — chunking & retrieval:**
- **Chunking:** article/section level (one provision = one chunk), preserving the exact source text.
- **Retrieval: hybrid.** BM25 gives lexical recall; a multilingual bi-encoder gives semantic recall;
  a cross-encoder reranks for precision. Scores are fused; the top provisions per indicator form a
  shortlist. For small corpora (≤ 80 provisions) **every** provision is graded — retrieval is a
  signal, not a filter.
- **Complex legal language:** the LLM is prompted to first state the *operative rule* in one
  sentence (ignoring definitions/recitals), then test it against the indicator — so a defining
  clause isn't mistaken for an operative one.

---

## Slide 8 — Backend Logic (2 of 2): Map → Verify (anti-hallucination) + Example

**Mapping to RDTII indicators — LLM-based reasoning (not a black-box classifier):**
- For each (provision, target indicator) pair, the model receives the indicator's **legal test**,
  its **scope**, and **every sibling indicator's** legal test, then decides in explicit steps:
  operative rule → does it satisfy the target's test? → is a sibling a better fit? → relevant?
- **Edge cases / ambiguity:** a conservative default (unsure ⇒ reject) favours a precise miss over
  a wrong over-assign; genuinely borderline rows are surfaced to the **review** queue rather than
  silently accepted or dropped.

**How the citation is guaranteed to match the source 100% (anti-hallucination):**
1. The **verbatim snippet is copied from the fetched source text** — the LLM never writes it.
2. A **grounding check** confirms the snippet actually occurs in the source document.
3. A **topical guard** flags a snippet that contains none of the pillar's concept vocabulary.
4. The **source URL** points to the law on the official portal; the JSON keeps the surrounding
   context (`raw_context_before/after`) for one-click human verification.
5. Every row carries a **confidence score**; < 0.85 → human review, < 0.60 → quarantined.

**Example input → output (use a real, clean row):**

*Input:* `economy = Singapore, pillar = 6`

*Output (one CSV row):*
| Field | Value |
| :--- | :--- |
| Economy | Singapore |
| Law Name | Personal Data Protection Act 2012 |
| Law Number / Ref | Act 26 of 2012 |
| Indicator ID | **P6-I4** (conditional cross-border flow) |
| Article / Section | Section 26 |
| Verbatim Snippet | "An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act…" |
| Mapping Rationale | "This Section permits cross-border transfer subject to prescribed protection requirements. Maps to P6-I4 because transfer is conditionally allowed, not banned." |
| Source URL | https://sso.agc.gov.sg/Act/PDPA2012 |
| Discovery Tag | KNOWN |
| Confidence | 0.82 |

> Note it maps to **P6-I4 (conditional)**, not P6-I1 (ban) — the sibling-aware prompt makes exactly
> this distinction. ‹FILL› optionally swap for a NEW-tagged row to showcase autonomous discovery.

---

## Slide 9 — Evaluation Metrics / Performance

**What we measure (and current numbers):**

| Metric | How measured | Result |
| :--- | :--- | :--- |
| **OCR quality (CER)** | edit distance vs ground-truth sidecar on the bundled scanned PDF | **1.11%** (PASS < 5%) |
| **Indicator-mapping correctness** | mappings checked against the official RDTII answer key (e.g. SG: PDPA→P7-I1, Cybersecurity Act→P7-I2, Companies Act §199→P6-I2, Criminal Procedure Code→P7-I5) | ‹FILL› report N correct / N checked |
| **Discovery precision** | share of surfaced laws that are in-force & on-topic (AU content lane verified in-force via OData) | AU P6: 14 laws, 0 junk after in-force filter |
| **Citation fidelity** | snippet-grounding check: snippet must occur in source | 100% verbatim by construction |
| **Coverage / no-blanks** | every indicator gets a row or an explicit "No evidence" placeholder | 9/9 indicators always populated |
| **Confidence routing** | auto ≥0.85 / review 0.60–0.85 / quarantine <0.60 | distribution reported per run |
| **Response time** | wall-clock per run (CPU-only) | ‹FILL› e.g. ~X min/economy live; repeat runs ~instant (cache) |
| **Multilingual robustness** | multilingual embedding + grade-all so non-English recall doesn't depend on English reranking | qualitative (MY bilingual handled) |

**Honesty note (keep — judges reward transparency):** the LLM grader is stochastic, so borderline
*definitional* clauses can flip between runs; the review queue is the safety net, and a chosen run
is frozen via the result cache for a reproducible submission.

---

## Slide 10 — Demo / Preview

**Demo storyboard (screenshots or 60–90s screen recording):**
1. **Dashboard** — pick *Singapore · Pillar 6*, choose LLM (deepseek) + OCR (MarkItDown), press Run.
   ‹FILL› screenshot of the sidebar.
2. **Live log** — watch discovery find laws on `sso.agc.gov.sg`, fetch + OCR, then map. ‹FILL›
   screenshot of the running log (`[discovery] … [ocr] … CER=1.11% PASS<5% … [done]`).
3. **Results dossier** — per-indicator cards with verbatim snippet, confidence traffic-light, and a
   clickable source URL; low-confidence rows flagged for review. ‹FILL› screenshot.
4. **Output** — open `outputs/…csv` (13 columns) + the consolidated `VeriTrade_MASTER` sheet.
   ‹FILL› screenshot of the CSV.
5. **Scanned-PDF proof** — run the bundled image-only gazette with RapidOCR, show CER 1.11%.

> Tip for the live demo: tick **"Fresh run"** (or clear `cache/_results/`) so judges see a genuine
> live crawl, not a cached replay.

---

## Slide 11 — Innovation & Competitive Advantage

**What sets VeriTrade apart:**
- **Content-based discovery, not a baked corpus.** It finds laws by what their *clauses say* and by
  official APIs/catalogues — no seed URLs, no hardcoded law names — so it generalises to new
  economies by adding one portal domain. (Rubric explicitly forbids a baked corpus.)
- **Verifiable by design.** 100%-verbatim snippets + grounding checks + source URLs + confidence +
  a full JSON audit trail. A second reviewer can reproduce and trust every row.
- **Legal reliability.** Sibling-aware prompting encodes the RDTII "distinguish-from" rules; a
  conservative default and a human-review queue prevent confident-but-wrong mappings; repealed/bill
  hits are dropped against the official register.
- **No vendor lock-in.** LLM and OCR are swappable via one config value — OpenRouter/Anthropic/
  OpenAI/Gemini/**local Ollama**/mock; MarkItDown/RapidOCR/Paddle/Tesseract/Azure.
- **Runs anywhere, cheaply.** CPU-only; **~$0.07/economy** on the default paid stack, **$0.00** on
  an open-weight stack; 3-tier caching makes repeat runs free and instant.
- **Built for the end user.** A plain-language dashboard for non-technical policy reviewers +
  machine-readable JSON for technical validators — "judges are both types."

---

## Slide 12 — Scalability & Future Development

**Scaling out:**
- **More economies** — add a portal domain to `OFFICIAL_PORTAL`; discovery generalises. Finals
  targets (Thailand, China, India, Indonesia, Russia, Lao, Mongolia, Timor-Leste) plug in the same way.
- **More languages** — the embedding model is already multilingual; swap the cross-encoder to a
  multilingual reranker (`BAAI/bge-reranker-v2-m3`) and add a dual-engine translation cross-check
  (machine translation × LLM) with bilingual snippet tracking for non-English statutes.
- **More domains** — the indicator layer is data-driven; add other RDTII pillars by defining their
  indicators (legal test + query terms), no pipeline changes.
- **Real-time monitoring** — scheduled re-crawls diff against cached results to flag amended/new
  laws automatically.

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
sentence-transformers · rank_bm25 · Streamlit · pydantic · pypdfium2

**Search:** Serper.dev (Google results API) · DuckDuckGo / Mojeek (keyless fallback)

**Repository:** ‹FILL› github.com/ftulabs/law-v2.0 · License: Apache-2.0

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
