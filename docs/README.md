# VeriTrade — documentation

Start at the [repository README](../README.md): it is the handover document (Quick Start,
interface, engines, economies, output format, cost, limitations). The pages below go deeper.

## Run and deploy

| Doc | What it covers |
| :--- | :--- |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Clean-machine deployment: Python virtual environment or Docker, the configuration reference, what persists where, how the hosted instance is deployed, troubleshooting |
| [../INSTALL.md](../INSTALL.md) | Desktop installers for macOS, Windows and Linux, and how to get past the unsigned-app warnings |
| [AUTH_AND_DATABASE.md](AUTH_AND_DATABASE.md) | Accounts and sessions, the SQLAlchemy storage layer, and the one variable (`DATABASE_URL`) that moves it to Postgres |

## How it works

| Doc | What it covers |
| :--- | :--- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | **System design.** Part I: the whole system, the fetch/read boundary and the second pass, adding an economy or an engine, a module map. Part II: schemas, the CSV and JSON contracts, confidence scoring (why 0.40 / 0.25 / 0.20 / 0.15, 0.85 and 0.60). Part III: engine-choice evidence, OCR benchmarks, cost metering |
| [CRAWLING.md](CRAWLING.md) | Politeness and robots.txt: what each live-test portal's robots file says, and why user-agent matching has to be exact |
| [OCR_LANGUAGE_EVIDENCE.md](OCR_LANGUAGE_EVIDENCE.md) | Per-language OCR evidence, separating what was measured from what is only documented from what is a gap |
| [retrieval-redesign.md](retrieval-redesign.md) | How the retrieval parameters were swept against the panel's database, and two counter-intuitive results not to re-litigate |
| [round2-expansion.md](round2-expansion.md) | Multilingual expansion: script-aware tokenisation, per-economy article boundaries, the grading prompt for non-English provisions |

## Status and review

| Doc | What it covers |
| :--- | :--- |
| [coverage-and-blockers.md](coverage-and-blockers.md) | What runs today, what blocks the rest, and the query vocabulary per economy and pillar |
| [NOTES_FOR_JUDGES.md](NOTES_FOR_JUDGES.md) | Decisions a reviewer may want the reasoning for |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Third-party components and their licences |
| [examples/](examples/) | A sample submission CSV and evidence JSON (`example_SG.csv`, `example_SG.json`) |
| [landing.html](landing.html) · [whitepaper.html](whitepaper.html) | Public landing page and the interactive white paper, served at `/app/static/` while the app runs |

The panel's Round 1 and Round 2 databases and the Round 1 output template are in the repository
root. The finalist orientation pack (the final-round README and output templates, the slides) is
deliberately **not** committed — see `Finalist Orientation/` in `.gitignore`. What the pipeline
reads is derived from the databases: `data/rdtii/indicator_reference.json` and
`data/ground_truth/rdtii_reference_p67.csv`.
