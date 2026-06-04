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
- `[discovery]` — found the PDPA, Cybersecurity Act, **and a scanned MAS notice**; one AU doc is tagged **NEW**.
- `[ocr] MAS Notice 655 via mock conf=0.94` — **the scanned-PDF branch ran**.
- `[done] … auto=… review=… quarantine=…` — confidence routed every mapping.

Point at the table: top rows are **auto-accepted** (PDPA s24 → P7.3 security, s26D → P7.4 breach,
s26 → P6.1 cross-border). Note a row with `(!)`.

## 3 · The scope-confusion guard (60s) — the money moment
```bash
python -m backend.cli review --queue
```
"Here's the trap every naive mapper falls into." Open the JSON and grep the MAS notice:
```bash
python -c "import json,glob;d=json.load(open(sorted(glob.glob('outputs/*.json'))[-1],encoding='utf-8'));[print(m['indicator_id'],m['scope_flag'],m['confidence_score'],m['review_status']) for m in d['mappings'] if m['scope_flag']]"
```
"A MAS financial-sector cyber-hygiene notice is **sectoral**. VeriTrade flags
`SECTORAL_NOT_NATIONAL`, caps the score at 0.55, and **quarantines** it — it never
gets mistaken for a national cybersecurity framework (P7.5)."

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
"Nothing is hardcoded." Show `.env`:
```
OCR_PROVIDER=tesseract        # or paddle / azure
LLM_PROVIDER=anthropic        # or openai
```
"Swap OCR or LLM providers with one line — same audit trail. Today's run used mock so
it's reproducible on this laptop; in production these become real engines."

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
