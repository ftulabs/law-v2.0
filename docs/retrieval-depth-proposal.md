# Proposal: recovering the 14 "right law, wrong section" losses

Status: **RESOLVED 2026-08-19 — experiments run, winner implemented. See section 10.**
Evidence base: `docs/pipeline-attribution.md`, `logs/trace_final.json`.

## 1. The failure, precisely

Of 69 pieces of panel evidence, retrieval loses 21. They are two different faults:

| | n | |
|---|---|---|
| the containing law reached the shortlist, but not the **cited section** | **14** | this proposal |
| the law never surfaced at all | 7 | out of scope here |

For the 14, the containing law is *already ranked well*. Its best provision's global rank:

| law | provisions | best rank | its provisions inside top-300 |
|---|---|---|---|
| Data Availability and Transparency Act 2022 | 169 | **3** | 20 |
| Telecommunications (Interception and Access) Act 1979 | 618 | **4** | 73 |
| MY PDP Code of Practice (communications) | 95 | **7** | 11 |
| Surveillance Legislation Amendment Act 2021 | 260 | 8 | 35 |
| Telecommunications Legislation Amendment Act | 267 | 22 | 24 |
| MY PDPA (Act 709) | 151 | 28 | 31 |
| Telecommunications Act 1997 | 1,226 | 47 | 10 |
| Telecommunications Regulations 2021 | 66 | 143 | 1 |

Median best-rank **24**; 12 of 14 within the top 50. Median law size 123 provisions, max 1,226.

So the shortlist already "knows" the right instrument — it just spends its 300 slots on breadth
across many laws rather than depth inside the few that matter. A 1,226-provision Act contributes
10 provisions, and the panel's section 10 is not among them.

## 2. Candidate A — law-conditioned second pass (primary proposal)

```
pass 1  global hybrid ranking over all provisions        -> top K
pass 2  laws in contention := top N laws, ranked by their BEST provision's GLOBAL score
        for each such law: take its top m provisions, ordered by the SAME global scores
shortlist := union(pass 1, pass 2)
```

**Why this is not the thing we already measured as harmful.** `retrieve_per_law_k = 3` was
turned off because it *lowered* recall. It differed in two decisive ways:

1. **It reserved slots for every law in the corpus.** With 383 laws and a 300-slot budget the
   rank-0 pass alone exhausted the budget, so the shortlist degenerated into one provision from
   each of 300 laws — maximum breadth, zero depth. Pass 2 here only deepens laws the global pass
   has *already* placed in contention; it adds **no breadth at all**.
2. **It re-ranked within each law**, because `retrieve()` renormalises BM25 over whatever
   provision set it is handed. A mediocre provision in an off-topic Act could therefore outrank
   a strong one elsewhere. Here scores are computed **once, globally**; the per-law step only
   *selects* among already-comparable scores, it never rescores.

**Why precision should hold.** Every added candidate comes from a document that already scored
highly for this indicator, so we buy depth inside relevant instruments — the least diluting way
to spend budget. The measured grader false-positive rate is **0 on 102 adversarial negatives**,
so extra candidates predominantly cost money rather than wrong answers. That is a hypothesis to
test (E3), not an assumption.

Sizing from the table above: N around 20 covers laws whose best rank is <= 25 (7/14 directly,
12/14 at N around 50); m around 10-20 is needed for the large Acts. Rough budget: K = 200-300
plus N*m around 200, i.e. **400-500 candidates per indicator vs 300 today (+33-67% LLM calls)**.

## 3. Candidate B — pseudo-relevance feedback (complementary, no law logic)

Expand the indicator query with the distinctive terms of the top-j provisions from pass 1, then
re-retrieve. Attacks the same failure from the other side: the right law is found, but the cited
section words the obligation differently ("warrant", "authorised officer") from the indicator's
vocabulary. Cheap, no LLM, no law-level bookkeeping. Classic risk: query drift when the top-j is
already off-topic.

## 4. Candidate C — size-adaptive depth

Let m grow with the law's size (e.g. `m = clamp(round(4*log2(n_provisions)), 5, 40)`). The
failures concentrate in large instruments (median 123 provisions, max 1,226) while a
17-provision amendment Act needs nothing. A refinement of A rather than an alternative.

## 5. Candidate D — structural neighbour expansion

When a provision is shortlisted, also admit its structural siblings (same Part/Division, or the
two adjacent section numbers within the same law). Legal obligations cluster: interception
warrants sit next to interception warrants. Extremely cheap and bounded. Whether it helps depends
on how far the missed sections sit from the retrieved ones — measured in E0 before it is taken
seriously.

## 6. Experiments

### E0 — characterisation (free, no LLM). Decides which lever is right and how to size it.

* distribution of **distinct laws present in the global top-300** per (economy, indicator) — if
  this is 100+, N must stay small or A's cost explodes;
* the **absolute global rank** of each of the 14 target sections (today known only to be > 300) —
  tells us whether a bigger flat K would fix this more simply than A;
* **structural distance** from each missed section to the nearest retrieved provision of the same
  law — decides candidate D;
* query/provision vocabulary overlap for the missed sections — sanity check for B.

### E1 — offline sweep (free, CPU only; ~1-2 h with warm embedding caches)

Grid: A over N in {10, 20, 40} x m in {5, 10, 20}, with K in {150, 200, 300}; B with j in {5, 10}
and 10/20 expansion terms; C as a variant of the best A; D standalone and combined with the best
A. Baseline: current production config.

### E2 — regression guard (free)

`tools/validate_retrieval.py` must show **no drop** in indicator-level law recall (22/23) or
provision recall (17/19). A change that trades indicator coverage for evidence depth is a
regression, not an improvement.

### E3 — precision, the only part needing the LLM (~$0.30; budget remaining ~$4.84)

Grade **only the candidates the new config adds**, for the affected indicators, and report:

a. how many previously-lost panel targets now survive grading (the win);
b. how many *added, non-panel* candidates the grader accepts — then manually classify a sample of
   ~20 as **genuine additional finding** vs **false positive**.

(b) is essential because `target_density` cannot tell those two apart, and finding more than the
panel is an explicit project goal — so a density drop is not by itself evidence of harm.

## 7. Metrics

| metric | now | role |
|---|---|---|
| **evidence-level retrieval recall** = targets passing retrieval / targets that had an extracted provision | **36/57 = 0.632** | primary |
| indicator-level law recall | 22/23 | must not regress (E2) |
| indicator-level provision recall | 17/19 | must not regress (E2) |
| LLM calls per economy (sum of shortlist sizes) | 2,700 | cost ceiling |
| target density | 0.13-0.20 | reported, **not** optimised |
| grader acceptance on added non-panel candidates | — | precision (E3) |

## 8. Expected trade-offs, stated in advance

* **Ceiling.** A/B/C/D address at most the **14**. The other 7 losses ("law never surfaced" — 4 MY
  amendment Acts whose text is amendment *instructions*, the AU HTML shell, and so on) are
  untouched by anything in this document.
* **Expected result:** evidence-level recall 0.632 -> ~0.75-0.85; LLM calls +30-60%;
  indicator-level unchanged; target density falls mechanically.
* **Failure mode to watch:** if E0 shows 100+ distinct laws in contention per indicator, A gets
  expensive and B or D becomes the better lever.
* **Honest possibility:** E0 may show that a flat K = 600 recovers most of the 14 at similar cost
  and with far less machinery. If so we should do that instead — part of E0's job is to give that
  outcome a fair chance to win.

## 9. Decision rule (fixed before running, to prevent post-hoc selection)

Adopt the configuration that maximises **evidence-level retrieval recall** subject to:

1. no regression in indicator-level law/provision recall (E2);
2. LLM calls <= **1.5x** current;
3. E3 showing no material increase in clearly-wrong accepted mappings.

If no configuration satisfies all three, report that and change nothing.

---

# 10. Results (2026-08-19) — the simple option won, the clever one was dominated

All experiments ran on the built corpus (47,775 provisions) against the panel's evidence, using
the curated `data/ground_truth/rdtii_reference_p67.csv` for the operative section per instrument.
Targets are split **statute vs non-statute**, because the brief for this round is to get Acts
right end to end; the non-statute instruments have an *acquisition* problem (PDF links hidden
behind anchor text), not a retrieval one.

## E0 — characterisation killed most of the design space

**Distinct laws inside the global top-300: median 53** (min 28, max 79). Small enough that a
law-conditioned pass 2 is affordable — so cost was never the objection that mattered.

The objection that mattered came from the rank distribution. The missed targets do **not** sit
just below the cut:

| rank of the missed target | count |
|---|---|
| 444 | 2 |
| 596 – 900 | 3 |
| 1,000 – 3,000 | 8 |
| 3,300 – 13,315 | 14 |

A provision at rank 6,226 or 13,315 out of 18,262 is not "nearly retrieved" — the scorer
actively judges it irrelevant. Budget cannot fix that:

```
flat K=450  recovers  2/27      flat K=1500  recovers  8/27
flat K=600  recovers  3/27      flat K=3000  recovers 13/27   (10x the cost)
flat K=900  recovers  5/27
```

## E1 — every depth mechanism was dominated by raising K

Statute-target retrieval recall, LLM calls, and `useful%` = share of pass-2 candidates coming
from a law that actually holds panel evidence:

| configuration | ACT recall | calls | useful% |
|---|---|---|---|
| **baseline flat K=300** | 0.702 (33/47) | 8,100 | — |
| A: N=20, m=10, score=max | 0.723 (34/47) | 9,942 | **0.028** |
| A: N=20, m=10, score=mean_top3 | 0.702 (33/47) | 9,637 | 0.025 |
| A: N=40, m=20, score=count_topk | 0.723 (34/47) | 20,879 | 0.020 |
| A: N=20, m=10, adaptive depth (C) | 0.723 (34/47) | 10,152 | 0.031 |
| D: adjacent sections ±2 | 0.745 (35/47) | 20,877 | 0.111 |
| **flat K=450** | **0.745 (35/47)** | **12,150** | — |
| flat K=450 + A / + D | 0.745 (35/47) | 12,171 / 22,976 | 0.000 / 0.097 |

**The objection to candidate A is confirmed by measurement.** Across every A variant,
`useful%` is **0.012–0.072** — that is, **93–99 % of the provisions pass 2 pulls in come from
laws that hold no panel evidence at all.** One strong provision does drag a law into
contention, and we would then pay to grade dozens of its sections for nothing. Worse, after
paying that price A still recovers *fewer* targets than simply raising K.

The four law-scoring definitions were meant to fix exactly this — requiring sustained relevance
(`mean_top3`, `sum_top5`) or hit density (`count_topk`) instead of a single lucky provision.
None of them helped: `mean_top3` was the *worst* performer. Depth inside a law is simply not
where the missing evidence is.

## E1b — the knee is sharp and sits exactly at 450

| K | 300 | 330 | 360 | 400 | 425 | **450** | 475 | 500 |
|---|---|---|---|---|---|---|---|---|
| ACT recall | 0.702 | 0.702 | 0.702 | 0.702 | 0.702 | **0.745** | 0.745 | 0.745 |

Nothing between 300 and 425 buys anything; 450 admits the two AU targets sitting at rank 444;
475 and 500 add nothing further.

## E2 — no regression; indicator-level actually improves

`tools/validate_retrieval.py`, production code, same corpus and labels:

| | K=300 | K=450 |
|---|---|---|
| law-level | 22/23 | **23/23** |
| provision-level | 17/19 | **18/19** |
| SG / AU / MY (provision) | 5/5 · 5/6 · 7/8 | 5/5 · **6/6** · 7/8 |
| LLM calls (3 economies) | 8,100 | 12,150 |

## E3 — the extra budget costs money, not precision

Graded a random 300 of the **4,050** candidates that K=450 adds over K=300, using the shipped
prompt: **0 of 300 accepted** ($0.15). Consistent with the earlier adversarial run (0 false
positives on 102 negatives). No manual classification was needed because nothing was accepted.

## Decision

All three gates pass — no indicator-level regression, calls exactly at the 1.5× ceiling, and no
precision cost. **Implemented: `retrieve_max_top_k` 300 → 450** (`backend/config.py`). Nothing
else changed; candidates A, B, C and D are rejected on measurement and should not be revisited
without new evidence.

## What this says about the remaining losses

Raising K recovers 2 of the 14 "right law, wrong section" cases. Inspecting the text behind the
rest shows most were never retrieval failures at all — of the 47 statute targets reaching
retrieval, **12 are matched to the wrong text**:

| cause | n | example |
|---|---|---|
| amendment instruction | 7 | MY PDPA (Amendment) 2024 "s 129" is really *"Pindaan seksyen 4 — the principal Act is amended…"*; AU Surveillance Legislation Amendment "s 25A" is *"At the end of subsection 4(1) Add:…"* |
| section-label mismatch | 4 | panel cites s 11(3) / s 3.1 / s 45(2)(a)(i), the corpus holds only the parent s 11 / s 3 / s 45 |
| wrong language side | 1 | MY Security Offences Act matched the Bahasa Malaysia column |

When the panel cites an **amendment Act**, the operative text lives in the *principal* Act after
consolidation — grading the amendment instruction is meaningless, and its low rank is the
scorer behaving correctly. That is the next real problem, and it belongs to
extraction/law-identity, not retrieval.
