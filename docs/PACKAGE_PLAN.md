# VeriTrade — Full Package Plan

**Date:** 2026-08-20 · **Owner:** Team FTU · **Status:** proposed, awaiting go

Scope: turn VeriTrade from a hackathon submission into a complete research + software
package — a peer-reviewed paper, a public benchmark on HuggingFace, a project website,
and a cross-platform application (web, iOS, Android, Windows, macOS, Linux; x86-64 + ARM64).

---

## 0. Decisions already taken

| # | Decision | Consequence |
|---|---|---|
| D1 | **Desktop bundles a local engine from day one** | Offline / air-gapped runs. Costs per-arch PyInstaller builds and a model-download step. |
| D2 | **HuggingFace: open annotations + gated full corpus** | Public benchmark ships immediately; gated corpus is **blocked on a licence review** the team must run (see §6.2). |
| D3 | **Tauri 2 for desktop *and* mobile** | One Rust shell, one React UI, five OS targets. Accept thinner mobile plugin ecosystem. |
| D4 | **Target ICLR 2027** | Paper is the hard deadline and the critical path. Everything else schedules around it. |

> ⚠ **Deadline check needed.** ICLR's historical cadence puts the 2027 abstract deadline in
> **mid-to-late September 2026** and the full paper ~5 days later. That is **4–5 weeks from
> today**. This plan assumes abstract ≈ 18 Sept, paper ≈ 24 Sept. **Verify the real dates on
> the ICLR site before committing** — the whole schedule keys off them.

---

## 1. Deliverables

| ID | Deliverable | Definition of done |
|---|---|---|
| **D-1** | **RDTII-Bench** — public benchmark | 3 tasks (discovery, extraction, mapping), gold labels, splits, loader, leaderboard script |
| **D-2** | **Paper** (ICLR format + NeurIPS-format arXiv build) | Camera-ready-quality PDF, all numbers reproducible from `bench/` |
| **D-3** | **Project website** | Static site on GH Pages: abstract, method figure, interactive results, demo, BibTeX |
| **D-4** | **HF assets** | `rdtii-bench` (public), `rdtii-corpus` (gated), `veritrade-demo` Space, ONNX retriever models |
| **D-5** | **VeriTrade API** | Versioned FastAPI job service with streaming run events; runs identically hosted or on-device |
| **D-6** | **Web app** | React/TS SPA replacing Streamlit as the primary UI |
| **D-7** | **Desktop apps** | Signed installers: Windows `.msi`/`.exe`, macOS `.dmg` (notarized), Linux `.deb`/`.rpm`/`.AppImage` — x64 + ARM64, with bundled offline engine |
| **D-8** | **Mobile apps** | iOS (TestFlight → App Store), Android (Play internal → production) |

The existing Streamlit app (`frontend/app.py`) is **frozen**, not deleted — it is the artifact
the hackathon judges evaluated. It keeps working against the same backend.

---

## 2. Architecture

### 2.1 The one decision that makes local-first cheap

`backend/main.py` is already a FastAPI app over the same `run_pipeline()` the CLI and Streamlit
call. So the offline desktop engine is **not a second implementation** — it is the *same API
server*, started as a Tauri sidecar bound to `127.0.0.1` with a loopback token:

```
        ┌──────────── shared React UI (apps/ui) ────────────┐
        │  talks to ONE API contract, differing only in     │
        │  API_BASE + auth mode                             │
        └───┬───────────────┬───────────────┬───────────────┘
            │ web           │ desktop       │ mobile
            ▼               ▼               ▼
   https://api.…    http://127.0.0.1:PORT   https://api.…
   (hosted)         (Tauri sidecar:         (hosted only —
                     PyInstaller binary)     no Python on iOS/Android)
                            │
                            └── backend/ (unchanged pipeline)
```

**Mobile is server-only.** Python cannot ship inside an App Store binary, and the model +
OCR footprint is wrong for a phone regardless. State this plainly in the store listings.

### 2.2 Repository layout (monorepo in `law-v2.0`)

```
law-v2.0/
├── backend/            # unchanged pipeline core
├── frontend/           # FROZEN Streamlit app
├── apps/
│   ├── api/            # versioned HTTP service (jobs, SSE, tokens) over backend/
│   ├── ui/             # React + TS + Vite — the single UI for all 5 targets
│   ├── shell/          # Tauri 2: src-tauri/ + gen/android/ + gen/apple/
│   └── engine/         # PyInstaller spec + sidecar entrypoint
├── bench/              # RDTII-Bench construction, eval harness, leaderboard
├── paper/              # LaTeX (shared body, swappable ICLR/NeurIPS style)
├── web/                # project website
└── .github/workflows/  # CI + 6-way release matrix
```

`research_pipeline` stays a separate repo and becomes the **model-comparison engine** for the
paper: add an `rdtii` task type that grades against gold labels instead of LLM-as-judge, and it
produces the paper's cost/accuracy Pareto table directly.

### 2.3 Build target matrix

| Target | Runner | Engine | Notes |
|---|---|---|---|
| Web | `ubuntu-latest` | hosted | Vite static build → CDN |
| Windows x64 | `windows-latest` | bundled | NSIS `.exe` + `.msi`; EV cert |
| Windows ARM64 | `windows-11-arm` | bundled | verify runner availability |
| macOS ARM64 | `macos-14` | bundled | `.dmg`, hardened runtime, notarized |
| macOS x64 | `macos-13` | bundled | ship universal2 if PyInstaller cooperates |
| Linux x64 | `ubuntu-latest` | bundled | `.deb` + `.rpm` + `.AppImage` |
| Linux ARM64 | `ubuntu-24.04-arm` | bundled | also covers Jetson (existing `deploy/`) |
| iOS | `macos-14` | hosted | Xcode, provisioning, TestFlight |
| Android | `ubuntu-latest` | hosted | SDK/NDK, AAB to Play |

---

## 3. Workstream 1 — Research & benchmark (critical path)

### 3.1 RDTII-Bench

Gold sources already in-repo:
- `ESCAP-RDTII-2.1_ Round 1 Database.xlsx` / `data/sample_kit/RDTII_Round1_Database.csv` —
  2,079 rows, 12 pillars, 3 economies, each with Raw Score, Act, Coverage, Impact, Timeframe **and a reference URL**.
- `data/ground_truth/gov_portals_p6_p7.csv` — 72 curated P6/P7 rows with URLs and a
  `policy.description` field that maps cleanly onto the 9 indicators.

Scale-up path: ESCAP's *Digital Trade Regulatory Review 2025* covers **48 economies** under
RDTII 2.1. If per-economy indicator values are obtainable, gold grows to ~48 × 9 ≈ 430 cells —
turning a hackathon answer key into a genuine benchmark. **Investigate in Sprint 0.**

**Three tasks:**

| Task | Input | Output | Metric |
|---|---|---|---|
| **T1 Discovery** | (economy, pillar), no seed URLs | ranked law candidates | law-level recall@k, precision, portal-fidelity |
| **T2 Extraction** | scanned/text PDF | article-level text | CER, section-boundary F1 |
| **T3 Mapping** | (provision, indicator) | satisfies / not | precision, recall, F1, Cohen's κ vs human |

**Annotation drive (the real cost).** T3 needs human labels. Plan: sample ~2,000 (provision,
indicator) pairs stratified across confidence bands and indicators, double-annotate a 20%
overlap for κ, adjudicate disagreements. Two annotators × ~2 weeks. Write the guideline
document *before* annotating — it becomes a paper appendix.

**Splits:** dev = Singapore · test = Australia + Malaysia · held-out = finals economies.
**Contamination:** these laws are public web text and certainly in LLM pretraining. Address it
head-on in the paper; report the held-out finals set as the contamination-resistant slice.

### 3.2 Experiments

1. **End-to-end** — P/R/F1 vs answer key, per indicator × economy.
2. **Retrieval ablation** — BM25 / dense / +cross-encoder / RRF; recall@k; how much gold
   evidence the shortlist silently drops.
3. **Coverage-policy ablation** — grade-all vs shortlist; per-law reservation on/off (the
   documented ordering bug in `_diverse_shortlist` is a ready-made ablation).
4. **Stability under repetition** ⭐ — N=5 seeds per config. The codebase already documents a
   real flip-flop (*MHR s77 → P6-I2 satisfied on 1 of 3 attempts*). Quantifying instability in
   LLM legal grading, and showing the cross-model panel suppresses it, is the paper's
   sharpest empirical claim.
5. **Cross-model panel ablation** — off / 2-of-3 / 3-of-5; accuracy vs added cost.
6. **Model sweep** — 8–12 LLMs via `research_pipeline`; cost/accuracy Pareto; open-weight vs frontier.
7. **Confidence calibration** — reliability diagram + ECE. The repo currently states confidence
   is uncalibrated; *measuring* it is a contribution, and it validates or kills the 0.85/0.60 routing.
8. **OCR → downstream propagation** — inject graded character noise, measure mapping F1 decay.
   Answers "how good does OCR actually need to be?", which nobody in this space has published.
9. **Cost & latency** table per configuration.

### 3.3 Paper positioning (ICLR framing)

ICLR rewards benchmark + empirical insight over systems engineering. Lead with the findings,
not the architecture:

> LLM legal grading is unstable at the decision boundary; independent cross-model panels
> recover *X* F1 points at *Y*% added cost; retrieval shortlisting silently discards *Z*% of
> gold evidence; self-reported confidence is miscalibrated by ECE *E*.

The system is the *instrument* that produces those findings. Working title:
**"RDTII-Bench: Autonomous Discovery and Indicator-Grounded Mapping of Digital Trade Regulation."**

---

## 4. Workstream 2 — Paper & website

- `paper/` holds one LaTeX body with a swappable style file — `iclr2027_conference.sty` for
  submission, `neurips_2026.sty` for the arXiv/preprint build. Same `main.tex`, one flag.
- **Every number in the paper is generated by `bench/`** — no hand-copied figures. A
  `make paper` target regenerates all tables/plots from `results/`.
- **Double-blind conflict:** ICLR permits arXiv preprints but forbids active promotion during
  review, and the website + HF datasets carry the team name. Mitigation: prepare an
  **anonymous mirror** (anonymised repo + anonymous HF org) for the submission, keep the
  branded public versions dark until the abstract is in, then publish.
- **Website** (`web/`): static, GH Pages. Reuse the design tokens already defined in
  `frontend/theme.py` — single blue accent, Inter + IBM Plex Mono, light/dark parity — so the
  paper site and the app read as one product. Sections: teaser, abstract, method figure,
  interactive results table (filter by economy/indicator), embedded HF Space demo, BibTeX,
  links to code + data.

---

## 5. Workstream 3 — Platform

### 5.1 API hardening (`apps/api`) — unblocks every client

1. **Async jobs.** `POST /v1/runs` → `202 {run_id}`; `GET /v1/runs/{id}`; `DELETE` to cancel.
   A live crawl takes minutes — the current synchronous endpoint cannot serve a phone.
2. **Streaming events.** `orchestrator.run_pipeline(log=…)` already emits parseable prefixes
   (`[doc]`, `[result]`, `[ocr]`, `[timing]`, `[crosscheck]`) that the Streamlit app
   regex-parses today. **Promote these to a typed `RunEvent` schema** and stream over SSE.
   This kills the regex coupling and gives all clients live progress for free.
3. **Auth for non-cookie clients.** Extend `backend/auth/service.py` with bearer tokens /
   API keys; loopback mode for the sidecar.
4. CORS, per-key rate limits, idempotency keys, artifact download endpoints, OpenAPI 3.1
   spec → generated TypeScript client for the UI.

### 5.2 Shared UI (`apps/ui`)

React + TypeScript + Vite + TanStack Query. Screens: run setup (country/topic, advanced
settings collapsed), live run view (streamed events, documents-found panel, results-so-far),
results table with confidence traffic-light, evidence detail (verbatim snippet + source link +
OCR provenance), **review queue** (finally builds out `backend/review/workflow.py`), export.

Carry over the design constraints in `CLAUDE.md` §5 verbatim — plain language, progressive
disclosure, no metaphor jargon, WCAG-AA both themes. Run UI work through the `ui-ux-pro-max`
skill as that section requires. Responsive layout doubles as the mobile layout.

### 5.3 Offline engine (`apps/engine`)

The heavy lift. Naive PyInstaller bundle ≈ 1.2 GB (torch + transformers + onnxruntime +
playwright). Reduction plan:

- **Drop torch entirely.** Export `paraphrase-multilingual-MiniLM-L12-v2` and the cross-encoder
  to **ONNX** and run them on `onnxruntime` — already a dependency via RapidOCR. Removes
  torch + transformers (~600 MB). Publish the exports as an HF model repo (D-4). Must verify
  ranking parity against the torch path before switching.
- **Models download on first run** into the app data dir, checksum-verified (~120 MB int8).
- **Playwright is not bundled** — offline mode degrades to Scrapling/httpx; browser escalation
  is an optional download. Document the capability difference honestly in-app.
- Target: **≤ 300 MB installer**, ≤ 450 MB installed before models.

Sidecar lifecycle: Tauri spawns it on a free port with a random loopback token, health-checks,
and tears it down on exit. Same binary as the hosted API, one code path.

### 5.4 Mobile (`apps/shell` — Tauri 2)

Tauri 2 drives iOS and Android from the same `src-tauri`. Store-risk mitigation: a pure
webview wrapper invites an **App Store 4.2 "minimum functionality" rejection**. Ship real
native value: offline-cached past runs, share-sheet export of CSV/JSON, push notification when
a long run finishes, biometric unlock. Budget one rejection cycle into the schedule.

---

## 6. Workstream 4 — Distribution

### 6.1 CI/CD
Extend the existing `.github/workflows/`: build matrix over the nine targets in §2.3,
artifact upload per target, GitHub Release on tag, HF dataset push on `bench/` change,
GH Pages deploy on `web/` change.

### 6.2 HuggingFace
- `ftulabs/rdtii-bench` — **public**, CC-BY-4.0 annotations: gold mappings, citations, source
  URLs, content hashes, char offsets, short verbatim snippets (quotation), plus a fetch script
  that reconstructs the corpus locally. Full dataset card with the annotation guideline.
- `ftulabs/rdtii-corpus` — **gated**, full extracted texts, access on licence acknowledgement.
  🔴 **BLOCKED** on a licence review of Singapore SSO and Malaysia AGC terms of use.
  Australia's `legislation.gov.au` is CC-BY 4.0 and is clear. *This review is a team task, not
  an engineering one — start it in week 1 or the gated half slips.*
- `ftulabs/veritrade-demo` — Space running sample/mock mode (no keys, no cost).
- `ftulabs/veritrade-retriever-onnx` — the ONNX exports from §5.3.

### 6.3 Long-lead items — **start this week, they gate later sprints**
| Item | Lead time | Why now |
|---|---|---|
| Apple Developer Program (organisation) | 2–4 weeks (D-U-N-S verification) | Blocks all iOS work |
| Windows code-signing cert (EV/OV) | 1–3 weeks (identity validation) | Unsigned `.exe` triggers SmartScreen |
| Google Play Console | days | Cheap, just do it |
| SG/MY licence review | unknown | Gates D-4 gated corpus |
| Annotator recruitment | 1 week | Gates the entire paper |

---

## 7. Schedule

Assumes ICLR abstract ≈ 18 Sept, paper ≈ 24 Sept — **verify first**.

| Sprint | Dates | Research / paper | Software |
|---|---|---|---|
| **S0** | Aug 20–25 | Bench schema, gold extraction, annotation guideline, 48-economy feasibility check | Env setup, freeze API contract, ONNX retriever spike, monorepo scaffold. **Kick off all §6.3 long-lead items.** |
| **S1** | Aug 26 – Sep 6 | 🔴 **Experiments + annotation drive** — the critical path | API jobs + SSE + typed RunEvents; React UI scaffold |
| **S2** | Sep 7–17 | Paper writing; **results freeze Sep 12**; figures; website; anonymous mirrors | UI feature-complete against hosted API; Tauri desktop shells green on CI |
| **★** | Sep 18 / 24 | **ICLR abstract / full submission**; arXiv posting; publish public HF bench + website | — |
| **S3** | Sep 25 – Oct 15 | Rebuttal prep; extend bench to finals economies | Engine sidecar; 6-arch installers; signing + notarization |
| **S4** | Oct 16 – Nov 15 | Gated corpus once legal clears | Mobile builds, TestFlight, Play internal testing, store submissions |

**Parallelism:** research and software are genuinely independent through S1–S2 — the paper
needs only `bench/` + `backend/`, never the new UI. If people are scarce, **software slips,
the paper does not.**

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| ICLR deadline is ~4 weeks out | Rushed paper | Freeze results Sep 12; scope to Round-1 economies if the 48-economy gold doesn't materialise; fall back to arXiv-first + a later cycle |
| Annotation throughput | No T3 labels → no paper | Start recruiting in S0; pilot 100 pairs first to calibrate the guideline before scaling |
| ONNX ranking parity fails | Engine bundle stays ~1 GB | Fall back to torch-CPU + a "large download" first-run warning; ship anyway |
| App Store 4.2 rejection | Mobile slips weeks | Native features listed in §5.4; budget one rejection cycle |
| SG/MY licence review blocks corpus | Gated half slips | Public annotations + downloader stand alone; corpus is additive |
| Live portals change mid-experiment | Non-reproducible numbers | Snapshot every fetched document with content hashes at experiment start; publish hashes with the bench |
| Doing all four workstreams at once | Everything half-done | The paper is the only hard deadline; software ships continuously after |

---

## 9. Open items for the team

1. **Confirm the real ICLR 2027 dates.** Everything keys off them.
2. **Who annotates, and when can they start?** This is the single biggest schedule risk.
3. **Is the 48-economy RDTII 2.1 indicator data obtainable?** Decides whether this is a
   hackathon write-up or a benchmark paper.
4. **Author list and affiliations** for the paper.
5. **Domains** — `veritrade.ftu.fyi` already hosts the Streamlit instance. Website and API
   need their own hostnames.
6. **Budget sign-off** — Apple $99/yr, Play $25, EV cert ~$200–400/yr, experiment LLM spend
   (~$50–200 for the full sweep), hosting.

---

## 10. Amendment (2026-08-20) — this package is built by a pipeline, not by hand

The deliverables above are unchanged. What changes is **where the code lives**: rather than
writing one-off scripts for VeriTrade's paper, each stage is built in a new standalone repo
(working name **Ledger**) with VeriTrade as its **first tenant**, coupled through a single
`project.yaml` manifest at this repo's root.

Design spec: **`docs/PIPELINE_SPEC.md`** (mirrored here for durability; its home is
`ftulabs/research_pipeline`, which this session could not push to).

**Why it costs no schedule.** The work is the same work; only its address changes. Each Ledger
stage is built in the sprint where this plan already required its output:

| Sprint | This plan needs | Ledger gains |
|---|---|---|
| S0 | Bench schema, gold extraction | Manifest + `RunRecord` + provenance stamp |
| S1 | The ablation sweep | Generalised runner + metrics with seed variance |
| S2 | Tables, figures, the PDF | Figure/paper stages + `verify` + claims registry |
| ★ | Submission, HF push, website | Release + web stages |
| S3–S4 | The apps (§5) | Product stage — schema-driven API/UI/Tauri scaffolding |

**The invariant it enforces.** This codebase's anti-hallucination rule — law text and citations
are *carried from extraction, never generated*, then grounded against source text — is applied
one level up: every number in the paper is carried from a recorded run, and `ledger verify`
fails CI on any value in the PDF without a backing record. No agent authors a claim.

**What this changes in §3–§5 above:**
- `bench/` becomes a tenant task module referenced by the manifest, not a standalone harness.
- `paper/` gets generated-asset discipline: no hand-typed numbers, `\input{}` only.
- `apps/` is scaffolded from the Pydantic schemas in `backend/schemas.py` rather than
  hand-written — with the honest caveat that the confidence traffic-light, evidence detail and
  review queue remain bespoke (roughly 70% generated, 30% hand-built).

**Unchanged:** the paper is still the only hard deadline, the ICLR submission is still
RDTII-Bench (Ledger is internal tooling, not the contribution), and if a stage slips, VeriTrade
does that step inline and Ledger harvests it afterwards.
