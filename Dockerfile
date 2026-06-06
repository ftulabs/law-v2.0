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

# Deps first (own layer → rebuilds of app code don't reinstall torch).
# CPU-ONLY torch, pinned: torch 2.2.2's aarch64 wheel gates the nvidia-cu* CUDA deps to
# x86_64 only, so arm64 gets a clean ~80MB CPU install. (torch >=2.7 added arm64-CUDA wheels
# that drag in multi-GB nvidia-cudnn/cublas/nccl — useless on the Nano's JetPack-4.6 CUDA and
# far too big for its disk.) The Nano never runs the LLM locally (that's remote OpenRouter),
# so CPU torch for the embedding model is all it needs. MAX_JOBS=2 caps any source build.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
 && pip install torch==2.2.2 \
 && pip install -r requirements.txt

COPY . .

# ── Bake HuggingFace models into the image ──────────────────────────────────
# Pre-download the sentence-transformers embedding model and cross-encoder so that
# LightRAG and the dense retrieval stage work immediately on cold start without
# hitting the network.  Values must match backend/config.py defaults.
# PIP_NO_CACHE_DIR=1 is set globally, but HF uses its own cache dir (HF_HOME).
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); \
print('✓ Embedding + cross-encoder models baked into image')"

# ── PaddleOCR (optional) ─────────────────────────────────────────────────────
# PaddlePaddle does NOT publish Linux aarch64 wheels on PyPI, so this step is
# intentionally non-fatal: it succeeds on x86_64 CI runners and silently skips
# on the arm64 Jetson TX2 target.  rapidocr_onnxruntime (always installed above)
# is the active OCR engine when PaddleOCR is absent.
RUN pip install "paddlepaddle>=3.0" "paddleocr>=3.0" \
    && echo "✓ PaddleOCR installed" \
    || echo "⚠  PaddleOCR not available on this platform — rapidocr is active"

# .env (OPENROUTER_API_KEY, RETRIEVER=lightrag, …) is MOUNTED at runtime, never baked in.
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
