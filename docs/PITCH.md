# VeriTrade — Pitch Deck Structure

11 slides, ~5 minutes. Keep the throughline: **auditable evidence, not a chatbot.**

---

### 1 · Title
**VeriTrade** — Auditable legal evidence extraction for UNESCAP RDTII 2.1.
Singapore · Australia · Malaysia · Pillars 6 & 7.
One line: *"We turn statutes into citation-grounded RDTII evidence a human can trust."*

### 2 · The problem
RDTII scoring is manual legal research: an analyst reads each statute, finds the exact
provision, cites it, judges relevance. Slow, inconsistent, **hard to audit**. Naive AI
makes it worse — it hallucinates law and confuses sectoral rules with national ones.

### 3 · The insight
The bottleneck isn't *generation*, it's *trust*. So build backwards from the audit
trail: every mapping must carry verbatim wording, article ref, source URL, raw context,
and an explainable confidence — or it doesn't ship.

### 4 · What it does (the 3 zones)
Discovery → Extraction & Mapping → Auditable output, over one audit store.
Handles HTML, text PDFs, **and scanned PDFs via OCR**. (Architecture diagram.)

### 5 · Live demo (the moment)
Run SG pillars 6+7. Show: scanned MAS notice OCR'd (conf 0.94); PDPA provisions
auto-accepted with correct indicators; **MAS notice flagged `SECTORAL_NOT_NATIONAL`
and quarantined** — the scope trap, caught automatically.

### 6 · How we reduce hallucination
- Retrieval-grounded: the model only sees retrieved verbatim snippets.
- Law text / article / URL are **carried, never generated**.
- `snippet_grounding` verifies the quote is an exact substring of source.
- Scope guard caps sectoral-vs-national mismatches below auto-accept.

### 7 · Confidence + human-in-the-loop
4-signal transparent score → auto-accept (≥0.85) / review (0.60–0.84) / quarantine.
Reviewers approve/reject/correct; every decision logged with before/after state.
*Humans spend time only where the machine is unsure.*

### 8 · Outputs for two audiences
CSV for legal/policy reviewers (verbatim + citation + rationale + confidence).
JSON for technical reviewers (timings, OCR quality, raw context, model version,
retrieval logs). Show a real exported row.

### 9 · Architecture & modularity
Python · FastAPI · Typer · Streamlit · SQLite audit store · BM25 retrieval.
**No provider hardcoded** — OCR (tesseract/paddle/azure) and LLM (anthropic/openai)
swap via `.env`. Runs fully offline in mock mode for reproducible demos.

### 10 · Roadmap
Live portal crawlers (Playwright) · dense hybrid retrieval (FAISS + RRF) ·
multilingual OCR for MY/TH scanned laws · reviewer accounts · all 7 pillars · more economies.

### 11 · Ask / close
"Auditable by construction. Every RDTII data point traces to the exact words of the
law." — call to action (pilot economies, data partners, judges' questions).

---

## Speaker notes
- Lead with the **scope-flag** demo — it's the most credible 'we understand legal
  nuance' signal and differentiates from a generic RAG chatbot.
- Say "evidence pipeline" not "assistant"; "grounded" not "generated".
- If pressed on accuracy: the system is designed to be *conservative* — it would
  rather quarantine for human review than auto-accept a wrong mapping.
