# P0 — Confidence Discrimination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the confidence score carry real information about whether a mapping is correct — raise AUC against the judges' answer key from the measured **0.458** (below chance) to **>= 0.70**, so the quarantine band becomes reachable and auto-accept stops being a relabelling of the grader's self-report.

**Architecture:** Today `final = 0.25*retrieval + 0.40*legal_match + 0.20*grounding + 0.15*scope`, but three of those four terms are constants in practice (measured, N=457), so the score reduces to `0.456 + 0.40*legal_match`. This plan does three things in order: (1) build the AUC harness that every later task is judged by; (2) turn the dead terms into live ones — rank-normalise `retrieval_score` (it is not on a 0-1 scale today), stop `snippet_grounding` self-certifying, and add a genuinely varying snippet-quality signal; (3) recentre the blend on the terms that now vary and recalibrate thresholds against AUC rather than against an auto%/pend% quota.

**Tech Stack:** Python 3.11+, pydantic v2 (`backend/schemas.py`), pytest, stdlib only — no new dependency

**Spec:**
- `docs/superpowers/plans/2026-09-06-veritrade-confidence-retrieval-fix.md` — master plan, and its **"Measured Baseline (2026-09-06)"** section, which is the evidence this plan argues from
- `CLAUDE.md` §4 (Known Gaps), §7 (retrieval parameters are MEASURED, not hand-tuned), §9 (judging criteria)

## Global Constraints

- **AUC is the gate, not auto%/pend%.** A change that moves auto% without moving AUC is not progress; a quota can be met by moving thresholds without improving a single mapping.
- **Minimal code comments.** Explain a decision only where the reason is not visible in the code. Do not reproduce this plan's prose in docstrings; the repo's existing heavy-comment style is not the target here.
- **No hand-tuned constants.** Every threshold introduced must be produced by a script in `tools/` or `backend/eval/`, and the measured value recorded in the commit message — the house rule from CLAUDE.md §7.
- **Sample mode must stay byte-identical.** `python main.py --economy Singapore --pillar 6` (offline, mock LLM) is the reproducibility demo; changes gated on live runs must not alter it.
- **`Verbatim Snippet` is never rewritten.** No task may modify snippet text; snippet *quality* is scored alongside it, never substituted for it.
- **Four-signal auditability is preserved.** `ConfidenceBreakdown` keeps all existing fields so the dashboard evidence panel and every stored JSON trace stay readable; new fields are additive with defaults.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `backend/eval/confidence_eval.py` | **create** | Join run mappings to the answer key, compute AUC. The acceptance gate. |
| `backend/pipeline/retrieval_norm.py` | **create** | Rank-percentile normalisation of a score list. Pure function, no I/O. |
| `backend/pipeline/snippet_quality.py` | **create** | Detect table-of-contents / outline text masquerading as a provision. |
| `backend/pipeline/confidence.py` | modify | Weighted blend, gates, cap constants. |
| `backend/pipeline/mapping.py` | modify | Normalise retrieval per indicator; pass real grounding + snippet quality into scoring. |
| `backend/schemas.py` | modify | Two additive `ConfidenceBreakdown` fields. |
| `backend/config.py` | modify | Calibrated thresholds. |
| `tests/test_confidence_eval.py` | **create** | AUC harness unit tests. |
| `tests/test_retrieval_norm.py` | **create** | Normalisation unit tests. |
| `tests/test_snippet_quality.py` | **create** | TOC-detection unit tests. |
| `tests/test_confidence.py` | modify | Existing 5 tests must keep passing; add discrimination tests. |

**Interfaces produced by this plan** (later tasks and P1/P2 rely on these exact names):

```python
# backend/pipeline/retrieval_norm.py
def rank_normalise(scores: list[float]) -> list[float]: ...

# backend/pipeline/snippet_quality.py
def body_text_score(snippet: str) -> float: ...

# backend/pipeline/confidence.py  (signature grows; new args keyword-only with defaults)
def score(retrieval_score: float, legal_match: float, grounding: float,
          scope_alignment: float, scope_flag: str | None,
          apply_scope_cap: bool = True, topical_ok: bool = True, explanation: str = "",
          *, body_text: float = 1.0, grounding_verified: bool = True) -> ConfidenceBreakdown: ...

# backend/eval/confidence_eval.py
def load_key(path: str = "data/ground_truth/rdtii_reference_p67.csv") -> set[tuple[str, str, str]]: ...
def label_runs(pattern: str, key: set) -> list[tuple[float, bool]]: ...
def auc(labelled: list[tuple[float, bool]]) -> float | None: ...
```

---

### Task 1: AUC harness against the answer key

Nothing else in this plan can be judged until this exists. It must be built first and must reproduce the baseline **AUC = 0.458** on the 2026-08-25 runs — if it does not, the harness is wrong, not the pipeline.

**Files:**
- Create: `backend/eval/confidence_eval.py`
- Test: `tests/test_confidence_eval.py`

**Interfaces:**
- Consumes: `outputs/rt_check/*.json` run traces; `data/ground_truth/rdtii_reference_p67.csv`
- Produces: `load_key()`, `label_runs()`, `auc()` — every later task's gate

- [ ] **Step 1: Write the failing test**

```python
# tests/test_confidence_eval.py
from backend.eval import confidence_eval as CE


def test_auc_perfect_separation():
    assert CE.auc([(0.9, True), (0.8, True), (0.2, False), (0.1, False)]) == 1.0


def test_auc_inverted_separation():
    assert CE.auc([(0.1, True), (0.2, True), (0.8, False), (0.9, False)]) == 0.0


def test_auc_ties_count_half():
    assert CE.auc([(0.5, True), (0.5, False)]) == 0.5


def test_auc_undefined_without_both_classes():
    assert CE.auc([(0.9, True), (0.8, True)]) is None


def test_load_key_returns_normalised_triples():
    key = CE.load_key()
    assert ("au", "myhealthrecordsact2012", "P6-I1") in key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_confidence_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.eval.confidence_eval'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/eval/confidence_eval.py
"""Does the confidence score predict whether a mapping is in the answer key?"""
from __future__ import annotations

import csv
import glob
import json
import os
import re

_ECON_PREFIX = {"AU": "au", "SG": "si", "MY": "ma", "CN": "ch", "IN": "in", "MN": "mo"}
_KEY_CSV = "data/ground_truth/rdtii_reference_p67.csv"


def _nk(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_key(path: str = _KEY_CSV) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            out.add((_nk(row["Economy"])[:2], _nk(row["Law Name"]), row["Indicator ID"].strip()))
    return out


def label_runs(pattern: str, key: set[tuple[str, str, str]]) -> list[tuple[float, bool]]:
    """(confidence, in_answer_key) per graded mapping. No-evidence rows are excluded."""
    labelled: list[tuple[float, bool]] = []
    for path in sorted(glob.glob(pattern)):
        econ = os.path.basename(path)[:2]
        prefix = _ECON_PREFIX.get(econ, _nk(econ)[:2])
        with open(path, encoding="utf-8") as fh:
            trace = json.load(fh)
        for m in trace.get("mappings", []):
            b = m.get("confidence_breakdown")
            if not b or not b.get("snippet_grounding"):
                continue
            hit = (prefix, _nk(m.get("law_name")), m.get("indicator_id", "")) in key
            labelled.append((float(m.get("confidence_score") or 0.0), hit))
    return labelled


def auc(labelled: list[tuple[float, bool]]) -> float | None:
    """P(score(in-key) > score(not-in-key)), ties counting half. None if a class is absent."""
    pos = [s for s, y in labelled if y]
    neg = [s for s, y in labelled if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def report(pattern: str = "outputs/rt_check/*.json") -> dict:
    key = load_key()
    labelled = label_runs(pattern, key)
    pos = [s for s, y in labelled if y]
    neg = [s for s, y in labelled if not y]
    return {
        "n": len(labelled), "n_in_key": len(pos), "n_not_in_key": len(neg),
        "mean_in_key": round(sum(pos) / len(pos), 3) if pos else None,
        "mean_not_in_key": round(sum(neg) / len(neg), 3) if neg else None,
        "auc": auc(labelled),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="outputs/rt_check/*.json")
    args = ap.parse_args()
    for k, v in report(args.glob).items():
        print(f"{k:18} {v}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_confidence_eval.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Reproduce the documented baseline**

Run: `python -m backend.eval.confidence_eval`
Expected, exactly — if it differs, fix the harness before Task 2:

```
n                  444
n_in_key           133
n_not_in_key       311
mean_in_key        0.781
mean_not_in_key    0.793
auc                0.458
```

- [ ] **Step 6: Commit**

```bash
git add backend/eval/confidence_eval.py tests/test_confidence_eval.py
git commit -m "eval: measure whether confidence predicts the answer key at all — it does not (AUC 0.458)"
```

---

### Task 2: Rank-normalise `retrieval_score`

`retrieval_score` is a raw hybrid/RRF fusion score, not a 0-1 quantity: measured range **0.274–1.209** (CN exceeds 1.0), median 0.425, only 2.9% above 0.85. Its 0.25 weight therefore contributes ~0.106 with almost no variance, and its scale differs per economy (AU p90 = 0.501 vs CN p90 = 0.988), so the same confidence number means different things in different economies. Rank-percentile within the (run, indicator) candidate set is scale-free, bounded, and comparable across economies.

**Files:**
- Create: `backend/pipeline/retrieval_norm.py`
- Test: `tests/test_retrieval_norm.py`

**Interfaces:**
- Produces: `rank_normalise(scores: list[float]) -> list[float]` — consumed by Task 5's wiring in `mapping.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retrieval_norm.py
from backend.pipeline.retrieval_norm import rank_normalise


def test_monotone_and_bounded():
    assert rank_normalise([0.31, 0.42, 0.68]) == [0.0, 0.5, 1.0]


def test_ties_share_a_percentile():
    out = rank_normalise([0.4, 0.4, 0.9])
    assert out[0] == out[1] < out[2]


def test_out_of_range_input_is_still_bounded():
    """CN's fusion scores exceed 1.0; normalisation must not propagate that."""
    assert all(0.0 <= v <= 1.0 for v in rank_normalise([0.3, 1.209]))


def test_all_equal_scores_map_to_midpoint():
    """grade-all mode gives many provisions score 0.0; they must not all become 1.0."""
    assert rank_normalise([0.0, 0.0, 0.0]) == [0.5, 0.5, 0.5]


def test_single_candidate_is_midpoint():
    assert rank_normalise([0.42]) == [0.5]


def test_empty():
    assert rank_normalise([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval_norm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.retrieval_norm'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/pipeline/retrieval_norm.py
"""Rank-percentile normalisation of retrieval scores.

The hybrid retriever's fusion score is unbounded (measured 0.274-1.209) and its scale differs
per economy, so it cannot be blended as a 0-1 term. Rank within the candidate set can be.
"""
from __future__ import annotations


def rank_normalise(scores: list[float]) -> list[float]:
    if not scores:
        return []
    if len(scores) == 1:
        return [0.5]
    n = len(scores)
    order = sorted(range(n), key=lambda i: scores[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        pct = 0.5 if j - i + 1 == n else ((i + j) / 2) / (n - 1)
        for k in range(i, j + 1):
            out[order[k]] = round(pct, 4)
        i = j + 1
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_retrieval_norm.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/retrieval_norm.py tests/test_retrieval_norm.py
git commit -m "retrieval: rank-normalise fusion scores — they range 0.274-1.209 and differ in scale per economy"
```

---

### Task 3: Detect table-of-contents text posing as a provision

This is the one genuinely new *live* signal in P0. Worked example from the measured run: `AU_P67_20260825-035642.json` auto-accepted at **0.916** a P7-I2 mapping whose snippet is `"4 Simplified outline of this Act"` — a contents entry, with `raw_context_before` full of dot leaders (`".........33"`). Nothing in the pipeline noticed it was not operative text.

**Files:**
- Create: `backend/pipeline/snippet_quality.py`
- Test: `tests/test_snippet_quality.py`

**Interfaces:**
- Produces: `body_text_score(snippet: str) -> float` in [0,1]; 1.0 = ordinary operative text, low = contents/index/heading matter. Consumed by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_snippet_quality.py
from backend.pipeline.snippet_quality import body_text_score


def test_dot_leader_contents_block_scores_low():
    toc = ("31 Legal professional privilege...................................36\n"
           "32 Admissibility of information.................................38\n"
           "33 Civil penalty provisions.....................................41")
    assert body_text_score(toc) < 0.4


def test_simplified_outline_heading_scores_low():
    """The exact AU snippet that auto-accepted at 0.916 for P7-I2."""
    assert body_text_score("4 Simplified outline of this Act") < 0.5


def test_operative_provision_scores_high():
    prov = ("A registered repository operator must not hold the records, or take the records, "
            "outside Australia, or process or handle the information relating to the records "
            "outside Australia.")
    assert body_text_score(prov) >= 0.9


def test_non_latin_operative_text_scores_high():
    """Heuristics are Latin-script; a Chinese provision must not be penalised."""
    assert body_text_score("个人信息处理者因业务需要，确需向中华人民共和国境外提供个人信息的，应当符合下列条件之一。") >= 0.9


def test_short_numeric_heading_scores_low():
    assert body_text_score("Part 3 — Notification  52") < 0.5


def test_empty_snippet_is_not_credited():
    assert body_text_score("") == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_snippet_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.snippet_quality'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/pipeline/snippet_quality.py
"""Is this snippet operative statutory text, or contents matter that merely mentions it?"""
from __future__ import annotations

import re

_DOT_LEADER = re.compile(r"\.{4,}\s*\d+")
_TRAILING_PAGENO = re.compile(r"\s\d{1,4}\s*$")
_OUTLINE_PHRASE = re.compile(
    r"\b(simplified outline|table of (contents|provisions)|contents|arrangement of sections|index)\b",
    re.I,
)
_OPERATIVE = re.compile(
    r"\b(must|shall|may not|is required|are required|prohibit|entitled|liable|"
    r"commits an offence|penalty|means|applies to|does not apply)\b",
    re.I,
)


def body_text_score(snippet: str) -> float:
    text = (snippet or "").strip()
    if not text:
        return 0.0
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0

    if sum(1 for ln in lines if _DOT_LEADER.search(ln)) / len(lines) >= 0.5:
        return 0.1
    if _OUTLINE_PHRASE.search(text):
        return 0.2
    if sum(c.isascii() for c in text) / len(text) < 0.5:
        return 1.0

    words = text.split()
    if len(words) <= 12 and not _OPERATIVE.search(text):
        return 0.3 if _TRAILING_PAGENO.search(text) else 0.4
    numeric_tail = sum(1 for ln in lines if _TRAILING_PAGENO.search(ln))
    if numeric_tail / len(lines) >= 0.6 and len(words) / len(lines) < 12:
        return 0.25
    return 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_snippet_quality.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Check it fires on real data, not just fixtures**

Run:

```bash
python -c "
import json,glob
from backend.pipeline.snippet_quality import body_text_score
low=tot=0
for f in sorted(glob.glob('outputs/rt_check/*.json')):
    for m in json.load(open(f,encoding='utf-8'))['mappings']:
        b=m.get('confidence_breakdown')
        if not b or not b['snippet_grounding']: continue
        tot+=1
        s=body_text_score(m['verbatim_snippet'])
        if s<0.5:
            low+=1
            if low<=5: print(f\"{s:.2f} {m['review_status']:14} {m['indicator_id']} {m['verbatim_snippet'][:70]!r}\")
print(f'--- {low}/{tot} snippets flagged as non-operative ---')
"
```

Expected, measured while writing this plan with the implementation above:

```
  0.20 AUTO@0.916 P7-I2 '4 Simplified outline of this Act\nThis Act provides for mandatory'
  0.20 AUTO@0.874 P7-I2 '4 Simplified outline of this Act\nThis Act creates a framework fo'
--- flagged 17/444 = 3.8%  by status: {'auto_accepted': 2, 'pending_review': 13, 'quarantined': 2} ---
```

Reproduce that, or better. If it flags 0 the heuristic is inert and Task 5 gains nothing — investigate before proceeding. If it flags more than ~25% of rows it is over-firing — tighten before proceeding.

**Calibrate your expectations:** at 3.8% of rows this signal is real but small, and it will not move AUC much on its own. The heavy lifting in P0 is Task 2 (retrieval normalisation, which changes every row) and Task 5 (the blend). Task 3's value is precision at the top of the distribution — it removes contents matter from *auto-accept* specifically, which is where a wrong row does the most damage to a submission.

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/snippet_quality.py tests/test_snippet_quality.py
git commit -m "confidence: detect contents/outline text posing as a provision (AU auto-accepted a TOC line at 0.916)"
```

---

### Task 4: Stop `snippet_grounding` self-certifying

`snippet_grounding` measures 1.0 on 444 of 457 mappings. Two structural causes: the snippet is *sliced from* the source text by extraction rather than generated by the model, so the substring test is near-tautological; and `mapping.py:621` calls `source_texts.get(prov.doc_id, prov.verbatim_snippet)` — when the document's text is missing, the snippet is compared **against itself** and scores a perfect 1.0. The anti-hallucination signal certifies itself precisely when it has nothing to check against.

**Files:**
- Modify: `backend/pipeline/mapping.py:621`, and the `confidence.score(...)` call at `:633`
- Modify: `backend/pipeline/confidence.py`
- Modify: `backend/schemas.py:230-236`
- Test: `tests/test_confidence.py`

**Interfaces:**
- Produces: `confidence.score(..., grounding_verified: bool = True)`; `ConfidenceBreakdown.grounding_verified`, `.body_text`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_confidence.py
def test_unverified_grounding_cannot_auto_accept():
    """With no source text the snippet is compared against itself; a perfect grounding score
    there is an artefact and must not carry a row to auto-accept."""
    b = C.score(retrieval_score=0.9, legal_match=1.0, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=True,
                grounding_verified=False)
    assert C.route(b.final) != ReviewStatus.AUTO_ACCEPTED
    assert b.grounding_verified is False


def test_verified_grounding_is_unaffected():
    b = C.score(retrieval_score=0.9, legal_match=1.0, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=True,
                grounding_verified=True)
    assert C.route(b.final) == ReviewStatus.AUTO_ACCEPTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_confidence.py -v`
Expected: FAIL — `TypeError: score() got an unexpected keyword argument 'grounding_verified'`

- [ ] **Step 3: Write minimal implementation**

In `backend/schemas.py`, add to `ConfidenceBreakdown` after `scope_alignment` (line 234):

```python
    grounding_verified: bool = True    # False when no source text was available to check against
    body_text: float = 1.0             # 1.0 = operative text, low = contents/index matter
```

In `backend/pipeline/confidence.py`, add next to `TOPICAL_FAIL_CAP` (line 32):

```python
UNVERIFIED_GROUNDING_CAP = 0.84   # below conf_auto_accept: surfaces for review, never auto-accepts
```

Add the keyword-only parameters to `score()`:

```python
    *,
    body_text: float = 1.0,
    grounding_verified: bool = True,
```

After the `topical_ok` cap block and before `final = round(...)`:

```python
    if not grounding_verified:
        final = min(final, UNVERIFIED_GROUNDING_CAP)
        caps.append(f"capped at {UNVERIFIED_GROUNDING_CAP} — no source text to verify the snippet against")
```

Pass both new values into the `ConfidenceBreakdown(...)` constructor:

```python
        grounding_verified=grounding_verified,
        body_text=round(body_text, 3),
```

In `backend/pipeline/mapping.py`, replace line 621:

```python
        src_text = source_texts.get(prov.doc_id, "")
        grounding_verified = bool(src_text)
        grounding = (confidence.snippet_grounding(prov.verbatim_snippet, src_text)
                     if grounding_verified else 1.0)
```

and add `grounding_verified=grounding_verified,` to the `confidence.score(...)` call at line 633.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_confidence.py -v`
Expected: PASS — 7 tests (the 5 pre-existing ones unchanged)

- [ ] **Step 5: Measure the blast radius on the real runs**

Run:

```bash
python -c "
import json,glob,os
for f in sorted(glob.glob('outputs/rt_check/*.json')):
    ms=[m for m in json.load(open(f,encoding='utf-8'))['mappings']
        if m.get('confidence_breakdown') and m['confidence_breakdown']['snippet_grounding']]
    same=sum(1 for m in ms if m.get('raw_context','')==m.get('verbatim_snippet',''))
    print(f'{os.path.basename(f)[:2]} {same}/{len(ms)} rows whose raw_context IS the snippet (proxy for missing source text)')
"
```

Record the output in the commit message.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/pipeline/confidence.py backend/pipeline/mapping.py tests/test_confidence.py
git commit -m "confidence: grounding compared the snippet against itself when source text was missing"
```

---

### Task 5: Recentre the blend on the signals that actually vary

With Tasks 2–4 done, `retrieval_score` is bounded and comparable, grounding no longer self-certifies, and `body_text` is a live term. Now the weighted sum can be rebuilt so the quarantine band is reachable. Measured today: the floor for any mapping passing the relevance gate is **0.63**, so the whole 0–0.60 band is dead and all 21 quarantines came from caps.

**Files:**
- Modify: `backend/pipeline/confidence.py` (`WEIGHTS`, `score()` body, note string)
- Modify: `backend/pipeline/mapping.py:505-530` (work list) and the `confidence.score(...)` call
- Test: `tests/test_confidence.py`

**Interfaces:**
- Consumes: `rank_normalise()` (Task 2), `body_text_score()` (Task 3), `grounding_verified` (Task 4)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_confidence.py
def test_quarantine_band_is_reachable_by_the_weighted_sum():
    """A weakly-retrieved, weakly-matched mapping must quarantine on score alone — no cap.
    Measured before this change: the floor was 0.63, so this was impossible."""
    b = C.score(retrieval_score=0.0, legal_match=0.5, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=True)
    assert C.route(b.final) == ReviewStatus.QUARANTINED
    assert "capped" not in b.explanation


def test_contents_snippet_cannot_auto_accept():
    """The AU regression: a table-of-contents line auto-accepted at 0.916 for P7-I2."""
    b = C.score(retrieval_score=0.9, legal_match=1.0, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=True, body_text=0.2)
    assert C.route(b.final) != ReviewStatus.AUTO_ACCEPTED


def test_strong_mapping_still_auto_accepts():
    """Guard against fixing precision by rejecting everything."""
    b = C.score(retrieval_score=0.95, legal_match=1.0, grounding=1.0, scope_alignment=1.0,
                scope_flag=None, apply_scope_cap=False, topical_ok=True, body_text=1.0)
    assert C.route(b.final) == ReviewStatus.AUTO_ACCEPTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_confidence.py -v`
Expected: FAIL — `test_quarantine_band_is_reachable_by_the_weighted_sum` yields `final == 0.75` (PENDING_REVIEW), and `score()` rejects `body_text`.

- [ ] **Step 3: Write minimal implementation**

In `backend/pipeline/confidence.py`, replace `WEIGHTS` (lines 25–30):

```python
WEIGHTS = {
    "retrieval_score": 0.40,   # rank-normalised within the indicator's candidate set
    "legal_match": 0.60,
}
```

`snippet_grounding` and `scope_alignment` stop being additive terms and become multiplicative gates — they were constants (1.0 on 444/457 and 422/457) contributing a flat +0.35 to every row. Both are still stored on the breakdown, so the evidence panel is unchanged.

Replace the `final = (...)` expression at the top of `score()`:

```python
    final = (
        WEIGHTS["retrieval_score"] * retrieval_score
        + WEIGHTS["legal_match"] * legal_match
    ) * grounding * min(1.0, max(0.0, scope_alignment)) * body_text
    caps = []
```

Keep all three cap blocks (`scope_flag`, `topical_ok`, `grounding_verified`) exactly as they are. Update the default note:

```python
    note = explanation or (
        f"0.40·ret({retrieval_score}) + 0.60·legal({legal_match}) "
        f"× ground({grounding}) × scope({scope_alignment}) × body({body_text})"
        + ("  [" + "; ".join(caps) + "]" if caps else "")
    )
```

In `backend/pipeline/mapping.py`, add the import:

```python
from . import retrieval_norm, snippet_quality
```

Normalise each indicator's candidates where the work list is built (replacing lines 524–528):

```python
            else:
                candidates = _diverse_shortlist(ind.indicator_id, provisions, eff_top_k,
                                                settings.retrieve_per_law_k, log)
        norms = retrieval_norm.rank_normalise([r.score for r in candidates])
        for r, rn in zip(candidates, norms):
            if grade_all or r.score >= min_retrieval:
                work.append((ind, r, rn))
```

Update `_grade`'s unpacking (line 530) to `ind, r, rn = item`, and in the `confidence.score(...)` call pass `retrieval_score=rn` in place of `r.score`, plus:

```python
            body_text=snippet_quality.body_text_score(prov.verbatim_snippet),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_confidence.py tests/test_retrieval_norm.py tests/test_snippet_quality.py -v`
Expected: PASS — 10 confidence tests including the 5 pre-existing ones

- [ ] **Step 5: Run the full suite for regressions**

First record the pre-change baseline if it is not already known:

```bash
git stash && pytest tests/ -q | tail -3 && git stash pop
```

Run: `pytest tests/ -q`
Expected: no new failures against that baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/confidence.py backend/pipeline/mapping.py tests/test_confidence.py
git commit -m "confidence: three of four signals were constants — blend the two that vary, gate on the rest"
```

---

### Task 6: Localise the topical guard for non-Latin script

`topical_grounded()` (`confidence.py:62-73`) exempts any snippet under 85% ASCII, because `_PILLAR_CONCEPT_TERMS` is English-only. So the guard that produced real quarantines for AU/SG/MY is **switched off entirely for CN and MN** — exactly the economies where a weak grader is most likely to invent a reading. Native statutory vocabulary already exists in `backend/rdtii/query_terms_i18n.py`.

**Files:**
- Modify: `backend/pipeline/confidence.py` (`topical_grounded`, plus a `_native_concept_terms` helper)
- Test: `tests/test_confidence.py`

**Interfaces:**
- Consumes: `backend/rdtii/query_terms_i18n.py` — **read this module first**; use its existing per-language structure rather than introducing a second vocabulary source.

- [ ] **Step 1: Read the existing native vocabulary**

Run: `python -c "import backend.rdtii.query_terms_i18n as Q; print([n for n in dir(Q) if not n.startswith('_')])"`

Use whatever mapping it exposes. Do not duplicate its terms into `confidence.py`.

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_confidence.py
def test_topical_gate_now_judges_chinese():
    """A Chinese cross-border provision passes on native vocabulary, not the ASCII exemption."""
    assert C.topical_grounded("个人信息不得出境，应当在中华人民共和国境内存储。", 6) is True


def test_topical_gate_fails_offtopic_chinese():
    """Chinese boilerplate with no P6 concept vocabulary must now FAIL — before this change the
    non-Latin exemption passed every Chinese snippet unconditionally."""
    assert C.topical_grounded("本法自公布之日起施行。", 6) is False


def test_topical_gate_fails_offtopic_mongolian():
    assert C.topical_grounded("Энэ хууль батлагдсан өдрөөс эхлэн хүчин төгөлдөр болно.", 6) is False


def test_topical_gate_exempts_unsupported_script():
    """Thai has no native vocabulary yet; it must stay exempt rather than fail everything."""
    assert C.topical_grounded("พระราชบัญญัตินี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ", 6) is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_confidence.py -k topical -v`
Expected: FAIL on `test_topical_gate_fails_offtopic_chinese` and `..._mongolian` — both currently return `True` via the ASCII exemption.

- [ ] **Step 4: Write minimal implementation**

Replace `topical_grounded()`:

```python
def topical_grounded(snippet: str, pillar: int | None) -> bool:
    terms = _PILLAR_CONCEPT_TERMS.get(pillar)
    if not terms or not snippet:
        return True
    low = snippet.lower()
    if sum(c.isascii() for c in low) / max(len(low), 1) >= 0.85:
        return any(t in low for t in terms)
    native = _native_concept_terms(pillar, low)
    if native is None:
        return True          # script has no vocabulary yet — exempt rather than fail-closed
    return any(t in low for t in native)
```

Add `_native_concept_terms(pillar, text)` returning the concept terms for the snippet's detected script from `query_terms_i18n`, or `None` when that script is unsupported. Detect script by unicode range (Han, Cyrillic) — `retrieval._tok` already performs this detection; reuse it if importable rather than writing a second copy.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_confidence.py -v`
Expected: PASS — all 14 tests

- [ ] **Step 6: Confirm it does not mass-quarantine the real CN/MN runs**

```bash
python -c "
import json
from backend.pipeline import confidence as C
for e,f in [('CN','outputs/rt_check/CN_P67_20260825-040610.json'),
            ('MN','outputs/rt_check/MN_P67_20260825-041235.json')]:
    ms=[m for m in json.load(open(f,encoding='utf-8'))['mappings'] if m.get('confidence_breakdown')]
    fail=sum(1 for m in ms if not C.topical_grounded(m['verbatim_snippet'], int(m['pillar'])))
    print(f'{e}: {fail}/{len(ms)} snippets would now fail the topical gate')
"
```

Expected: a minority. If it fails more than ~30%, the native vocabulary is too narrow — widen it from `query_terms_i18n`; do not relax the gate.

- [ ] **Step 7: Commit**

```bash
git add backend/pipeline/confidence.py tests/test_confidence.py
git commit -m "confidence: the topical guard was disabled for exactly the economies that need it most"
```

---

### Task 7: Recalibrate thresholds against AUC and record the measured values

Thresholds are `conf_auto_accept = 0.85` / `conf_review_floor = 0.60` (`config.py:202-203`), chosen for the old distribution. The new blend has a different one, so they must be re-derived by measurement, per CLAUDE.md §7 — not by taste.

**Files:**
- Create: `tools/calibrate_confidence.py`
- Modify: `backend/config.py:202-203`
- Modify: `docs/superpowers/plans/2026-09-06-veritrade-confidence-retrieval-fix.md`

**Interfaces:**
- Consumes: `backend.eval.confidence_eval.auc` / `label_runs` / `load_key` (Task 1)

- [ ] **Step 1: Write the calibration tool**

```python
# tools/calibrate_confidence.py
"""Pick routing thresholds from the score distribution, and report the AUC they sit on."""
from __future__ import annotations

import argparse

from backend.eval.confidence_eval import auc, label_runs, load_key


def main(pattern: str) -> None:
    labelled = label_runs(pattern, load_key())
    print(f"AUC = {auc(labelled)}   (baseline 0.458; P0 gate >= 0.70)")
    scores = sorted(s for s, _ in labelled)
    for name, q in (("conf_review_floor", 0.25), ("conf_auto_accept", 0.75)):
        print(f"{name:20} {scores[int(q * (len(scores) - 1))]:.3f}   (q={q})")
    total_pos = max(1, sum(y for _, y in labelled))
    for t in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        keep = [(s, y) for s, y in labelled if s >= t]
        if not keep:
            continue
        hits = sum(y for _, y in keep)
        print(f"  t={t:.2f}  kept={len(keep):4d}  precision={hits / len(keep):.3f}  "
              f"recall={hits / total_pos:.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="outputs/rt_check/*.json")
    main(ap.parse_args().glob)
```

- [ ] **Step 2: Re-run the six economies with the new scoring**

The scores in `outputs/rt_check/` came from the old formula, so calibration needs fresh traces:

```bash
python batch_run.py --economies Singapore Australia Malaysia China India Mongolia --pillar 6 7 --live
```

Expected: 6 new JSON traces. If a live portal is down, note which economy is missing and calibrate on the rest — do **not** substitute the stale `rt_check` traces, whose `confidence_score` is from the old formula.

- [ ] **Step 3: Run the calibration**

Run: `python tools/calibrate_confidence.py --glob "outputs/<new-run-glob>.json"`

- [ ] **Step 4: Check the P0 gate**

**AUC must be >= 0.70.** If it is not, P0 has not met its goal — do not proceed to P1, and do not paper over it by moving thresholds. Use the per-threshold precision/recall table to find which of Tasks 2–6 failed to contribute, and fix that.

- [ ] **Step 5: Write the measured thresholds into config**

Set `conf_auto_accept` and `conf_review_floor` in `backend/config.py:202-203` to the printed values. Record the measured AUC, the thresholds, and the resulting auto%/pend%/quar% per economy in the commit message.

- [ ] **Step 6: Record the result in the master plan**

Append the measured numbers under the master plan's "Measured Baseline (2026-09-06)" section as an "After P0" row, so the before/after pair sits in one place.

- [ ] **Step 7: Commit**

```bash
git add tools/calibrate_confidence.py backend/config.py docs/superpowers/plans/
git commit -m "confidence: recalibrate routing thresholds on the redesigned score (AUC 0.458 -> <measured>)"
```

---

## Definition of Done

- [ ] `pytest tests/ -q` — no new failures; the 5 pre-existing `test_confidence.py` tests still pass
- [ ] `python -m backend.eval.confidence_eval` reports **AUC >= 0.70** on fresh traces
- [ ] The quarantine band is reachable by the weighted sum alone, not only by caps — proven by `test_quarantine_band_is_reachable_by_the_weighted_sum`
- [ ] `python main.py --economy Singapore --pillar 6` (offline sample mode) produces the same CSV as before this plan
- [ ] Submission CSV still has 14 columns + 2 translation columns, unchanged
- [ ] Every new threshold traces to a script's output recorded in a commit message

## Out of Scope (deliberately deferred)

- Retrieval budget / shortlist sizing, amending-instrument filtering, IN section-unit capping — **P1**
- Grader prompt discrimination between adjacent indicators, `excludes` fields, cross-check panel — **P2**. P0 raises the *measurability* of P2: once confidence discriminates, adjacency confusion becomes visible in the AUC breakdown.
- MY robots.txt carve-out, CN mirror resilience, mock-grader production guard — **P3**
- Turning confidence into a calibrated probability — P0 targets *ranking* (AUC), not calibration

## Self-Review

**Spec coverage.** Master-plan P0 rows map as: P0.1 → Task 1; P0.1b → Task 2; P0.2 → **deferred, see below**; P0.3 → Task 4; P0.3b → Task 3; P0.4 → Task 6; P0.5 → tests inside every task.

**Known gap — P0.2 (per-indicator gates).** The master plan asked for per-indicator acceptance gates for the checkable indicators (P6-I1, P6-I4, P7-I4). No task here implements them, deliberately: with AUC at 0.458 there is no evidence about *which* indicators are misrouted, so per-indicator thresholds would be six hand-tuned constants with nothing to fit them to — the exact practice CLAUDE.md §7 forbids. Task 7 produces that evidence. **Decide P0.2 after Task 7**, and only if the breakdown shows per-indicator variance worth fitting.

**Type consistency.** `rank_normalise` (Task 2) is consumed in Task 5 under the same name; `body_text_score` (Task 3) is consumed in Task 5 as `body_text=`; `grounding_verified` (Task 4) keeps one spelling across `score()`, `ConfidenceBreakdown`, and `mapping.py`. `ConfidenceBreakdown` gains exactly two fields, both with defaults, so every existing construction site and stored trace stays valid.

**Ordering risk.** Task 5 changes `work` from a 2-tuple to a 3-tuple. `_grade` is the only consumer (`mapping.py:530`), but grep for other unpackings of `work` before editing.

**The 0.70 gate is a target, not a projection.** Nobody has yet measured what AUC this design achieves — that is what Task 7 is for. What *is* measured is that the current design cannot discriminate at all (0.458) and why (three constant terms). If Task 7 lands between 0.55 and 0.70, that is real progress on a broken baseline and the right response is to find the next dead signal, not to lower the gate quietly: record the measured value, say so, and decide with the user whether to continue into P0.2 or move to P1.

**Label-noise caveat.** NOT-IN-KEY is not a pure false-positive set: the key is at law+indicator granularity and 10 of the 37 laws it cites are outside our catalogue (CLAUDE.md §4), so some not-in-key rows are correct-but-unlisted. The 0.70 gate is set with that headroom in mind; an AUC of 1.0 is not achievable against this label set and should not be chased.
