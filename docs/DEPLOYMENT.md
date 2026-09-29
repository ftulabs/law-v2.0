# Deploying VeriTrade

How to bring VeriTrade up on a clean machine, either directly in a Python virtual environment or
as a Docker container, and how the hosted instance at https://veritrade.ftu.fyi is deployed.

For the desktop installers (macOS, Windows, Linux) see [INSTALL.md](../INSTALL.md). For the
system design see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Contents

1. [Requirements](#1-requirements)
2. [Path A — Python virtual environment](#2-path-a--python-virtual-environment)
3. [Path B — Docker](#3-path-b--docker)
4. [Configuration reference](#4-configuration-reference)
5. [What persists, and where](#5-what-persists-and-where)
6. [The hosted instance](#6-the-hosted-instance)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Requirements

| | Minimum | Notes |
| :--- | :--- | :--- |
| Python | 3.11 or 3.12 | Both are tested in CI (`.github/workflows/ci.yml`). The Docker image uses 3.11 |
| CPU / RAM | 4 cores, 8 GB RAM | Embedding and OCR run on CPU; no GPU is needed. The hosted container is capped at 6 GB |
| Disk | ~3 GB for the install, plus the download cache | The document cache grows with each economy crawled (`python tools/cache_gc.py` trims it) |
| Network | Outbound HTTPS | To the government portals, to Hugging Face (first run only, models) and to the LLM provider |
| API key | One OpenRouter key with credit | For real grading. Without one the pipeline runs on an offline lexical stand-in and says so |

Nothing else is required. Tesseract, PaddleOCR, Azure and the stealth browser are optional
extras, listed below where they matter.

---

## 2. Path A — Python virtual environment

The same steps as the README's Quick Start.

```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0

python -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt       # 5–15 minutes; pulls PyTorch (CPU) and sentence-transformers

cp .env.example .env                  # Windows: copy .env.example .env
#   set OPENROUTER_API_KEY=… and, for a demo without accounts, AUTH_ENABLED=false

streamlit run frontend/app.py         # http://localhost:8501
```

Optional extras:

| Extra | Command | Needed for |
| :--- | :--- | :--- |
| Stealth browser | `scrapling install` | Portals behind a JavaScript challenge — Indonesia (`peraturan.bpk.go.id`), and China's `search.cac.gov.cn` search lane |
| Playwright Chromium | `playwright install chromium` | The render-a-page fallback in `backend/pipeline/browser_fetch.py` |
| PaddleOCR | `pip install paddlepaddle paddleocr` | `OCR_PROVIDER=paddle` (Thai and Cyrillic recognisers) |
| Tesseract | system package + `TESSERACT_CMD` in `.env` | `OCR_PROVIDER=tesseract` (Lao offline) |

To serve other machines on the network:

```bash
streamlit run frontend/app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
```

Health check: `curl -fsS http://localhost:8501/_stcore/health` returns `ok`.

---

## 3. Path B — Docker

The [`Dockerfile`](../Dockerfile) builds a CPU-only image on `python:3.11-slim-bookworm`,
installs `torch==2.2.2` and `requirements.txt`, bakes the embedding model
(`paraphrase-multilingual-MiniLM-L12-v2`) and the English cross-encoder into the image, tries to
install PaddleOCR (non-fatal if the platform has no wheel), and starts Streamlit on port 8501.

```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0
cp .env.example .env                  # then set OPENROUTER_API_KEY

docker build -t veritrade .
docker run -d --name veritrade -p 8501:8501 \
  --env-file .env \
  -v "$PWD/outputs:/app/outputs" \
  -v "$PWD/data/cache:/app/data/cache" \
  veritrade
```

Open http://localhost:8501. The image has a `HEALTHCHECK` on `/_stcore/health`.

**Platforms.** The file's header comments describe a cross-build for an arm64 Jetson board, but
the base image is multi-architecture and the hosted instance is built from this same Dockerfile
with a plain `docker build` on an x86_64 host (`.github/workflows/deploy.yml` runs on a
self-hosted `Linux, X64` runner and calls [`deploy/redeploy.sh`](../deploy/redeploy.sh)).
The team has not timed a from-scratch build on a reviewer-class machine; on x86_64, PyPI's
`torch==2.2.2` wheel also pulls NVIDIA CUDA libraries, so expect a large image (several GB) and a
long first build.

**Not in the image.** `.env` is mounted at run time and never baked in. The stealth browser
(`scrapling install`) and Playwright's Chromium are not installed by the Dockerfile, so inside
the container a portal that refuses plain HTTP is logged as a fetch failure rather than retried
in a browser. This affects Indonesia most.

---

## 4. Configuration reference

Every setting has a default in [`backend/config.py`](../backend/config.py) and can be
overridden in `.env` (the file is read from the repository root, whatever the working
directory) or as an environment variable. [`.env.example`](../.env.example) lists them.

| Variable | Default | What it does |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `mock` in code, `openrouter` in `.env.example` | `openrouter` · `anthropic` · `openai` · `gemini` · `local` · `mock` |
| `OPENROUTER_API_KEY` | empty | Key for engine A, engine B and the helper models |
| `OPENROUTER_MODEL` | `deepseek/deepseek-v4-flash` | The grader (declared engine A). Engine B: `google/gemini-3.7-flash` |
| `OPENROUTER_REASONING` | `off` | Reasoning for hybrid models |
| `VERIFY_ENABLED` / `VERIFY_MODEL` | `true` / `deepseek/deepseek-v4-pro-0813` | Second-pass quote check on accepted rows |
| `LOCAL_LLM_BASE_URL` / `LOCAL_LLM_MODEL` | `http://localhost:11434/v1` / `llama3.1` | Any OpenAI-compatible server (Ollama, vLLM) for `LLM_PROVIDER=local` |
| `OCR_PROVIDER` | `rapidocr` | `rapidocr` · `paddle` · `tesseract` · `markitdown` · `vlm` · `azure` · `mock` |
| `AUTH_ENABLED` | `true` | `false` skips the sign-in screen |
| `DATABASE_URL` | empty (SQLite) | A Postgres URL moves accounts and run history off the local file — see [AUTH_AND_DATABASE.md](AUTH_AND_DATABASE.md) |
| `CACHE_DIR` | `data/cache` | Downloaded documents and caches |
| `FETCH_TTL_HOURS` | `24` | Reuse a downloaded body younger than this without a network request |
| `CRAWL_DELAY_SECONDS` | `2` | Gap between requests to one host |
| `CRAWL_RESPECT_ROBOTS` | `true` | robots.txt enforcement. Turning it off is logged on every request |
| `CONF_AUTO_ACCEPT` / `CONF_REVIEW_FLOOR` | `0.85` / `0.60` | Confidence routing thresholds |
| `TRANSLATION_ENABLED` | `true` | Two machine-translation columns for non-English sources |

---

## 5. What persists, and where

| Path | Contents | Safe to delete? |
| :--- | :--- | :--- |
| `data/cache/` | Downloaded document bodies (named by SHA-256) and `_index.json` | Yes — the next run downloads again. The live-test second pass needs the bodies of the first pass |
| `data/cache/_results/` | Stored full results (30-day TTL, invalidated by any code change) | Yes |
| `outputs/` | CSV / JSON exports, and `veritrade.db` (accounts, runs, review decisions) | Exports yes; deleting `veritrade.db` removes accounts and review history |
| `~/.cache/huggingface/` | Embedding and reranker models | Yes — downloaded again on the next run |

---

## 6. The hosted instance

https://veritrade.ftu.fyi is deployed on every push to `main` by
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml):

1. The CI suite runs first (`ci.yml`).
2. [`deploy/redeploy.sh`](../deploy/redeploy.sh) writes the API keys from the repository secrets
   into the host's env file, builds the image and restarts the container with the cache and
   outputs on host volumes.
3. The workflow makes one real grader call inside the running container, so a revoked key fails
   the deploy instead of producing a healthy-looking site.
4. The public URL is served through a Cloudflare tunnel (`deploy/setup_cf_tunnel.sh`).

Rotate a key without a full redeploy: `.github/workflows/rotate-key.yml`.

---

## 7. Troubleshooting

| Symptom | Cause and fix |
| :--- | :--- |
| First run stalls for minutes | Model download from Hugging Face (~0.5 GB). Once only |
| `[error] … fell back to the OFFLINE STAND-IN grader` | No usable key for the selected provider. Set it in `.env` or on the **Engines** screen |
| OpenRouter `402` / `403 Key limit exceeded` | No credit, or the key's daily cap is reached. `curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key` shows the cap |
| `[fetch] SKIPPED by robots.txt …` | The portal disallows that path. Expected; not a bug |
| `[fetch] SKIPPED, robots.txt UNREADABLE …` | The host did not answer. Usually the portal is down or unreachable from this network |
| A result appears instantly, marked as saved | **Search again** was unticked on the Run screen. Tick it to run live |
| `AttributeError` on a module after `git pull` | Restart Streamlit; it does not re-import changed modules |
| Windows: old code still served on port 8501 | `pkill` does not stop it. Use PowerShell `Stop-Process` on the process that owns port 8501 |
