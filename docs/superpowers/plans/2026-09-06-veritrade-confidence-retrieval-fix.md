# VeriTrade Confidence & Retrieval Fix — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confidence discrimination failure (weighted sum never rejects) and retrieval precision collapse (too many low-relevance provisions graded) that caused 2.9x-11.8x mapping explosion with auto-accept dropping from 15-43% → 5-37% across all 6 economies when scaling from July 3-economy live crawl to August 6-economy live crawl.

**Architecture:** The pipeline has 4 stages: Discovery → Fetch → Extraction → Retrieval/Mapping. The bugs are concentrated in (1) Retrieval: global `retrieve_max_top_k=450` grades too many provisions per indicator for AU/MY/IN; (2) Confidence: 4-signal weighted sum floor ~0.71 vs 0.60 threshold means nothing rejected by weighted sum — only hard caps create rejections; (3) Grader: prompts don't discriminate adjacent indicators (P6-I1 vs P6-I4, P7-I1 vs P7-I2) and cross-check voting was reverted due to shared blind spots. Fix each subsystem with indicator-specific thresholds, per-economy retrieval budgets, and strengthened prompt gates.

**Tech Stack:** Python 3.11+, rank_bm25, sentence-transformers, OpenAI-compatible LLM providers (local vLLM/llama.cpp, OpenRouter), SQLite audit store, Streamlit dashboard

**Spec:** 
- CLAUDE.md §3-4 (architecture, known gaps)
- CLAUDE.md §7 (multilingual retrieval strategy)
- CLAUDE.md §9 (judging criteria checklist)
- PROJECT_STATE.md §5 (recent milestones: confidence never rejected, acceptance concentrates in uncheckable indicators)

## Global Constraints

- **No widening `retrieve_max_top_k`** — user explicitly rejected this approach
- **Indicator-specific thresholds** — confidence gates must be per-indicator (P6-I1/P6-I4/P7-I4 binary, P7-I5/P7-I1 broad)
- **Per-economy retrieval budgets** — AU needs 300-450, SG needs 40, IN needs section-unit capping
- **Real LLM enforcement** — mock grader must not run in production (`!use_samples`)
- **Backwards compatibility** — sample mode (offline, deterministic) must remain unchanged
- **No hardcoded law names** — discovery logic must not hardcode economy/law names
- **CER < 5%** — scanned PDF quality threshold must be maintained
- **Output format** — CSV must match official template exactly (14 columns + 2 translation)

---

## File Map

| Subsystem | Files | Responsibility |
|-----------|-------|----------------|
| **Confidence** | `backend/pipeline/confidence.py` | 4-signal scoring, routing caps, topical guard |
| **Retrieval** | `backend/pipeline/retrieval.py` | BM25 + dense + cross-encoder ranking, per-economy budget |
| **Retrieval Budget** | `backend/pipeline/retrieval_budget.py` | Per-economy shortlist sizing |
| **Mapping** | `backend/pipeline/mapping.py` | SYSTEM prompt, sibling disambiguation, cross-check |
| **Indicators** | `backend/rdtii/indicators.py` | Legal test, query_terms, scope, distinction rules |
| **Orchestrator** | `backend/pipeline/orchestrator.py` | Stage wiring, provider resolution, real-LLM enforcement |
| **Config** | `backend/config.py` | All tunable parameters (confidence, retrieval, budget) |
| **Fetch** | `backend/pipeline/fetch.py` | MY robots.txt 500 carve-out, CN resilience |
| **Tests** | `tests/test_confidence.py`, `tests/test_retrieval.py`, `tests/test_mapping.py` | Unit + integration tests |

---

## Phase Breakdown

| Phase | Focus | Target |
|-------|-------|--------|
| **P0** | Confidence Discrimination | Weighted sum produces < 0.60 for bad mappings; indicator-specific gates |
| **P1** | Retrieval Precision | Per-indicator budgets, amending filter, IN section-unit fix |
| **P2** | Grader Discrimination | Strengthened prompts, indicator exclusions, cross-check for local |
| **P3** | Pipeline Hardening | MY/CN fixes, real-LLM enforcement, production guards |

---

## Measured Baseline (2026-09-06) — supersedes the P0 premise above

Measured on the 457 graded mappings in `outputs/rt_check/*.json` (SG/AU/MY/CN/IN/MN, 2026-08-25),
and against `data/ground_truth/rdtii_reference_p67.csv` joined on (economy, law name, indicator).
Reproduce with `python -m backend.eval.confidence_eval` (built in Task 1 of the P0 plan).

**The confidence score does not discriminate at all. AUC = 0.458** — below chance, i.e. a mapping
that matches the judges' answer key scores marginally *lower* (mean 0.781, n=133) than one that
does not (mean 0.793, n=311). This is not a weak signal needing re-weighting; it carries no
information about correctness.

Why, from the same data:

| Signal | Measured distribution (N=457) | Effective role |
|---|---|---|
| `snippet_grounding` | 444x **1.0**, 13x 0.0 (the 13 are no-evidence rows) | constant +0.20 |
| `scope_alignment` | **1.0 on 422 (92.3%)** | near-constant +0.15 |
| `retrieval_score` | range **0.274-1.209** (CN exceeds 1.0), median 0.425, only 2.9% >= 0.85 | not on a 0-1 scale; contributes ~0.106 +/- 0.03 |
| `legal_match` | 87% of mass at {0.7: 160, 0.9: 121, 1.0: 114} | the only live term |

Consequences, all verified rather than inferred:

- `final ~= 0.456 + 0.40 * legal_match`. The floor for anything passing the relevance gate is
  **0.63**, so the entire 0-0.60 quarantine band is unreachable by the weighted sum.
- **All 21 quarantines across all six economies are cap-driven; zero came from the weighted sum.**
- **73% of auto-accepts (81/111) are simply `legal_match == 1.0`.** Routing is a relabelling of the
  grader's own self-report.
- `legal_match == 0.7` alone produces 148 of the 160 pending rows — the entire review backlog.
- `retrieval_score` scales differ per economy (AU p90 = 0.501 vs CN p90 = 0.988), so the same
  confidence number means different things in different economies.

**Two consequences for the plan.** (1) P0.1 as written ("redesign weights") cannot work: three of
the four terms are constants, and re-weighting constants changes nothing. P0 is re-scoped to
*build a discriminating signal*. (2) The Phase-0 target below (`auto% > 25`, `pend% < 60`) is a
symptom quota and must not be the acceptance gate — it can be met by moving thresholds without
improving a single mapping. **The P0 acceptance gate is AUC against the answer key.**

Label-noise caveat, stated so it is not rediscovered: NOT-IN-KEY is not a pure false-positive set.
The key is at law+indicator granularity and 10 of the 37 laws it cites are outside our catalogue
(CLAUDE.md Sec.4), so some not-in-key rows are correct-but-unlisted. AUC 0.458 is therefore a
noisy-label estimate — but a real signal would show through partial label noise at n=133/311.

**Detailed P0 plan:** `docs/superpowers/plans/2026-09-06-p0-confidence-discrimination.md`

---

### P0: Confidence Discrimination (Week 1)

**Goal (revised 2026-09-06):** Confidence must discriminate correct from incorrect mappings — AUC vs the answer key from **0.458 to >= 0.70**. auto%/pend% are reported as secondary symptom metrics, never as the gate.

| Task | Files | Deliverable |
|------|-------|-------------|
| P0.1 | `backend/eval/confidence_eval.py` | AUC harness vs answer key — the gate every later task is measured by |
| P0.1b | `retrieval_norm.py`, `mapping.py` | Rank-normalise `retrieval_score` per (run, indicator) — it is not 0-1 today |
| P0.2 | `confidence.py`, `indicators.py` | Add binary acceptance gates for checkable indicators (P6-I1, P6-I4, P7-I4) |
| P0.3 | `confidence.py`, `mapping.py` | `snippet_grounding` is self-certifying (source_texts falls back to the snippet itself) — make it a gate, not a term |
| P0.3b | `snippet_quality.py` | New live signal: reject table-of-contents/outline snippets (AU "Simplified outline" auto-accepted at 0.916) |
| P0.4 | `confidence.py`, `rdtii/query_terms_i18n.py` | Non-Latin topical guard using native concept terms |
| P0.5 | `tests/test_confidence.py` | Unit tests for all new gates |

---

### P1: Retrieval Precision (Week 2)

**Goal:** AU/MY/IN graded provisions per indicator reduced to budget; amending instruments filtered before grading

| Task | Files | Deliverable |
|------|-------|-------------|
| P1.1 | `config.py`, `retrieval_budget.py`, `orchestrator.py` | Per-indicator `retrieve_max_top_k` from budget file |
| P1.2 | `orchestrator.py`, `discovery.py` | Filter amending instruments BEFORE retrieval (AU 53% → <10%) |
| P1.3 | `discovery.py`, `config.py` | IN section-unit budget: cap at 22 laws, not sections |
| P1.3b | `retrieval.py` | Add BM25 minimum score floor (e.g., 0.1) to skip noise |
| P1.4 | `tests/test_retrieval.py` | Verify per-economy recall at budget matches targets |

---

### P2: Grader Discrimination (Week 3)

**Goal:** Adjacent indicators (P6-I1/P6-I4, P7-I1/P7-I2) separated; cross-check for local LLM

| Task | Files | Deliverable |
|------|-------|-------------|
| P2.1 | `mapping.py` SYSTEM prompt | Explicit "Distinguish from" rules for each adjacent pair |
| P2.2 | `indicators.py` | Add `excludes` field per indicator (sibling exclusion list) |
| P2.3 | `mapping.py` | Enable cross-check panel for local LLM (2-model) |
| P2.4 | `tests/test_mapping.py` | Adjacency confusion test matrix |

---

### P3: Pipeline Hardening (Week 4)

**Goal:** MY AGC PDFs fetched, CN principal statutes resilient, mock grader blocked in production

| Task | Files | Deliverable |
|------|-------|-------------|
| P3.1 | `pipeline/robots.py` | MY robots.txt 500 → treat as allowable (RFC 9309) |
| P3.2 | `discovery.py`, `fetch.py` | CN `cac.gov.cn` mirrors + `flk.npc.gov.cn` browser lane |
| P3.3 | `orchestrator.py` | Raise if `llm.name=="mock"` and `!use_samples` |
| P3.4 | `llm_factory.py` | Mock only available when `LLM_PROVIDER=mock` explicit |

---

## Execution Order

```
Week 1: P0.1 → P0.2 → P0.3 → P0.4 → P0.5
Week 2: P1.1 → P1.2 → P1.3 → P1.3b → P1.4
Week 3: P2.1 → P2.2 → P2.3 → P2.4
Week 4: P3.1 → P3.2 → P3.3 → P3.4
```

## Validation Criteria (After Each Phase)

```bash
# Run after each phase - must pass before next phase
python -c "
from backend.pipeline.orchestrator import run_pipeline
for econ in ['SG', 'AU', 'MY', 'CN', 'IN', 'MN']:
    r = run_pipeline(econ, [6,7], use_samples=False, llm_provider='local')
    auto = sum(1 for m in r.mappings if m.review_status == 'auto_accepted')
    pend = sum(1 for m in r.mappings if m.review_status == 'pending_review')
    quar = sum(1 for m in r.mappings if m.review_status == 'quarantined')
    total = len(r.mappings)
    print(f'{econ}: total={total} auto%={auto/total*100:.1f}% pend%={pend/total*100:.1f}% quar%={quar/total*100:.1f}%')
# Phase 0 GATE: python -m backend.eval.confidence_eval  ->  AUC >= 0.70
# Phase 0 secondary (symptom only): auto% > 25%, pend% < 60%, total < 500
# Phase 1 target: AU graded/indicator < 450, IN laws <= 22
# Phase 2 target: P6-I1 vs P6-I4 confusion < 5%, P7-I1 vs P7-I2 < 5%
"
```

---

## Spec Coverage Check

| CLAUDE.md Requirement | Phase |
|----------------------|-------|
| Zone 1 mandatory: autonomous discovery | P1.2, P3.1, P3.2 |
| Zone 2 mandatory: OCR + extraction | (unchanged) |
| Both Pillars 6 & 7 mandatory | P0, P2 cover all 9 indicators |
| Output format 14+2 columns | (unchanged) |
| Indicators mapped correctly | P0, P2 |
| Sample run reproducible < 10 min | (unchanged) |
| Live run tolerates portal downtime | P3.1, P3.2 |
| CER measured and reported | (unchanged) |
| Verbatim snippets exact | P0.3 |
| Article-level citations | (unchanged) |
| No hardcoded economy/law names | P1.3, P3 |
| Provider abstraction works | P2.3, P3.3 |
| Audit trail (SQLite, JSON) | (unchanged) |
| Tests pass locally | P0.5, P1.4, P2.4 |