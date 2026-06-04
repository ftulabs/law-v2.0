# VeriTrade — Live Demo Script (≈6 minutes)

Goal: show an **auditable** pipeline, not a chatbot. The throughline is *traceability* —
every claim ends at verbatim source text + a confidence the reviewer can interrogate.
Runs fully offline in mock mode, so nothing depends on the venue Wi-Fi.

## 0 · Setup (before you present)
```bash
pip install -r requirements.txt
cp .env.example .env            # leave providers as mock for the live run
```

## 1 · The problem (30s, no terminal)
"RDTII scoring needs a human to read statutes and cite the exact provision. It's slow
and hard to audit. VeriTrade automates the evidence extraction *while keeping the
audit trail* — discover → extract (incl. scanned PDFs) → map → score → human review."

## 2 · Run the pipeline (60s)
```bash
python -m backend.cli run-pipeline --economy SG --pillar 6 --pillar 7 --use-samples
```
Narrate the live log:
- `[providers] OCR=markitdown LLM=mock` — **Microsoft MarkItDown is the default engine**.
- `[discovery]` — found the PDPA, Cybersecurity Act and the MAS notice; one AU doc is tagged **NEW**.
- `[done] … auto=… review=… quarantine=…` — confidence routed every mapping.

Point at the table: auto-accepted rows map to the **official RDTII codes** — s13 → P7-I1
(legal basis), s18 → P7-I2 (purpose), s21/s22 → P7-I3 (data subject rights), s26D → P7-I4
(breach), s48J → P7-I5 (enforcement), s26 → P6-I1 (cross-border), s26A → P6-I3 (contractual).

Then run Australia to show **MarkItDown extracting a real PDF**:
```bash
python -m backend.cli run-pipeline --economy AU --pillar 6 --pillar 7 --use-samples
```
The AU Privacy Act ships as a real PDF — the JSON shows `"ocr_quality":{"provider":"markitdown",...}`.

## 3 · Disambiguation + scope guard (60s) — the money moment
"The official indicators are deliberately close — a default cross-border RESTRICTION
(P6-I1) vs the consent/adequacy/contract EXCEPTIONS (P6-I4/I2/I3); a basis-to-process duty
(P7-I1) vs purpose limitation (P7-I2). Naive mappers smear one provision across all of
them." VeriTrade shows the model every sibling indicator and asks for the BEST fit, then
drops the rest. Two guards to show:
```bash
python -c "import json,glob;d=json.load(open(sorted(glob.glob('outputs/*.json'))[-1],encoding='utf-8'));[print(m['indicator_id'],m['scope_flag'],m['confidence_score'],m['review_status']) for m in d['mappings'] if m['scope_flag']]"
```
- **Scope guard**: the sectoral MAS notice is flagged `SECTORAL_NOT_NATIONAL`, capped at
  0.55, **quarantined** — it never enters a national-indicator submission.
- **No over-mapping**: a security or localisation clause that fits *none* of the 10
  official indicators produces **no row** — the system declines rather than guesses.

## 4 · The dashboard (2 min)
```bash
streamlit run frontend/app.py
```
- **Evidence tab** — confidence bars colour-coded to the routing bands; toggle *Only scope-flagged*.
- **Audit detail tab** — pick a mapping → show the **verbatim snippet**, source URL,
  **confidence breakdown** (the 4 signals), **OCR metrics**, and **retrieval log**.
  "Every number is explained; every quote is grounded in source text."
- **Review queue tab** — approve one item with a note; reopen the JSON/`review_log`
  to show the human decision was recorded with before/after state.

## 5 · The outputs (45s)
"Two artefacts, two audiences."
- `outputs/veritrade_<run>.csv` → legal reviewers (verbatim, citation, rationale, confidence).
- `outputs/veritrade_<run>.json` → technical reviewers (timings, OCR quality, raw context, model version, retrieval logs).

## 6 · Modularity close (30s)
"Nothing is hardcoded." Show the dashboard **Engines** panel (or `.env`):
```
OCR_PROVIDER=markitdown       # default · or tesseract / paddle / azure
LLM_PROVIDER=anthropic        # or openai  (paste a key in the sidebar to go live)
```
"Judges pick the OCR engine and LLM right in the sidebar — MarkItDown extraction is the
default, and the same audit trail holds whichever engine runs."

---

## Backup one-liners
```bash
python -m backend.cli discover --economy AU --pillar 6          # Zone 1 only, see NEW tag
python -m backend.cli runs                                      # list past runs
python -m backend.cli export --run <run_id> --format both       # re-export
uvicorn backend.main:app --reload                               # API at /docs
```

## If asked "is the mapping real or hallucinated?"
Open Audit detail → `snippet_grounding = 1.0` means the cited quote is an exact
substring of the source text. The model is never allowed to supply law text, article
numbers, or URLs — those come from extraction. Grounding < 1.0 lowers confidence
automatically.
