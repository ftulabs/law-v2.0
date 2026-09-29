# VeriTrade — one image for a laptop, a server (x86_64) or a Jetson (arm64). CPU only.
#
#   docker compose up -d --build        → http://localhost:8501   (see docs/DEPLOYMENT.md)
#
# The language model runs REMOTELY (OpenRouter by default), so the image needs no GPU — only
# Python 3.11 and the CPU dependencies: torch for the embedding model, OCR, the crawler and a
# headless Chromium for the portals that answer a plain HTTP client with a JavaScript challenge.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MAX_JOBS=2 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/root/.cache/huggingface \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# System libs needed by wheels at runtime: lxml (libxml2/xslt), Pillow (jpeg/zlib),
# onnxruntime/rapidocr & opencv (libgl, libglib, libgomp), plus git/curl.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
        libxml2-dev libxslt1-dev libjpeg62-turbo-dev zlib1g-dev \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first (own layer → rebuilds of app code don't reinstall torch).
# torch comes from PyTorch's CPU-only index. From PyPI, the x86_64 wheel pulls several GB of
# NVIDIA CUDA libraries this image never uses — the slowest part of a first build, and a
# licence question for anyone who republishes the image. 2.2.2 is kept because
# requirements.txt pins numpy<2 and transformers<5 to match it (arm64 deploy target).
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
 && pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# Headless Chromium, with the system libraries it needs. Indonesia's legal database answers
# a plain HTTP client with HTTP 403 and a Cloudflare JavaScript challenge; the crawler's
# browser lane (Scrapling → Playwright) runs that challenge the way a visitor's browser does.
# Without this step the lane fails inside the container and Indonesia finds nothing.
RUN python -m playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# Bake the two small retrieval models so the first run needs no model download.
# (The 2 GB multilingual reranker for non-Latin economies is fetched on first use and kept
# in the hf-cache volume — see docker-compose.yml.)  Values must match backend/config.py.
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); \
print('embedding + cross-encoder models baked into image')"

# PaddleOCR is an OPTIONAL second OCR engine (~1 GB). RapidOCR, installed above, is the
# default and covers scanned PDFs. Off by default so a first build stays well inside the
# 30-minute deployment benchmark; `docker compose build --build-arg INSTALL_PADDLE=1` adds it.
ARG INSTALL_PADDLE=0
RUN if [ "$INSTALL_PADDLE" = "1" ]; then \
      pip install "paddlepaddle>=3.0" "paddleocr>=3.0" \
      && echo "PaddleOCR installed" \
      || echo "PaddleOCR not available on this platform — RapidOCR is active"; \
    fi

COPY . .

# .env (API keys, …) is supplied at runtime, never baked in.
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
