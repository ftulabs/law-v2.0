# VeriTrade — self-host image for Jetson Nano (linux/arm64, CPU-only).
#
# The heavy LLM runs REMOTELY (OpenRouter), so the Nano needs no GPU/CUDA — only Python
# 3.11 + the app's CPU deps (torch CPU, sentence-transformers, LightRAG, OCR, crawler).
# JetPack 4.6 ships Python 3.6, too old for this codebase, so we ship our own runtime in
# the image instead of touching the host.
#
# Cross-build on an x86_64 host with buildx + QEMU binfmt (slow but no Nano RAM pressure):
#   docker buildx build --platform linux/arm64 -t veritrade:arm64 --load .
# Then ship to the Nano:  docker save veritrade:arm64 | gzip | ssh minh@jetson-nano \
#   'gunzip | docker load'  and run with the .env mounted (see deploy/run_on_jetson.sh).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MAX_JOBS=2 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    HF_HUB_DISABLE_TELEMETRY=1

# System libs needed by wheels at runtime: lxml (libxml2/xslt), Pillow (jpeg/zlib),
# onnxruntime/rapidocr & opencv (libgl, libglib, libgomp), plus git/curl.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
        libxml2-dev libxslt1-dev libjpeg62-turbo-dev zlib1g-dev \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first (own layer → rebuilds of app code don't reinstall torch). torch resolves to the
# PyPI linux_aarch64 CPU wheel; MAX_JOBS=2 caps any source build so the QEMU build stays
# within RAM. Everything else (pydantic-core, numpy, onnxruntime, lxml) has arm64 wheels.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
 && pip install -r requirements.txt

COPY . .

# .env (OPENROUTER_API_KEY, RETRIEVER=lightrag, …) is MOUNTED at runtime, never baked in.
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
