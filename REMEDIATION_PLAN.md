# VeriTrade — Remediation Plan (handoff for a fresh Claude session)

> **How to use this file:** You are picking up the VeriTrade codebase mid-build. Read §0
> (orientation) and §1 (constraints) first — they contain context you cannot infer from the
> code alone. Then execute the tasks in §3, in order A → B → C, one item at a time: implement,
> run the item's *Verify* command, confirm its *Acceptance* criteria, then move on. Do **not**
> batch-commit; the human commits when asked. Update the checkboxes as you finish.
>
> This plan was written 2026-06-22 after re-reading the official hackathon docs end-to-end. If
> anything here contradicts the current code, **trust the code + the official docs** (§2) and
> note the discrepancy — memories/plans are point-in-time.

---

## §0 — Orientation (what this project is)

**VeriTrade** is Team FTU's entry to the **UN ESCAP Global Hackathon on AI for Digital Trade
Regulatory Analysis (RDTII 2.1)**. Round 1 deadline **20 July 2026**; mandatory economies
**Singapore (SG), Australia (AU), Malaysia (MY)**; mandatory pillars **6** (cross-border data)
and **7** (domestic data protection).

**The task the tool automates:** given `(economy, pillar)` with **zero seed URLs**, it must
(Zone 1) discover relevant laws on live government portals, (Zone 2) extract clean article-level
text from HTML / text-PDF / scanned-PDF and map each provision to an RDTII indicator with a
verbatim snippet + citation, and output a CSV/JSON. **Zone 3 (scoring) is OPTIONAL → extra
points** and is now implemented (see §0.3).

**Run it:**
```bash
# offline sample (reproducible, no key):
python main.py --economy Singapore --pillar 6
# live crawl (scored path):
python main.py --economy Singapore --pillar 6 --live --llm openrouter
# dashboard:
streamlit run frontend/app.py
# tests:
python -m pytest tests/        # full suite currently green (113 passed)
```
`.env` (gitignored) holds `OPENROUTER_API_KEY` and `SERPER_API_KEY`. With no key the pipeline
falls back to the deterministic **mock** LLM/OCR so it always runs.

### §0.1 Pipeline & key modules
```
(economy, pillar)
  → Zone 1 discovery  backend/pipeline/discovery.py, zone1.py, data/sources.yaml
  → fetch             backend/pipeline/fetch.py, scrapling_fetch.py, browser_fetch.py
  → Zone 2 OCR/extract backend/pipeline/ocr.py, extraction.py, providers/ocr_*.py
  → Zone 2 retrieval  backend/pipeline/retrieval.py (BM25+dense+rerank)
  → Zone 2 mapping    backend/pipeline/mapping.py (one LLM call per (indicator,provision))
  → Zone 3 scoring    backend/pipeline/scoring.py (one LLM call per measure) — OPTIONAL
  → export            backend/export/csv_export.py, json_export.py, scored_export.py
  orchestrated by     backend/pipeline/orchestrator.py ; CLIs: main.py, backend/cli.py
  schemas             backend/schemas.py ; indicators+rubric backend/rdtii/
  config              backend/config.py (pydantic-settings; env-overridable)
  frontend            frontend/app.py (Streamlit; "Legal Dossier" aesthetic)
```

### §0.2 RDTII indicators (the 9 we extract; output ids P6-I1..I4, P7-I1..I5)
Defined in `backend/rdtii/indicators.py` (`legal_test` + `query_terms` per indicator).
- **P6** (localisation): I1 ban/local-processing · I2 local storage · I3 infrastructure · I4 conditional-flow.
- **P7** (framework): I1 comprehensive data-protection framework · I2 **dedicated cybersecurity** ·
  I3 minimum retention duration · I4 DPO/DPIA · I5 government access.
- **GOTCHA:** `OUTPUT_TEMPLATE_31MAY.xlsx` "Indicator Reference" sheet mislabels these with GDPR
  names (P7-I2 as "purpose limitation"). **Ignore that sheet.** The scored answer key in
  `ESCAP-RDTII-2.1_ Round 1 Database.xlsx` uses the localisation/framework definitions above.

### §0.3 Zone 3 scoring — already built (context you need)
- Rubric (0/0.5/1 per indicator, verbatim from `Scoring_information_2.xlsx`): `backend/rdtii/scoring_rubric.py`.
- Scorer (LLM + deterministic mock + indicator roll-up): `backend/pipeline/scoring.py`.
- Mock scorer path: `_mock_score` in `backend/providers/llm_factory.py` (dispatched on the
  `<SCORE_INDICATOR>` tag in the prompt).
- Schema fields `raw_score`, `impact` on `EvidenceMapping` (`backend/schemas.py`).
- Scored CSV (Database shape): `backend/export/scored_export.py`. Toggle `SCORING_ENABLED` (default True).
- Frontend: ink "rubber-stamp" score badge + "Indicator scorecard" strip + scored-CSV download.
- Tests: `tests/test_scoring.py`.
- **Score = restrictiveness / compliance cost (0=simplified … 1=heavily regulated)**, NOT
  "did we find a law". **P7-I1 & P7-I2 polarity is INVERTED**: finding a comprehensive/dedicated
  *horizontal* framework scores **0**, sectoral-only 0.5, none 1. Validated vs the answer key
  (SG/MY/AU 7.1=0; SG/MY 7.2=0; AU 7.2=0.5).

---

## §1 — Hard constraints (do not violate)

1. **No hardcoded answers.** Never inject specific law *names* or seed URLs as the "answer" to
   `(economy, pillar)` in discovery keywords / `query_terms` / `sources.yaml`. Discovery must be
   generic and live. This is a scored anti-pattern.
2. **The 13-column submission CSV is sacred.** `SUBMISSION_COLUMNS` in `backend/schemas.py` must
   match `OUTPUT_TEMPLATE_31MAY.xlsx` ("Output Data" sheet) **exactly** — judges validate
   programmatically. Do **not** add/rename/reorder columns. Extra data (pillar, coverage, score,
   OCR/CER) goes in the JSON or the *separate* scored CSV, or the optional **Notes** column.
3. **Verbatim snippets are exact** — never paraphrase. Citations come from extraction, never
   generated by the LLM (anti-hallucination control).
4. **All UI / CSS / frontend work must go through the `frontend-design` skill.** Preserve the
   "Legal Dossier" aesthetic (Fraunces/Newsreader/IBM Plex Mono, parchment, verdict palette
   forest/ochre/oxblood). The Zone-3 score badge is deliberately INK-toned (a different axis from
   the confidence verdict) — keep that separation.
5. **Per-country extraction is intentional** — SG/MY are numbered-only, AU is font-marked. Don't
   try to unify them into one regex. See `backend/pipeline/extraction.py` and the per-country branches.
6. **`.env` is gitignored** — never commit keys. Commit/push/deploy only when the human asks.
7. **Jetson deploy pins** `torch==2.2.2` → `requirements.txt` caps `transformers<5`, `numpy<2`.
   Keep those caps when pinning (§3 C2).

---

## §2 — Source-of-truth documents (in repo root)

| File | What it authoritatively defines |
|---|---|
| `Hackathon Overview-Dr.Witada A.pdf` | Scoring weights, deliverables, what "runs" means, recommended output schema |
| `OUTPUT_TEMPLATE_31MAY.xlsx` → **Instructions** sheet | How to fill every field; "one row per provision"; field REQUIRED/OPTIONAL |
| `OUTPUT_TEMPLATE_31MAY.xlsx` → "Output Data" sheet | The exact 13 columns + REQUIRED/OPTIONAL row |
| `ESCAP-RDTII-2.1_ Round 1 Database.xlsx` | **Reference-only** answer key (per-economy scored rows). NOT the submission format. |
| `Scoring_information_1.pdf` | Zone-3 scoring FAQ (6.1 vs 6.4, infra, comprehensive, min retention) |
| `Scoring_information_2.xlsx` | Zone-3 scoring criteria table (0/0.5/1 per indicator) |
| `CLAUDE.md` | Project guide / status (keep it honest & current) |

**Scoring weights (Overview):** 40% Substantive Accuracy (framework alignment + **NEW evidence =
20/40** + citation fidelity) · 30% Technical Resilience (live crawling PASS/FAIL · OCR CER<5% ·
end-to-end no manual steps) · 30% Architecture (modular backend · audit trail · cost-efficiency).

**Two facts that reframe the plan (established this session):**
- The Instructions sheet says **"One row per provision … If one article maps to two indicators,
  create two rows."** → scoring is **per-measure**, independent. There is **no** indicator-level
  roll-up in the submission. The Database's one-score-per-indicator is reference-only.
- The output template has **no score column**. To earn Zone-3 extra points, the score must travel
  in the optional **Notes** column (visible to the policy judge in Excel) and/or the JSON / scored
  CSV — never by adding a column to the 13-col CSV.

---

## §3 — Tasks (execute A → B → C, one at a time)

### PHASE A — Substantive Accuracy (40 pts; highest leverage)

- [x] **A1 — Citation fidelity: paragraph-level article refs**
  - **Why:** Overview slide 8 deducts points for `Section 26` (low traceability) vs `Section 26(2)`.
    Instructions: "Include article number AND paragraph … never write just 'Art. 26'."
  - **Current state:** `backend/pipeline/extraction.py:560-564` already appends a leading
    subsection marker, but only when the section body *starts* with `(1)`. SG bodies like
    `26.—(1)` are often preceded by a title line, so the marker is missed → output shows `Section 26`.
  - **Do:** (a) detect the first subsection marker in the body even when a heading precedes it;
    append it **only when the snippet's operative text begins in that subsection** (do NOT tag
    `(1)` on a snippet that spans the whole multi-subsection section — that would be a *wrong*
    narrower citation). (b) Where a section maps to an indicator via one specific subsection, let
    the citation reflect that subsection. Keep snippets verbatim and unchanged.
  - **Files:** `backend/pipeline/extraction.py` (label build ~L546-566, `_normalise_label`).
  - **Verify:** `python main.py --economy Singapore --pillar 6 --llm mock` then inspect the CSV's
    `Article / Section` column.
  - **Acceptance:** ≥80% of SG/MY P6/P7 rows cite to subsection level (e.g. `Section 26(2)`); no
    whole-section snippet is mislabeled with a single subsection; tests stay green.

- [x] **A2 — Audit & harden NEW/KNOWN tagging (worth 20/40)**
  - **Why:** "NEW evidence … the single largest scoring differentiator." Over-tagging a
    self-discovered law as KNOWN throws away the 20 points; under-tagging mislabels sample-kit laws.
  - **Current state:** `backend/pipeline/sample_kit.py` `is_known()` matches a produced mapping to
    the sample kit by URL key **or** law-name token overlap, per (economy, pillar). Review the
    token-overlap threshold (~L93-103) — confirm it can't fire on a merely-similar NEW law.
  - **Do:** Tighten to a confident match (URL-key match, or high token overlap **plus** matching
    law number where available). Then run `--live` for SG/AU/MY and confirm real NEW provisions appear.
  - **Files:** `backend/pipeline/sample_kit.py`; tagging call in `backend/pipeline/orchestrator.py`
    (~L211-222).
  - **Verify:** `python main.py --economy Malaysia --pillar 7 --live --llm openrouter` and check the
    KNOWN/NEW split in the log + CSV `Discovery Tag`.
  - **Acceptance:** each live economy yields ≥1 valid NEW row; no law absent from the sample kit is
    tagged KNOWN; sample-kit example laws are tagged KNOWN.

- [x] **A3 — Place the Zone-3 score correctly (demote roll-up, embed in Notes)**
  - **Why:** §2 — submission is per-measure; the indicator roll-up is not a submission artifact;
    the template has no score column, so the score belongs in **Notes** (primary CSV, policy judge)
    + JSON, with the scored CSV as a supplementary demo artifact.
  - **Do:** (a) Prepend the score to the official CSV's **Notes** field, e.g.
    `"RDTII score 1 (heavy): <one-line impact>. "` + existing OCR/scope notes — implemented in
    `backend/export/csv_export.py` `_row()` (read `m.raw_score`, `m.impact`); keep within the
    existing Notes column, do not add a column. (b) Demote the roll-up: drop the
    "INDICATOR SCORES" footer from `scored_export.py`; in `json_export.py` move it under an
    `analytical_index` key clearly labelled "not part of the submission (RDTII index computation)".
    Keep `aggregate_indicator_scores` (still correct: max for normal, **min** for inverted 7.1/7.2).
  - **Files:** `backend/export/csv_export.py`, `backend/export/scored_export.py`,
    `backend/export/json_export.py`. Update `tests/test_scoring.py` + `tests/test_output.py`.
  - **Verify:** `python main.py --economy Singapore --pillar 7 --llm mock`; check CSV `Notes` has the
    score, CSV still has exactly 13 columns, JSON has `analytical_index`.
  - **Acceptance:** 13-col CSV byte-structure unchanged (header identical); Notes carries score+impact;
    scored CSV has no roll-up footer; tests green.

- [x] **A4 — Required fields per Instructions**
  - **Why:** `Last Amended` is REQUIRED (must never be blank); `Location Reference` for PDFs should
    be a real page number (HTML anchor is fine).
  - **Do:** Ensure `last_amended` is always populated (amendment year → else enactment year → else a
    Notes flag explaining absence). Ensure PDF-sourced provisions get a page number in `location_ref`
    (`_location_ref` in `extraction.py`, OCR page metadata).
  - **Files:** `backend/pipeline/extraction.py` (`_location_ref`, `_mk`), possibly `discovery.py`
    (amendment_date), `csv_export.py`.
  - **Verify:** inspect CSV `Last Amended` (no blanks) and `Location Reference` (PDF rows show `p. N`).
  - **Acceptance:** 0 blank `Last Amended` in a submission run; PDF rows carry a page number.

### PHASE B — Technical Resilience (30 pts; live demo is a PASS/FAIL gate)

- [ ] **B1 — Live crawl end-to-end for SG/AU/MY, zero manual steps**
  - **Why:** Overview slide 9: "processes pre-downloaded PDFs only → 0 points for crawling." The
    3 Aug live demo must crawl live.
  - **Current state:** AU OData JSON API works; MY uses the portal's own DataTables JSON catalogues
    (`json-updated-2024.php`, `json-amendment-2024.php`) + pdp.gov.my web search; SG via web search.
    SG token-AJAX and MY DataTables may need Playwright escalation (CLAUDE.md flags this as un-QA'd).
  - **Do:** QA `--live` for each economy; wire/verify Playwright auto-escalation in
    `backend/pipeline/browser_fetch.py` / `scrapling_fetch.py` for JS-gated fetches; confirm graceful
    fallback + clear logging when a portal is down. Do NOT add seed URLs (constraint §1.1).
  - **Files:** `backend/pipeline/discovery.py`, `fetch.py`, `scrapling_fetch.py`, `browser_fetch.py`,
    `data/sources.yaml`.
  - **Verify:** `python main.py --economy Australia --pillar 6 --live --llm openrouter` (repeat MY, SG).
  - **Acceptance:** all three economies complete crawl→extract→map live with no manual intervention;
    a down portal degrades gracefully (logged, not a crash).

- [ ] **B2 — Validate CER on a real scanned gazette (beyond the bundled sample)**
  - **Why:** OCR PASS requires CER<5% on real image PDFs; only the bundled sample (1.11%) is proven.
  - **Do:** Run RapidOCR/Paddle on ≥1 real scanned legal PDF, measure CER, record in JSON
    (`ocr_quality_cer`). Optionally use Azure Document Intelligence as a ground-truth baseline.
  - **Files:** `backend/pipeline/ocr.py`, `cer.py`, `providers/ocr_*.py`.
  - **Verify:** run on the scan, read `ocr_reports[].cer` in JSON.
  - **Acceptance:** a measured CER <5% on a non-bundled real scan, reported in JSON.

### PHASE C — Architecture & submission hygiene (30 pts + reviewer interop)

- [x] **C1 — `run.py --country` entrypoint alias**
  - **Why:** Overview's canonical command is `python run.py --country SG --pillar 6`; Deliverable #1
    is "stress test with the reviewer API/Script" — an automated reviewer may call exactly this.
  - **Do:** Add a thin `run.py` at repo root that forwards to the same pipeline as `main.py`,
    accepting `--country` (alias of `--economy`) and `--pillar`. Keep `main.py` working too.
  - **Verify:** `python run.py --country SG --pillar 6` produces the same outputs as `main.py`.
  - **Acceptance:** both entrypoints work; `--country` accepted.

- [ ] **C2 — Pin `requirements.txt` (no "latest")**
  - **Why:** Overview Deliverable #1 / README mandates pinned versions.
  - **Do:** Convert `>=` to exact `==` from the working environment (`pip freeze` as reference),
    **keeping** the Jetson caps `transformers<5`, `numpy<2`, and the torch comment.
  - **Verify:** `pip install -r requirements.txt` in a clean venv resolves; tests still green.
  - **Acceptance:** every runtime dep pinned to `==`; Jetson caps preserved.

- [x] **C3 — README mandatory sections** (Overview slide 13)
  - **Do:** Ensure `README.md` has: project name + one-line description; **Setup** (3-5 lines);
    **Run** (one command); **Outputs** (csv/json/scored csv/logs); **Pinned versions**;
    **Open-source fallback** (point at the local/Ollama provider — already in
    `backend/providers/llm_local.py`, and mock OCR/LLM).
  - **Verify:** a newcomer can clone → install → run in one command following only the README.
  - **Acceptance:** all mandatory sections present and accurate.

- [ ] **C4 — Cost-efficiency reporting**
  - **Why:** Architecture block scores "your actual operational cost."
  - **Do:** Run `python tools/cost_logger.py …`, capture wall-clock + token cost per document, and
    surface the number in the README and/or JSON run metadata.
  - **Verify:** `logs/cost_report.json` populated; README cites a per-document cost.
  - **Acceptance:** a real measured cost figure is documented.

---

## §4 — Out of scope for this pass (note, don't build)
- Mock grader is lexical-only (can confuse close indicators) — mitigated by using a real LLM for
  submissions; do not over-invest in the mock.
- Full human-review UI (the `backend/review/workflow.py` data layer exists; the dashboard review
  tab is minimal). Audit-trail requirement is already met (verbatim snippet in every row).
- Multilingual cross-encoder reranker (`BAAI/bge-reranker-v2-m3`) — a Finals concern
  (China/Russia/Lao/Mongolia), not Round 1 (SG/AU/MY are English/Malay).
- Pitch deck + screen-recording video — the human will produce these after the product stabilises.

## §5 — Definition of done for the whole plan
All A/B/C checkboxes ticked; `python -m pytest tests/` green; a live `--live` run for SG, AU, MY
each produces a 13-column CSV (with score in Notes) + JSON (+ scored CSV) with ≥1 NEW row and no
blank required fields; README lets a cold reviewer run the tool in one command. Then tell the
human; they decide on commit/deploy.
