# Deploying VeriTrade

How to bring VeriTrade up on a clean machine, either directly in a Python virtual environment or
as a Docker container, and how the hosted instance at https://veritrade.ftu.fyi is deployed.

For the desktop installers (macOS, Windows, Linux) see [INSTALL.md](../INSTALL.md). For the
system design see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Contents

1. [Requirements](#1-requirements)
2. [Path A — Docker (recommended)](#2-path-a--docker-recommended)
3. [Path B — Python virtual environment](#3-path-b--python-virtual-environment)
4. [Configuration reference](#4-configuration-reference)
5. [What persists, and where](#5-what-persists-and-where)
6. [The hosted instance](#6-the-hosted-instance)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Requirements

| | Docker path | Python path |
| :--- | :--- | :--- |
| Software | Docker Desktop (Windows, macOS) or Docker Engine + Compose v2 (Linux), and git | Python 3.11 or 3.12 (both tested in CI), and git |
| CPU / RAM | 4 cores, 8 GB RAM (no GPU) | same |
| Disk | ~8 GB for the image, plus the document cache | ~3 GB, plus the document cache |
| Network | Outbound HTTPS to the government portals, Hugging Face (models) and the LLM provider | same |
| API key | One OpenRouter key with credit, for real grading. Without one the tool runs on an offline stand-in grader and says so | same |

**Measured on 2026-09-29** (12-core laptop, 16 GB RAM, home broadband, no image cached): clone
+ `docker compose up -d --build` → **13 minutes** to a healthy app; the offline check in step 5
below → **1 minute**. A slower connection mostly lengthens the package download (~5 of the 13
minutes).

---

## 2. Path A — Docker (recommended)

Everything the tool needs is inside the image, including the headless Chromium that
Indonesia's legal database requires (it answers a plain HTTP client with a Cloudflare
JavaScript challenge) and the two small retrieval models. Nothing is installed on the host.

**Step 1 — Install Docker** (skip if `docker compose version` already prints a version).
Windows / macOS: install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
start it; wait until it says *Engine running*. Linux: install Docker Engine and the Compose
plugin from your distribution's instructions.

**Step 2 — Get the code**

```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0
```

**Step 3 — Configure**

```bash
cp .env.example .env              # Windows (cmd): copy .env.example .env
```

Open `.env` in any text editor and set your key:

```env
OPENROUTER_API_KEY=sk-or-...      # https://openrouter.ai/keys
AUTH_ENABLED=false                # optional: skip the sign-in screen
```

Everything else already has the declared defaults (engine A `deepseek/deepseek-v4-flash`, OCR
`rapidocr`). The key can also be pasted later on the **Engines** screen instead.

**Step 4 — Build and start**

```bash
docker compose up -d --build
```

The first time this downloads and builds for about 10–15 minutes; the terminal shows each
step. Later starts take seconds (`docker compose up -d`).

**Step 5 — Verify**

```bash
docker compose ps                 # STATUS shows "healthy" after ~10 s
docker compose exec veritrade python main.py --economy Singapore --pillar 6
```

Expected: `[done] 6 mappings in ~55s` and two files `outputs/SG_P6_<time>.csv` / `.json`
(offline sample corpus, no key needed). Then open **http://localhost:8501**: on the **Run**
screen pick Singapore, topic 6, *Live portals*, **Run analysis** — a live run takes 3–7 minutes
per pillar with a key set.

**Everyday commands**

| To | Run |
| :--- | :--- |
| Stop | `docker compose down` (data is kept) |
| Start again | `docker compose up -d` |
| See the logs | `docker compose logs -f veritrade` |
| Update after `git pull` | `docker compose up -d --build` |
| Change a setting | edit `.env`, then `docker compose up -d` |
| Delete everything, including data | `docker compose down -v` |

Results, downloaded laws, the accounts database and models are kept in Docker volumes
(`vt-outputs`, `vt-cache`, `vt-models`), so they survive restarts and rebuilds. To copy the
exports out: `docker compose cp veritrade:/app/outputs ./outputs`.

**Optional:** add PaddleOCR (~1 GB, a second OCR engine) with
`docker compose build --build-arg INSTALL_PADDLE=1 && docker compose up -d`.

---

## 3. Path B — Python virtual environment

```bash
git clone https://github.com/ftulabs/law-v2.0.git
cd law-v2.0

python -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt       # 5–15 minutes; pulls PyTorch and sentence-transformers
python -m playwright install chromium # the browser for JavaScript-challenge portals (Indonesia)
#   Linux only, once, with admin rights:  python -m playwright install-deps chromium

cp .env.example .env                  # Windows: copy .env.example .env
#   set OPENROUTER_API_KEY=… and, for a demo without accounts, AUTH_ENABLED=false

streamlit run frontend/app.py         # http://localhost:8501
python main.py --economy Singapore --pillar 6   # the same offline check as Path A step 5
```

Optional extras:

| Extra | Command | Needed for |
| :--- | :--- | :--- |
| PaddleOCR | `pip install paddlepaddle paddleocr` | `OCR_PROVIDER=paddle` (Thai and Cyrillic recognisers) |
| Tesseract | system package + `TESSERACT_CMD` in `.env` | `OCR_PROVIDER=tesseract` (Lao offline) |

To serve other machines on the network:

```bash
streamlit run frontend/app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
```

Health check: `curl -fsS http://localhost:8501/_stcore/health` returns `ok`.

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
| Docker volumes `vt-outputs`, `vt-cache`, `vt-models` | The same three, when run with `docker compose` | `docker compose down -v` removes them |

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
| First run stalls for minutes | Model download from Hugging Face. In Docker the two small models are in the image; the 2 GB multilingual reranker is fetched on the first non-Latin economy (China, Thailand, Russia…) and kept in `vt-models` |
| `docker compose` says `Cannot connect to the Docker daemon` | Docker Desktop is not running. Start it and wait for *Engine running* |
| Port 8501 already in use | Another app (or a local `streamlit run`) holds it. Stop it, or change the left side of `"8501:8501"` in `docker-compose.yml` to e.g. `"8502:8501"` and open that port |
| Indonesia finds nothing outside Docker | The browser is missing: `python -m playwright install chromium` (Linux: also `install-deps`) |
| `[error] … fell back to the OFFLINE STAND-IN grader` | No usable key for the selected provider. Set it in `.env` or on the **Engines** screen |
| OpenRouter `402` / `403 Key limit exceeded` | No credit, or the key's daily cap is reached. `curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key` shows the cap |
| `[fetch] SKIPPED by robots.txt …` | The portal disallows that path. Expected; not a bug |
| `[fetch] SKIPPED, robots.txt UNREADABLE …` | The host did not answer. Usually the portal is down or unreachable from this network |
| A result appears instantly, marked as saved | **Search again** was unticked on the Run screen. Tick it to run live |
| `AttributeError` on a module after `git pull` | Restart Streamlit; it does not re-import changed modules |
| Windows: old code still served on port 8501 | `pkill` does not stop it. Use PowerShell `Stop-Process` on the process that owns port 8501 |
