# Ledger — a research-to-software pipeline

**Date:** 2026-08-20 · **Status:** design, pre-implementation
**Home:** a new repo, seeded from `ftulabs/research_pipeline` · **First tenant:** this repo (VeriTrade)

> *Name is provisional.* "Ledger" encodes the invariant below: every artifact in a
> published package traces back to a recorded run. Swap it if something better lands.

---

## 1. The invariant

VeriTrade's core anti-hallucination rule is that law text, citations and URLs are
**carried from extraction, never generated** — the model grades evidence, it never authors
it. `confidence.snippet_grounding()` then checks that the cited snippet is *actually present*
in the source text before the mapping can be trusted.

Ledger applies exactly that rule one level up:

> **Every number, table and figure in a published artifact is carried from a recorded run,
> never typed by a human and never written by a model.** `ledger verify` re-derives each one
> from `runs/` and fails CI if any value in the paper has no backing record.

Same function, different domain. VeriTrade grounds legal snippets against source law; Ledger
grounds paper numbers against run records. That check is the product — everything else is
plumbing around it.

**Corollary — no agents author claims.** Ledger is a deterministic toolchain. LLMs may run
*inside* a tenant's experiments (VeriTrade's graders) but never in the path that produces a
number, a table, or a claim. This is what makes the reproducibility statement defensible.

---

## 2. Tenant model

A **tenant** is a research project. It stays in its own repo and declares itself to Ledger
through one manifest at its root. Ledger never vendors tenant code; it imports entry points.

```yaml
# law-v2.0/project.yaml — VeriTrade as tenant #1
name: veritrade
title: "RDTII-Bench: Autonomous Discovery and Indicator-Grounded Mapping"

code:
  repo: ftulabs/law-v2.0
  package: backend
  env: requirements.txt

tasks:                                  # what can be run and scored
  - id: t1_discovery
    entry: bench.tasks.discovery:run
    gold: data/ground_truth/gov_portals_p6_p7.csv
    metrics: [recall_at_k, precision]
  - id: t3_mapping
    entry: bench.tasks.mapping:run
    gold: bench/gold/mapping_pairs.jsonl
    metrics: [precision, recall, f1, kappa]

matrix:                                 # the experiment grid
  economy: [SG, AU, MY]
  pillar: [6, 7]
  llm: [deepseek-v4-flash, gpt-4o-mini, gemini-2.5-flash, qwen2.5-72b]
  crosscheck: [off, panel_3, panel_5]
  seed: [0, 1, 2, 3, 4]

product:                                # stage 8 reads only this block
  entry: backend.pipeline.orchestrator:run_pipeline
  request: backend.schemas:RunRequest
  result: backend.schemas:RunResult
  events: backend.schemas:RunEvent
  targets: [web, windows, macos, linux, ios, android]
  sidecar: true                         # bundle the engine for desktop

release:
  hf_dataset: ftulabs/rdtii-bench
  license: apache-2.0
```

The manifest is the only coupling. A second tenant — an OCR study, a retrieval paper — writes
its own and gets the same eight stages for free.

---

## 3. The eight stages

Each stage consumes typed artifacts and emits typed artifacts. Every one is independently
runnable (`ledger run`, `ledger figures`, …) so a broken stage never blocks the others.

| # | Stage | In | Out |
|---|---|---|---|
| **S1** | `spec` | `project.yaml` | Validated manifest, resolved entry points, env lock |
| **S2** | `run` | manifest + matrix | `runs/<run_id>.json` — canonical `RunRecord`, resumable |
| **S3** | `metrics` | `runs/` | `metrics.json` — aggregates, CIs, seed variance, significance |
| **S4** | `figures` | `metrics.json` | `tables/*.tex` + `figures/*.pdf`, deterministic |
| **S5** | `paper` | generated assets + prose | Compiled PDF, style-swappable (ICLR / NeurIPS / arXiv) |
| **S6** | `release` | metrics + data | HF dataset push, Zenodo DOI, arXiv tarball, BibTeX |
| **S7** | `web` | manifest + metrics + figures | Static project site |
| **S8** | `product` | `product:` block | API service, typed client, UI, Tauri shells, installers |

### S2 — the runner (generalised from this repo)

Today `benchmark.py` is hardwired to *model × benchmark* with an LLM judge. Generalise the
axis, keep everything that already works:

| Keep as-is | Generalise |
|---|---|
| Per-pair resume cache (`results/raw/*.json`) | `Task` protocol: `run(config) -> RunRecord`, not just "call model, judge output" |
| `--workers` intra-pair concurrency | Matrix from the manifest, arbitrary axes, not `models × benchmarks` |
| `--mock` deterministic dry run | Seeds as a first-class axis, with variance reported |
| Forced JSON schema on judge output | LLM-judge becomes *one* built-in task type among several |
| `--charts-only` re-render | `RunRecord` carries the provenance stamp (below) |

VeriTrade's grading-against-gold becomes a second built-in task type. The scoring philosophy
is unchanged: a failed call is recorded as a failure, never silently scored zero and averaged in.

### S8 — the product layer

The ambitious stage, and tractable only because it is **schema-driven codegen**, not bespoke
UI work. VeriTrade already exposes Pydantic models (`RunRequest`, `RunResult`,
`EvidenceMapping`), so:

```
Pydantic  →  JSON Schema  →  ├─ run-config form (fields, defaults, validation)
                             ├─ TypeScript types + typed API client
                             └─ results table columns + detail view
```

Generated: FastAPI job service (async jobs + SSE over the tenant's event type), OpenAPI 3.1
spec, TS client, UI shell with config form / live event stream / generic results table,
Tauri configs for five OS targets, PyInstaller sidecar spec, and the CI release matrix.

**Not generated, and honestly so:** the domain-specific results view. VeriTrade's confidence
traffic-light, evidence detail with verbatim snippet and OCR provenance, and the review queue
are its own design work. Ledger provides **slots** the tenant fills. Expect roughly 70% of the
app scaffolded, 30% bespoke — and the 30% is the part users actually judge.

---

## 4. The provenance spine

Every `RunRecord` carries:

```json
{
  "run_id": "…", "task": "t3_mapping", "config": {…},
  "provenance": {
    "code_commit": "d83d0d0", "config_hash": "…", "data_hash": "…",
    "env_hash": "…", "started_at": "…", "duration_s": 0.0
  },
  "result": {…}, "failures": [{"reason": "…", "config": {…}}]
}
```

`ledger verify` walks the compiled paper, resolves every `\num{}` / `\input{}` back through
`metrics.json` to the `runs/` that produced it, and exits non-zero on:

- a number in the PDF with no backing record;
- a record whose `code_commit` is not an ancestor of the tag being released;
- a stale figure — `metrics.json` newer than the `figures/` derived from it;
- a claim whose bound values no longer match the current metrics (below).

This runs in CI on every push touching `paper/`. **No unbacked number ships.**

### Claims registry

Kills the classic "abstract says 12%, Table 3 says 9%" bug:

```yaml
claims:
  - id: C1
    template: "Cross-model panels recover {d_f1} F1 points at {cost}% added cost."
    bind:
      d_f1:  cells[crosscheck=panel_3].f1 - cells[crosscheck=off].f1
      cost: (cells[crosscheck=panel_3].usd / cells[crosscheck=off].usd - 1) * 100
```

The paper writes `\claim{C1}`; LaTeX receives the substituted sentence. Re-run the
experiments and the prose updates or CI fails. Deterministic — no model in the loop.

---

## 5. Build order — harvest, don't speculate

**The rule: no stage is written before a tenant needs it.** A framework designed for N=1 fits
nothing. Every stage below is built *because* VeriTrade's paper requires it that week, and it
is written in the Ledger repo with VeriTrade as an external tenant from the first commit — the
seam gets forced early, when it is cheap.

**This does not delay the paper.** The work is the same work; only its address changes.

| When | VeriTrade needs | Ledger gains |
|---|---|---|
| S0 (Aug 20–25) | Bench schema, gold extraction | **S1 spec** + `RunRecord` schema + provenance stamp |
| S1 (Aug 26 – Sep 6) | The ablation sweep | **S2 run** (generalised) + **S3 metrics** with seed variance |
| S2 (Sep 7–17) | Tables, figures, the PDF | **S4 figures** + **S5 paper** + `verify` + claims registry |
| ★ (Sep 18/24) | Submission, HF push, website | **S6 release** + **S7 web** |
| S3–S4 (Sep 25 – Nov) | The apps | **S8 product**, proven against VeriTrade's own schemas |

Stage 8 lands exactly when the previous plan already scheduled the app work — so the pipeline
framing costs nothing in schedule and yields a reusable asset instead of one-off scripts.

**Generalise on the second tenant, not the first.** Until a second project runs through it,
treat every abstraction as provisional and resist parameterising anything VeriTrade hasn't
actually exercised.

---

## 6. Non-goals

- **Not an auto-scientist.** No agent forms hypotheses, designs experiments, or writes claims.
- **Not a workflow engine.** No DAG scheduler, no distributed execution. Stages are CLI
  commands with file inputs and outputs; a Makefile is the orchestrator.
- **Not a hosted service.** It runs locally and in CI.
- **Not a paper generator.** Humans write prose; Ledger guarantees the numbers inside it.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Abstraction built for N=1 | Nothing is generalised until a second tenant needs it; §5 build order enforces this |
| Factory work crowds out the paper | Every stage is scheduled against a paper deliverable it unblocks; if a stage slips, the tenant does it inline and Ledger harvests later |
| S8 promises more than codegen can deliver | Stated up front: ~70% scaffolded, 30% bespoke, and the bespoke part is the visible part |
| `verify` becomes CI friction | Starts advisory (warn), flips to blocking once the paper's assets are fully generated |
| Two repos drift | The manifest is the only contract; a tenant contract test runs in both CIs |

---

## 8. Open items

1. **Name.** "Ledger" is provisional and collides with fintech tooling.
2. **Create the repo** — `ftulabs/<name>`, seeded by lifting `src/eval_llm/` in as the S2/S3 core.
   This session could push only to `law-v2.0`, so the repo
   needs creating before any of it can be pushed.
3. **Does this repo become the tenant, get archived, or stay a standalone tool?** Its existing
   single-model CLI (`eval-llm`) has users; lifting the matrix runner out shouldn't break them.
4. **Licence.** This repo is MIT, VeriTrade is Apache-2.0. Pick one for Ledger.
