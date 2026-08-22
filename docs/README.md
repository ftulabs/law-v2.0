# VeriTrade — documentation

Start at the [repository README](../README.md); it is the front door and links here for depth.

| Doc | What it covers |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **System design.** Part I orients a new contributor with diagrams — the whole system, the fetch/read seam, adding an economy, adding an engine, confidence routing, a module map. Part II is the reference: schemas, the CSV and JSON contracts, and why the confidence weights are 0.40 / 0.25 / 0.20 / 0.15 and the floor is 0.60. |
| [`CRAWLING.md`](CRAWLING.md) | **Politeness and robots.txt.** What each live-test portal's robots file actually says, why user-agent group selection has to be exact (Indonesia turns on it), and the four conditions under which the TLS allowlist is defensible. |
| [`OCR_LANGUAGE_EVIDENCE.md`](OCR_LANGUAGE_EVIDENCE.md) | Per-language OCR evidence, separating what was measured from what is only documented from what is a gap. Includes the character-dictionary measurements that disqualify PaddleOCR for Vietnamese, Mongolian and Kazakh. |
| [`retrieval-redesign.md`](retrieval-redesign.md) | How the retrieval parameters were swept against the panel's own database, and two counter-intuitive results recorded so they are not re-litigated. |
| [`round2-expansion.md`](round2-expansion.md) | Multilingual expansion — script-aware tokenisation, per-economy article boundaries, and the grading prompt for non-English provisions. |
| [`AUTH_AND_DATABASE.md`](AUTH_AND_DATABASE.md) | Accounts and sessions, the SQLAlchemy storage layer, and the one env var that moves it to cloud Postgres. |
| [`NOTES_FOR_JUDGES.md`](NOTES_FOR_JUDGES.md) | Decisions a reviewer may want the reasoning for. |
| [`precompute-corpus.md`](precompute-corpus.md) | The precomputed corpus layers L0–L3. Paused, not deleted. |
| [`landing.html`](landing.html) · [`whitepaper.html`](whitepaper.html) | Public landing page and the interactive white paper. Served at `/app/static/` while the app is running. |

The panel's own material — the RDTII databases, the output templates, the framework
documentation — is deliberately **not** committed; see the note at the foot of `.gitignore`. The
artefacts derived from it are, and they are what the pipeline reads:
`data/rdtii/indicator_reference.json` and `data/ground_truth/rdtii_reference_p67.csv`.
- [coverage-and-blockers.md](coverage-and-blockers.md) — what runs today, what blocks the rest, and the query vocabulary counted per economy and pillar
