# VeriTrade — Auditable Legal Evidence Extraction Pipeline

> **Not a chatbot.** VeriTrade is an *auditable legal evidence extraction pipeline* that
> discovers official legal documents, extracts verbatim provisions (HTML / text PDF /
> scanned PDF + OCR), and maps them to **UNESCAP RDTII 2.1** indicators with citation
> grounding, confidence scoring, and human-in-the-loop review.

Scope economies: **Singapore · Australia · Malaysia**
Scope pillars: **Pillar 6 (cross-border data policies)** · **Pillar 7 (data protection & cybersecurity)**

---

## Why VeriTrade

Legal-research automation usually fails on *auditability*. A reviewer can't trust a mapping
they can't trace back to the exact statutory wording. VeriTrade is built backwards from the
audit trail: every RDTII mapping carries the **verbatim snippet**, **article/section**,
**source URL**, **raw retrieval context**, and a **confidence score** that routes it to
auto-accept, human review, or quarantine.

## Architecture (3 zones)

```
ZONE 1 — DISCOVERY            ZONE 2 — EXTRACTION & MAPPING        OUTPUT
┌──────────────────┐         ┌──────────────────────────────┐   ┌──────────────┐
│ portal crawlers  │         │ OCR (pluggable provider)     │   │ CSV (review) │
│ indicator search │ ──docs─▶│ provision extraction         │──▶│ JSON (tech)  │
│ relevance rank   │         │ retrieval-grounded mapping   │   │ audit store  │
│ KNOWN/NEW tag    │         │ confidence scoring           │   │ HITL queue   │
└──────────────────┘         └──────────────────────────────┘   └──────────────┘
        │                              │                                │
        └──────────────── SQLite audit store (every step logged) ───────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Quickstart

```bash
# 1. Install
python -m venv .venv && . .venv/Scripts/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure (optional — runs in mock mode with no keys)
cp .env.example .env

# 3. Run the end-to-end pipeline on the bundled sample corpus
python -m backend.cli run-pipeline --economy SG --pillar 7 --use-samples

# 4. Inspect structured outputs
ls outputs/            # veritrade_<run>.csv  veritrade_<run>.json

# 5. Launch the reviewer dashboard
streamlit run frontend/app.py

# 6. Or serve the API
uvicorn backend.main:app --reload
```

## CLI cheat-sheet

| Command | Purpose |
|---|---|
| `python -m backend.cli discover --economy SG --pillar 7` | Zone 1 only: find candidate laws |
| `python -m backend.cli extract --doc <id>` | Zone 2: OCR + extract provisions |
| `python -m backend.cli map --economy SG --pillar 7` | Map provisions → RDTII indicators |
| `python -m backend.cli run-pipeline --economy SG --pillar 7 --use-samples` | Full pipeline → CSV+JSON |
| `python -m backend.cli review --queue` | Show items awaiting human review |
| `python -m backend.cli export --run <id> --format csv` | Re-export a finished run |

## Outputs

- **CSV** (`outputs/*.csv`) — the **official RDTII submission format**: exact template
  columns/order, Economy as the UN name, `Indicator ID` as `P6-I1`, year-only
  `Last Amended`, 2-dp `Confidence`, verbatim snippets preserved. Rejected/quarantined
  rows are excluded by default (a sectoral mis-map never enters a national submission).
- **JSON** (`outputs/*.json`) — for technical reviewers: timings, OCR quality, raw
  context, retrieval logs, model versions, confidence breakdown, `source_pdf_path`.

Schemas: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#4-csv-schema--official-submission-template-policy-judge).

> **Submission note:** the bundled RDTII indicator codes are illustrative — confirm each
> `Indicator ID` against the official RDTII 2.1 codebook before submitting.

## Modularity — pick your engines

Two ways to choose OCR + LLM, no code changes:

1. **In the dashboard** (great for demos/judges): the sidebar **Engines** panel lets you
   pick the OCR engine and LLM, paste a model name + API key, and shows which engines are
   ready on this machine. Unavailable engines fall back to `mock` automatically so a run
   never breaks.
2. **Via `.env`** (default for CLI/API):
   - `OCR_PROVIDER=tesseract|paddle|azure|mock`
   - `LLM_PROVIDER=anthropic|openai|mock`

CLI flags also override per-run: `--ocr tesseract --llm anthropic --llm-model claude-opus-4-8`.
The API accepts the same on `POST /pipeline/run`; `GET /providers` reports availability.

## Project status

Hackathon MVP. Runs end-to-end offline (mock providers) so a live demo never depends on a
network call. Real providers activate automatically when keys are present.
