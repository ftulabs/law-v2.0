# Retrieval redesign — measured, not argued

Branch: `feat/precompute-corpus` · measured 2026-08-15 · CPU-only dev laptop

Every number here comes from running the pipeline over a built corpus and scoring it against
the judges' own RDTII 2.1 Round-1 Database. Reproduce with:

```bash
python -m backend.eval.ground_truth          # labels  -> data/ground_truth/rdtii_p67_labels.json
python -m backend.eval.linkage               # cited laws -> catalogue law_ids
python tools/build_eval_corpus.py --economy MY   # (and SG, AU)
python tools/sweep_retrieval.py --stage final
python tools/validate_retrieval.py           # production code, same corpus + labels
```

---

## 1. The evaluation set

**Labels.** The Database is a label set: for every (economy, indicator) the panel recorded the
Act(s) they accepted and a justification that usually names the provision ("According to
Section 199, every company must retain accounting records for 5 years"). `backend/eval/
ground_truth.py` parses that into 48 label rows over pillars 6–7 — 43 citing a provision,
**5 recording an ABSENCE** ("Singapore does not implement ban on data transfer"). The absence
rows are kept separate: a pipeline that returns a provision there is producing a false
positive, so scoring them as targets would reward the wrong behaviour.

**Law linkage.** The panel cites laws by name, and often links a third-party mirror
(`mohre.um.edu.my`, `cyrilla.org`) rather than the official portal, so URLs are useless as a
join key. `backend/eval/linkage.py` matches names with a symmetric token-overlap test plus an
instrument-TYPE guard. **27 of 37 cited laws** are in our catalogue. The 10 that are not is a
finding, not a bug — see §5.

**Corpus.** Retrieval cannot be measured on the answer laws alone (every ranking looks
perfect) nor on a purely random sample (nothing competes). `backend/eval/corpus_sample.py`
builds a stratified corpus per economy: all cited laws + 60 **hard** distractors (titles
closest to the pillar vocabulary) + 60 random. Built end to end through the real pipeline:

| | laws | provisions |
|---|---|---|
| SG | 127 | 13,628 |
| AU | 129 | 12,917 |
| MY | 127 | 10,045 |
| **total** | **383** | **36,590** |

**Metrics.** `law_recall` = did any provision of a cited law reach the shortlist (the ceiling
on what grading can possibly get right). `prov_recall` = did the *specific* provision the
panel named reach it. `n_calls` = shortlist size summed over indicators, i.e. what the config
costs in LLM calls — recall without it is meaningless, since grading everything scores 1.000.

---

## 2. The first finding was not about retrieval

Before any parameter moved, the target-coverage check said two Australian Acts held **1 and 0
provisions**. Both are RDTII answer laws:

* Telecommunications (Interception and Access) Act 1979 — the 7.3 retention answer (s 187C)
* Telecommunications Act 1997 — cited for 7.5

Cause: `legislation.gov.au` publishes large Acts as **multi-volume** compilations, and for
those the single-file PDF URL `…/text/original/pdf` returns **404**. The correct form appends
the volume: `…/text/original/pdf/{volumeNumber}`. The 404 was silent — fetch failed, the
pipeline fell back to the SPA landing page, and the Act contributed one junk provision.

Fixed in `discovery._au_compilation_pdf_urls` (+ `corpus/build.py` reads every volume and
splits each **separately**; concatenating them first made the splitter treat volume 2's
opening body as a table of contents and drop it, which is how ss 187A–187N disappeared).

| Act | provisions before | after |
|---|---|---|
| Telecommunications (Interception and Access) Act 1979 | 1 | 618 |
| Telecommunications Act 1997 | 0 | 1,377 |

**No retrieval configuration could have recovered those.** Two more portal defects were found
and fixed the same way: `lom.agc.gov.my` now AES-GCM-encrypts its catalogue JSON (the shipped
MY adapter was silently returning **0 Acts**), and `sso.agc.gov.sg` ignores `CurrentPage`, so
its index has to be enumerated by sort-window union.

---

## 3. Sweep results (383 laws, 36,590 provisions, 27 economy×indicator pairs)

`law_hits` are over the 22 pairs with a locatable cited law; `prov_hits` over the 18 that name
a provision. `dens` = share of the shortlist drawn from cited laws.

| configuration | law recall | prov recall | dens | LLM calls |
|---|---|---|---|---|
| **baseline (shipped)** | 1.000 (22/22) | 0.833 (15/18) | 0.075 | 1,431 |
| k=40 per-law=0 | 0.955 | 0.889 | 0.290 | 1,188 |
| k=40 per-law=1 | 1.000 | 0.778 | 0.053 | 1,188 |
| k=40 per-law=3 | 1.000 | 0.778 | 0.053 | 1,188 |
| k=150 per-law=1 | 1.000 | 0.944 | 0.072 | 4,455 |
| k=150 per-law=3 | 1.000 | 0.889 | 0.036 | 4,455 |
| k=300 per-law=0 | 1.000 | **1.000** | 0.180 | 8,910 |
| k=300 per-law=3 | 1.000 | 0.944 | 0.031 | 8,910 |
| **CHOSEN — k=300, per-law=1, α=0.65** | **1.000 (22/22)** | **1.000 (18/18)** | 0.150 | 8,100 |
| same but α=0.50 (control) | 1.000 | 0.944 | 0.147 | 8,100 |

### 3.1 Per-law allocation was the coverage bug

`retrieve_per_law_k = 3` reserves each law's top-3 before spending the global budget. On a
383-law corpus that reservation *cannot fit*: the rank-0 pass alone wants 383 slots for a
budget of 40–300. The shortlist therefore degenerates into **one provision from each of the
top-k laws — maximum breadth, zero depth**. An answer like Companies Act s 199 only survives
if it happens to be that Act's single best-scoring provision for the indicator.

Measured in the lab: at k=150 dropping per-law 3→1 lifts provision recall 0.889 → 0.944; at
k=300, 3→1 lifts 0.944 → 1.000.

**Then the end-to-end check overturned the lab's choice of 1.** The lab ranks the reservation
by GLOBAL score; the shipped `_diverse_shortlist` calls `retrieve()` on each law's provisions
separately, so BM25 is renormalised **within** each law — a mediocre provision from an
off-topic Act can outrank a strong one from the right Act, and on a 129-law corpus the
reservation consumes ~43 % of the budget doing it. Running the real code both ways:

| shipped code, k=300 | law recall | prov recall | target density |
|---|---|---|---|
| `retrieve_per_law_k = 1` | 22/22 | 16/18 | SG 0.173 · AU 0.133 · MY 0.130 |
| **`retrieve_per_law_k = 0`** | **22/22** | **17/18** | SG 0.210 · AU 0.191 · MY 0.176 |

So the setting ships at **0**: better recall *and* a cleaner shortlist. The per-law guarantee
is a good idea implemented against the wrong scores; re-implementing it over global scores is
worth revisiting, and until then it is off rather than half-working.

### 3.2 Budget: 300 is a knee, not a ceiling

Provision recall 0.833 (k=40) → 0.944 (k=150) → 1.000 (k=300), then **flat** through
k=500, 800 and 1,200. Beyond 300 the extra calls buy nothing measurable, so "compute is not a
constraint" does not mean "make k huge" — it means spend up to the knee and stop.

Cost does **not** grow with the corpus: the cap binds, so a 500k-provision national corpus
still grades 300 per indicator.

### 3.3 A law-level prefilter was tested and rejected

The intuitive two-stage design — rank laws, then take depth inside the best ones — was
measured at prefilter ∈ {5, 10, 25, 50} laws and is **uniformly worse** than no prefilter at
every budget (prefilter=5: law 0.818/prov 0.667; prefilter=50 at k=300: 0.955/0.944 vs
1.000/1.000 without). A law whose *title* and bulk are about something else still holds the
one provision that answers the indicator, and a law-level gate throws it away before the
provision is ever considered. Hypothesis killed by measurement; recorded so it is not
re-proposed.

### 3.4 Fusion weights

| knob | result |
|---|---|
| `hybrid_alpha` | 0.65 best (18/18). 0.50 → 17/18. Pure dense (0.0) and pure BM25 (1.0) → 16/18. |
| cross-encoder weight | 0.25–0.75 equivalent; **0.0 (no reranker) loses a target**, 1.0 (reranker only) loses three. Keep 0.5. |
| phrase bonus / sibling penalty | no recall effect; removing them lowers `dens` 0.136 → 0.127, i.e. they help precision slightly. Keep. |
| dense-recall guarantee | **inert** at k ≥ 150: 0.000 recall change for ~10% more calls. Default 0. |

The cross-encoder result is worth stating plainly: it is English-only and that is a known
limitation for the Finals economies — but on Round-1 data it is **load-bearing**, not
decorative. Removing it costs a target.

---

## 4. What shipped

`backend/config.py`:

| setting | was | now | why |
|---|---|---|---|
| `hybrid_alpha` | 0.5 | **0.65** | 18/18 vs 17/18 |
| `retrieve_max_top_k` | 40 | **300** | recall knee |
| `retrieve_top_k` | 20 | **40** | floor for small corpora |
| `retrieve_per_law_k` | 3 | **1** | breadth-without-depth degeneration |
| `dense_recall_extra` | hardcoded `max(2, k//3)` | **0** (configurable) | measured inert, cost ~10% of calls |

### Before / after, measured end-to-end on the shipped code

`tools/validate_retrieval.py` runs the **production** functions (`retrieval.retrieve` +
`mapping._diverse_shortlist`, driven by `settings`) over the same corpus and labels, so the
swept result and the shipped behaviour cannot drift apart unnoticed. Both columns below are
that script, same corpus, only `settings` differing:

| | old settings | new settings |
|---|---|---|
| shortlist k | 40 | 300 |
| **law recall** | 22/22 (1.000) | 22/22 (1.000) |
| **provision recall** | **11/18 (0.611)** | **17/18 (0.944)** |
| SG / AU / MY provisions | 5/5 · **1/5** · 5/8 | 5/5 · **5/5** · 7/8 |
| target density | 0.028 · 0.039 · 0.047 | 0.210 · 0.191 · 0.176 |
| LLM calls (3 economies) | 1,080 | 8,100 |

Australia is the headline: **1 of 5 cited provisions retrieved, now 5 of 5.** And the
shortlist got *cleaner* as it got bigger — density rose 4–5× — because the old configuration
was spending its 40 slots on one-provision-per-law breadth instead of on the laws that matter.

Cost: 8,100 calls ≈ **$6.2** at `deepseek-v4-flash` list price for a full three-economy
grading pass, and it does not grow with the corpus (the cap binds).

> The lab sweep reports the baseline at 0.833, not 0.611, because `rank_lab.baseline_config`
> reproduces the shipped *parameters* but ranks the per-law reservation globally, which the
> shipped code does not. The end-to-end figure (0.611) is the one to quote; the discrepancy is
> exactly why this validation script exists.

---

## 5. Limits — read before quoting these numbers

1. **18 provision-level targets.** The Database names a specific provision for only 18 of the
   27 economy×indicator pairs. Moving one target moves recall by 0.056. These are directional
   measurements on a small set, not tight estimates.
2. **10 of 37 cited laws are outside our catalogue**, so they are excluded from the
   denominator: SG PDPC guidance and an IMDA licence, AU's Cyber Security Strategy and OAIC
   PIA guidance (policy documents, not legislation) and the Telecommunications Regulations
   2021 (a legislative instrument, not an Act), and MY's sectoral Codes of Practice + the PDP
   Standard 2015. **This is the largest remaining coverage gap** and it is a *discovery*
   problem, not a retrieval one — the fix is enumerating subsidiary instruments and regulator
   guidance, not tuning ranking.
3. **The corpus is 383 laws, not 6,529.** Distractors are stratified to imitate full-corpus
   contention, but hard-negative pressure at true scale will be higher.
4. **Precision is not measured.** `dens` is a dilution signal, not precision: a law the panel
   did not cite may still be a legitimate find, and finding more than the panel is an explicit
   goal. Real precision needs the grader — see §6.
5. **Extraction noise is in the corpus.** SSO PDFs carry an amendment-history appendix that
   splits into provision-shaped rows; it lowers `dens` for every configuration equally, so
   comparisons hold, but absolute density is pessimistic.

---

## 6. Not done: the LLM half

The grader experiment and the confidence-weight fit are **implemented but unrun**: the
OpenRouter key in `.env` / `.streamlit/secrets.toml` returns `401 User not found`, and no
Anthropic/OpenAI/Gemini key is configured. Fitting weights against the offline mock grader
would be fitting to a lexical stub, so it was not done.

Ready to run the moment a working key is present:

```bash
python -c "from backend.eval.grader_eval import *; \
           pairs=build_pairs(); r,s=grade_pairs(pairs, budget_usd=5.0); print(save(r,s))"
```

`backend/eval/grader_eval.py` builds **222 labelled pairs** — 105 positives (the provisions
the panel cited), 90 **sibling negatives** (a confirmed answer for indicator X offered to a
sibling Y it is not an answer to: exactly the P6-I1/P6-I4 and P7-I1/P7-I2 confusions), and 27
random negatives — then reports grader recall, sibling false-positive rate, and grid-fits the
four confidence weights by ROC AUC against the shipped `WEIGHTS`. Estimated cost at
deepseek-v4-flash list price: **$0.14**, comfortably inside the $5 budget.

Until that runs, `backend/pipeline/confidence.py` weights are **unchanged** — they are
hand-chosen and remain so, and this document does not claim otherwise.
