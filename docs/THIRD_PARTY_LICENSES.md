# Third-party licences

VeriTrade's own source code is released under the **Apache License 2.0** (`LICENSE` at the
repo root: the canonical Apache 2.0 text, with the appendix line filled in as
"Copyright 2026 VeriTrade (ftulabs)"). This page lists every third-party component the code
depends on or fetches at runtime, with its licence, so the licensing declaration for
Section 3 of the submission form can be checked.

**How it was produced (2026-09-29).** The Python inventory is the transitive closure of
`requirements.txt`, resolved against the installed environment (Python 3.12.10, Windows) and
passed to `pip-licenses --from=mixed`. Environment markers were evaluated for both Windows and
Linux, so Linux-only packages are included where they are declared. The raw output, with a
scope column and the packages that pull each one in, is
[`third_party_licenses.csv`](third_party_licenses.csv). Model licences were read from the
Hugging Face model API. Repository licences were read from the GitHub licence API.
Anything that could not be checked that way is marked **not verified**.

**Scope of the environment.** The machine used has `numpy 2.3.5`, `transformers 5.10.2` and
`torch 2.12.0`. The `requirements.txt` pins are `numpy<2` and `transformers<5`, and the
Dockerfile uses `torch==2.2.2`. These packages keep the same licence across those versions
(BSD / Apache-2.0 / BSD-3-Clause), so the version skew does not change any finding.

## Summary

| | Packages | Licence families |
|---|---|---|
| Required (from `requirements.txt`, with transitive dependencies) | 158 | MIT 62 · Apache-2.0 45 · BSD 43 · PSF 3 · ISC 1 · MPL-2.0 (with MIT/Apache) 3 · MPL/GPL/LGPL triple licence 1 |
| Optional only (PaddleOCR stack, `anthropic`) | 22 | MIT 8 · Apache-2.0 6 · BSD 5 · LGPL 2 · UNKNOWN 1 |
| **Total** | **180** | |

No required Python package is licensed under GPL, AGPL, SSPL or a non-commercial licence. The
items that need attention are listed under [Exceptions and notes](#exceptions-and-notes).

## Direct Python dependencies (`requirements.txt`)

| Package | Installed | Licence | Required / optional | Purpose in VeriTrade |
|---|---|---|---|---|
| fastapi | 0.136.1 | MIT | required | HTTP API |
| uvicorn[standard] | 0.46.0 | BSD-3-Clause | required | ASGI server for the API |
| pydantic | 2.13.4 | MIT | required | Data models and schemas |
| pydantic-settings | 2.14.1 | MIT | required | `.env`/config loading (`backend/config.py`) |
| typer | 0.25.1 | MIT | required | CLI (`main.py`) |
| rich | 15.0.0 | MIT | required | CLI output |
| pyyaml | 6.0.2 | MIT | required | `data/sources.yaml` and other config |
| python-dotenv | 1.2.2 | BSD-3-Clause | required | `.env` loading |
| httpx | 0.28.1 | BSD-3-Clause | required | HTTP client (fetch, LLM calls) |
| filelock | 3.29.1 | MIT | required | Cross-process lock on the fetch cache |
| streamlit | 1.58.0 | Apache-2.0 | required | Dashboard (`frontend/app.py`) |
| pandas | 2.3.3 | BSD-3-Clause | required | Tables and CSV export |
| openpyxl | 3.1.5 | MIT | required | Reads the ESCAP Database and template workbooks |
| SQLAlchemy | 2.0.49 | MIT | required | Audit and review database |
| bcrypt | 5.0.0 | Apache-2.0 | required | Password hashing (accounts) |
| markitdown[pdf] | 0.1.6 | MIT | required | Default text-layer PDF/HTML extraction |
| beautifulsoup4 | 4.14.3 | MIT | required | HTML parsing |
| lxml | 6.1.0 | BSD-3-Clause | required | HTML/XML parsing |
| pypdf | 6.11.0 | BSD-3-Clause | required | PDF reading |
| pdfplumber | 0.11.9 | MIT | required | Fallback text-layer extractor |
| rank-bm25 | 0.2.2 | Apache-2.0 | required | BM25 lexical retrieval |
| numpy | 2.3.5 (pin `<2`) | BSD-3-Clause | required | Numerics |
| sentence-transformers | 5.5.1 | Apache-2.0 | required (dense stage degrades to BM25 if absent) | Embeddings and cross-encoder |
| transformers | 5.10.2 (pin `<5`) | Apache-2.0 | required | Model runtime for sentence-transformers |
| torch (via sentence-transformers) | 2.12.0 (Docker 2.2.2) | BSD-3-Clause | required | Model runtime |
| lightrag-hku | 1.5.0 | MIT | required (falls back to hybrid retriever if absent) | Graph retrieval at crawl scale |
| nest_asyncio | 1.6.0 | BSD | required | Runs LightRAG's event loop inside Streamlit |
| scrapling[fetchers] | 0.4.8 | BSD-3-Clause | required | Default Zone-1 fetcher (TLS impersonation, stealth browser) |
| playwright | 1.59.0 | Apache-2.0 | required | Headless browser for JavaScript-gated portals |
| pypdfium2 | 5.9.0 | BSD-3-Clause / Apache-2.0 (bundles PDFium, BSD-3-Clause) | required | PDF page rendering for OCR and scan detection |
| rapidocr_onnxruntime | 1.4.4 | Apache-2.0 | required | Default OCR engine for scanned PDFs |
| Pillow | 12.2.0 | MIT-CMU (HPND) | required | Image handling |
| openai | 2.41.0 | Apache-2.0 | required | Client for OpenRouter (OpenAI-compatible) and OpenAI |
| pytest | 9.0.3 | MIT | required (test only) | Test suite |
| pdf-inspector | 1.14.2 | MIT | required (degrades to a density heuristic if absent) | Page-level scan/text triage |
| python-docx | 1.2.0 | MIT | **imported but not listed in `requirements.txt`** (`backend/pipeline/ocr.py`, `frontend/livetest.py`) | `.docx` extraction |
| *paddlepaddle* | 3.3.1 | Apache-2.0 | optional (commented out) | PaddleOCR runtime (`--ocr paddle`) |
| *paddleocr* | 3.6.0 | Apache-2.0 | optional (commented out) | PP-OCRv5 scanned-PDF OCR |
| *anthropic* | 0.105.2 | MIT | optional (commented out) | `LLM_PROVIDER=anthropic` |
| *pytesseract* | not installed | Apache-2.0 | optional (commented out) | Tesseract OCR wrapper |
| *pdf2image* | not installed | MIT | optional (commented out) | Rasterises PDFs through the Poppler binaries |
| *azure-ai-vision-imageanalysis* | not installed | MIT | optional (commented out) | Azure Document Intelligence OCR |
| *faiss-cpu* | not installed | MIT | optional (commented out, unused) | Alternative vector index |
| *scrapy* | not installed | BSD-3-Clause | optional (commented out, unused) | — |
| *psycopg[binary]* | not installed | LGPL-3.0 | optional (only for `DATABASE_URL=postgresql+psycopg://…`) | Postgres driver |

Licences for the packages that are not installed come from their PyPI metadata and are
**not verified** against an installed copy.

<details>
<summary><strong>Full Python inventory: 180 packages, direct and transitive</strong> (click to expand)</summary>

| Package | Version | Licence | Scope | Pulled in by |
|---|---|---|---|---|
| aiohappyeyeballs | 2.6.2 | Python Software Foundation License | transitive | aiohttp |
| aiohttp | 3.14.0 | Apache-2.0 AND MIT | transitive | lightrag-hku paddleocr |
| aiosignal | 1.4.0 | Apache Software License | transitive | aiohttp |
| aistudio-sdk | 0.3.8 | UNKNOWN | transitive, optional (Paddle only) | paddlex |
| altair | 6.1.0 | BSD License | transitive | streamlit |
| annotated-doc | 0.0.4 | MIT | transitive | fastapi typer |
| annotated-types | 0.7.0 | MIT License | transitive | pydantic |
| anthropic | 0.105.2 | MIT License | direct, optional | — |
| anyio | 4.13.0 | MIT | transitive | anthropic google-genai httpx openai scrapling starlette streamlit watchfiles |
| apify_fingerprint_datapoints | 0.13.0 | Apache Software License | transitive | browserforge scrapling |
| ascii_colors | 0.11.22 | Apache-2.0 | transitive | pipmaster |
| attrs | 26.1.0 | MIT | transitive | aiohttp jsonschema referencing |
| bce-python-sdk | 0.9.71 | Apache License 2.0 | transitive, optional (Paddle only) | aistudio-sdk |
| bcrypt | 5.0.0 | Apache Software License | direct | — |
| beautifulsoup4 | 4.14.3 | MIT License | direct | markdownify markitdown |
| blinker | 1.9.0 | MIT License | transitive | streamlit |
| browserforge | 1.2.4 | Apache Software License | transitive | scrapling |
| cachetools | 7.1.4 | MIT | transitive | streamlit |
| certifi | 2026.4.22 | Mozilla Public License 2.0 (MPL 2.0) | transitive | curl-cffi httpcore httpx requests |
| cffi | 2.0.0 | MIT | transitive | cryptography curl-cffi |
| chardet | 7.4.3 | 0BSD | transitive, optional (Paddle only) | paddlex |
| charset-normalizer | 3.4.7 | MIT | transitive | markitdown pdfminer-six requests |
| click | 8.4.1 | BSD-3-Clause | transitive | aistudio-sdk browserforge huggingface-hub magika scrapling streamlit typer uvicorn |
| colorama | 0.4.6 | BSD License | transitive | click colorlog pytest tqdm uvicorn |
| coloredlogs | 15.0.1 | MIT License | transitive | onnxruntime |
| colorlog | 6.10.1 | MIT License | transitive, optional (Paddle only) | paddlex |
| configparser | 7.2.0 | MIT License | transitive | lightrag-hku |
| crc32c | 2.8 | GNU Lesser General Public License v2 or later (LGPLv2+) | transitive, optional (Paddle only) | bce-python-sdk |
| cryptography | 48.0.0 | Apache-2.0 OR BSD-3-Clause | transitive | google-auth pdfminer-six |
| cssselect | 1.4.0 | BSD-3-Clause | transitive | scrapling |
| curl_cffi | 0.15.0 | MIT | transitive | scrapling |
| defusedxml | 0.7.1 | Python Software Foundation License | transitive | markitdown |
| distro | 1.9.0 | Apache Software License | transitive | anthropic google-genai openai |
| docstring_parser | 0.18.0 | MIT License | transitive, optional (Paddle only) | anthropic |
| et_xmlfile | 2.0.0 | MIT License | transitive | openpyxl |
| fastapi | 0.136.1 | MIT | direct | — |
| filelock | 3.29.1 | MIT | direct | huggingface-hub modelscope paddlex torch |
| flatbuffers | 25.12.19 | Apache Software License | transitive | onnxruntime |
| frozenlist | 1.8.0 | Apache-2.0 | transitive | aiohttp aiosignal |
| fsspec | 2026.4.0 | BSD-3-Clause | transitive | huggingface-hub torch |
| future | 1.0.0 | MIT License | transitive, optional (Paddle only) | bce-python-sdk |
| gitdb | 4.0.12 | BSD License | transitive | gitpython |
| GitPython | 3.1.50 | BSD-3-Clause | transitive | streamlit |
| google-api-core | 2.31.0 | Apache Software License | transitive | lightrag-hku |
| google-auth | 2.53.0 | Apache Software License | transitive | google-api-core google-genai |
| google-genai | 2.8.0 | Apache-2.0 | transitive | lightrag-hku |
| googleapis-common-protos | 1.75.0 | Apache Software License | transitive | google-api-core |
| greenlet | 3.5.0 | MIT AND PSF-2.0 | transitive | patchright playwright sqlalchemy |
| h11 | 0.16.0 | MIT License | transitive | httpcore uvicorn |
| hf-xet | 1.5.0 | Apache-2.0 | transitive | huggingface-hub |
| httpcore | 1.0.9 | BSD-3-Clause | transitive | httpx |
| httptools | 0.7.1 | MIT | transitive | streamlit uvicorn |
| httpx | 0.28.1 | BSD License | direct | anthropic google-genai huggingface-hub openai paddlepaddle |
| huggingface_hub | 1.17.0 | Apache Software License | transitive | paddlex sentence-transformers tokenizers transformers |
| humanfriendly | 10.0 | MIT License | transitive | coloredlogs |
| idna | 3.15 | BSD-3-Clause | transitive | anyio httpx requests yarl |
| imagesize | 2.0.0 | MIT License | transitive, optional (Paddle only) | paddlex |
| iniconfig | 2.3.0 | MIT | transitive | pytest |
| itsdangerous | 2.2.0 | BSD License | transitive | streamlit |
| Jinja2 | 3.1.6 | BSD License | transitive | altair pydeck torch |
| jiter | 0.15.0 | MIT | transitive | anthropic openai |
| joblib | 1.5.3 | BSD-3-Clause | transitive | scikit-learn |
| json_repair | 0.60.1 | MIT | transitive | lightrag-hku |
| jsonschema | 4.26.0 | MIT | transitive | altair |
| jsonschema-specifications | 2025.9.1 | MIT | transitive | jsonschema |
| lightrag-hku | 1.5.0 | MIT License | direct | — |
| lxml | 6.1.0 | BSD-3-Clause | direct | scrapling |
| magika | 0.6.3 | Apache Software License | transitive | markitdown |
| markdown-it-py | 4.2.0 | MIT License | transitive | rich |
| markdownify | 1.2.2 | MIT License | transitive | markitdown |
| markitdown | 0.1.6 | MIT | direct | — |
| MarkupSafe | 3.0.3 | BSD-3-Clause | transitive | jinja2 |
| mdurl | 0.1.2 | MIT License | transitive | markdown-it-py |
| modelscope | 1.37.1 | Apache-2.0 | transitive, optional (Paddle only) | paddlex |
| mpmath | 1.3.0 | BSD License | transitive | sympy |
| msgspec | 0.21.1 | BSD-3-Clause | transitive | scrapling |
| multidict | 6.7.1 | Apache License 2.0 | transitive | aiohttp yarl |
| nano-vectordb | 0.0.4.3 | MIT License | transitive | lightrag-hku |
| narwhals | 2.22.0 | MIT | transitive | altair scikit-learn |
| nest-asyncio | 1.6.0 | BSD License | direct | — |
| networkx | 3.6.1 | BSD-3-Clause | transitive | lightrag-hku paddlepaddle torch |
| numpy | 2.3.5 | BSD License | direct | lightrag-hku magika nano-vectordb onnxruntime opencv-contrib-python opencv-python opt-einsum paddlepaddle paddlex pandas pydeck rank-bm25 rapidocr-onnxruntime scikit-learn scipy sentence-transformers shapely streamlit transformers |
| onnxruntime | 1.20.1 | MIT License | transitive | magika rapidocr-onnxruntime |
| openai | 2.41.0 | Apache Software License | direct | — |
| opencv-contrib-python | 4.10.0.84 | Apache Software License | transitive, optional (Paddle only) | paddlex |
| opencv-python | 4.13.0.92 | Apache Software License | transitive | rapidocr-onnxruntime |
| openpyxl | 3.1.5 | MIT License | direct | — |
| opt-einsum | 3.3.0 | MIT | transitive, optional (Paddle only) | paddlepaddle |
| orjson | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) | transitive | scrapling |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | transitive | altair huggingface-hub lightrag-hku modelscope onnxruntime paddlex pipmaster pytest streamlit transformers |
| paddleocr | 3.6.0 | Apache License 2.0 | direct, optional | — |
| paddlepaddle | 3.3.1 | Apache Software License | direct, optional | — |
| paddlex | 3.6.1 | Apache-2.0 | transitive, optional (Paddle only) | paddleocr |
| pandas | 2.3.3 | BSD License | direct | lightrag-hku paddlex streamlit |
| patchright | 1.59.1 | Apache-2.0 | transitive | scrapling |
| pdf-inspector | 1.14.2 | MIT License | direct | — |
| pdfminer.six | 20251230 | MIT | transitive | markitdown pdfplumber |
| pdfplumber | 0.11.9 | MIT License | direct | markitdown |
| pillow | 12.2.0 | MIT-CMU | direct | paddlepaddle paddlex pdfplumber rapidocr-onnxruntime streamlit |
| pipmaster | 1.1.13 | Apache-2.0 | transitive | lightrag-hku |
| playwright | 1.59.0 | Apache-2.0 | direct | scrapling |
| pluggy | 1.6.0 | MIT License | transitive | pytest |
| prettytable | 3.17.0 | BSD-3-Clause | transitive, optional (Paddle only) | aistudio-sdk paddlex |
| propcache | 0.5.2 | Apache Software License | transitive | aiohttp yarl |
| Protego | 0.6.0 | BSD-3-Clause | transitive | scrapling |
| proto-plus | 1.28.0 | Apache Software License | transitive | google-api-core |
| protobuf | 7.34.1 | 3-Clause BSD License | transitive | google-api-core googleapis-common-protos onnxruntime paddlepaddle proto-plus streamlit |
| psutil | 7.2.2 | BSD-3-Clause | transitive, optional (Paddle only) | aistudio-sdk |
| py-cpuinfo | 9.0.0 | MIT License | transitive, optional (Paddle only) | paddlex |
| pyarrow | 24.0.0 | Apache-2.0 | transitive | streamlit |
| pyasn1 | 0.6.3 | BSD-2-Clause | transitive | pyasn1-modules |
| pyasn1_modules | 0.4.2 | BSD License | transitive | google-auth |
| pyclipper | 1.4.0 | MIT License | transitive | paddlex rapidocr-onnxruntime |
| pycparser | 3.0 | BSD-3-Clause | transitive | cffi |
| pycryptodome | 3.23.0 | BSD License; Public Domain | transitive, optional (Paddle only) | bce-python-sdk |
| pydantic | 2.13.4 | MIT | direct | anthropic fastapi google-genai lightrag-hku openai paddlex pydantic-settings |
| pydantic-settings | 2.14.1 | MIT | direct | — |
| pydantic_core | 2.46.4 | MIT | transitive | pydantic |
| pydeck | 0.9.2 | Apache License 2.0 | transitive | streamlit |
| pyee | 13.0.1 | MIT License | transitive | patchright playwright |
| Pygments | 2.20.0 | BSD-2-Clause | transitive | pytest rich |
| pypdf | 6.11.0 | BSD-3-Clause | direct | — |
| pypdfium2 | 5.9.0 | BSD-3-Clause, Apache-2.0, dependency licenses | direct | paddlex pdfplumber |
| pypinyin | 0.55.0 | MIT License | transitive | lightrag-hku |
| pyreadline3 | 3.5.6 | BSD License | transitive | humanfriendly |
| pytest | 9.0.3 | MIT | direct | — |
| python-bidi | 0.6.10 | GNU Library or Lesser General Public License (LGPL) | transitive, optional (Paddle only) | paddlex |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License | transitive | pandas |
| python-docx | 1.2.0 | MIT License | direct, undeclared | — |
| python-dotenv | 1.2.2 | BSD-3-Clause | direct | lightrag-hku magika pydantic-settings uvicorn |
| python-multipart | 0.0.28 | Apache-2.0 | transitive | streamlit |
| pytz | 2026.2 | MIT License | transitive | pandas |
| PyYAML | 6.0.2 | MIT License | direct | huggingface-hub lightrag-hku paddleocr paddlex rapidocr-onnxruntime transformers uvicorn |
| rank-bm25 | 0.2.2 | Apache2.0 | direct | — |
| rapidocr-onnxruntime | 1.4.4 | Apache-2.0 | direct | — |
| referencing | 0.37.0 | MIT | transitive | jsonschema jsonschema-specifications |
| regex | 2026.5.9 | Apache-2.0 AND CNRI-Python | transitive | tiktoken transformers |
| requests | 2.34.0 | Apache Software License | transitive | aistudio-sdk google-api-core google-auth google-genai markitdown modelscope paddleocr paddlex streamlit tiktoken |
| rich | 15.0.0 | MIT License | direct | curl-cffi typer |
| rpds-py | 0.30.0 | MIT | transitive | jsonschema referencing |
| ruamel.yaml | 0.19.1 | MIT License | transitive, optional (Paddle only) | paddlex |
| safetensors | 0.7.0 | Apache Software License | transitive | paddlepaddle transformers |
| scikit-learn | 1.9.0 | BSD-3-Clause | transitive | sentence-transformers |
| scipy | 1.17.1 | BSD License | transitive | scikit-learn sentence-transformers |
| scrapling | 0.4.8 | BSD License | direct | — |
| sentence-transformers | 5.5.1 | Apache Software License | direct | — |
| setuptools | 81.0.0 | MIT | transitive | lightrag-hku torch |
| shapely | 2.1.2 | BSD License | transitive | paddlex rapidocr-onnxruntime |
| shellingham | 1.5.4 | ISC License (ISCL) | transitive | typer |
| six | 1.17.0 | MIT License | transitive | bce-python-sdk markdownify python-dateutil rapidocr-onnxruntime |
| smmap | 5.0.3 | BSD License | transitive | gitdb |
| sniffio | 1.3.1 | Apache Software License; MIT License | transitive | anthropic google-genai openai |
| soupsieve | 2.8.4 | MIT | transitive | beautifulsoup4 |
| SQLAlchemy | 2.0.49 | MIT | direct | — |
| starlette | 1.0.0 | BSD-3-Clause | transitive | fastapi streamlit |
| streamlit | 1.58.0 | Apache-2.0 | direct | — |
| sympy | 1.14.0 | BSD License | transitive | onnxruntime torch |
| tenacity | 9.1.4 | Apache Software License | transitive | google-genai lightrag-hku streamlit |
| threadpoolctl | 3.6.0 | BSD License | transitive | scikit-learn |
| tiktoken | 0.13.0 | MIT License | transitive | lightrag-hku |
| tld | 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later | transitive | scrapling |
| tokenizers | 0.22.2 | Apache Software License | transitive | transformers |
| toml | 0.10.2 | MIT License | transitive | streamlit |
| torch | 2.12.0 | BSD-3-Clause | transitive | sentence-transformers |
| tqdm | 4.67.3 | MPL-2.0 AND MIT | transitive | aistudio-sdk huggingface-hub modelscope openai rapidocr-onnxruntime sentence-transformers transformers |
| transformers | 5.10.2 | Apache 2.0 License | direct | sentence-transformers |
| typer | 0.25.1 | MIT | direct | huggingface-hub transformers |
| typing-inspection | 0.4.2 | MIT | transitive | fastapi pydantic pydantic-settings |
| typing_extensions | 4.15.0 | PSF-2.0 | transitive | aiohttp aiosignal altair anthropic anyio beautifulsoup4 fastapi google-genai huggingface-hub openai paddleocr paddlepaddle paddlex pydantic pydantic-core pyee referencing scrapling sentence-transformers sqlalchemy starlette streamlit torch typing-inspection |
| tzdata | 2026.2 | Apache-2.0 | transitive | pandas |
| ujson | 5.12.1 | BSD-3-Clause AND TCL | transitive, optional (Paddle only) | paddlex |
| urllib3 | 2.7.0 | MIT | transitive | modelscope requests |
| uvicorn | 0.46.0 | BSD-3-Clause | direct | streamlit |
| w3lib | 2.4.1 | BSD-3-Clause | transitive | scrapling |
| watchdog | 6.0.0 | Apache Software License | transitive | streamlit |
| watchfiles | 1.1.1 | MIT License | transitive | uvicorn |
| wcwidth | 0.7.0 | MIT | transitive | ascii-colors |
| websockets | 16.0 | BSD-3-Clause | transitive | google-genai streamlit uvicorn |
| xlsxwriter | 3.2.9 | BSD License | transitive | lightrag-hku |
| yarl | 1.24.2 | Apache-2.0 | transitive | aiohttp |

The Windows-only packages `colorama` and `pyreadline3` (both BSD) are included above. The
Linux-only packages pulled in by the default PyPI `torch` wheel (`triton`: MIT;
`nvidia-*-cu12/13`, `cuda-toolkit`, `cuda-bindings`: NVIDIA proprietary licences) and
`uvloop` (MIT OR Apache-2.0, via `uvicorn[standard]`) were not installed on this machine,
so they are not in the CSV. See note N6.

</details>

## Components downloaded or used at runtime (not pip packages)

| Component | Exact id / version | Licence | How it is used | Required? |
|---|---|---|---|---|
| Embedding model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (`embed_model`) | Apache-2.0 (HF, verified) | Downloaded from Hugging Face on first use. Baked into the Docker image | required for the dense stage |
| Cross-encoder (Latin script) | `cross-encoder/ms-marco-MiniLM-L-6-v2` (`cross_encoder_model`; HF now redirects to `…-L6-v2`) | Apache-2.0 (HF, verified). Trained on MS MARCO, see N4 | Downloaded from HF. Baked into the Docker image | optional (`cross_encoder=auto`) |
| Cross-encoder (non-Latin) | `BAAI/bge-reranker-v2-m3` (`cross_encoder_model_multilingual`) | Apache-2.0 (HF, verified) | Downloaded from HF when enabled | optional (off by default) |
| RapidOCR models | `ch_PP-OCRv4_det_infer.onnx`, `ch_PP-OCRv4_rec_infer.onnx`, `ch_ppocr_mobile_v2.0_cls_infer.onnx` | Apache-2.0 (shipped inside the `rapidocr_onnxruntime` wheel) | Loaded by ONNX Runtime (MIT) | required (scanned PDFs) |
| PaddleOCR models | PP-OCRv5 det/rec (e.g. `PaddlePaddle/PP-OCRv5_server_det`, `…_rec`) | Apache-2.0 (HF, verified) | Downloaded by PaddleOCR on first use | optional (`--ocr paddle`) |
| Browser for Scrapling / Playwright | Playwright Chromium + chrome-headless-shell (build 1217), plus Playwright's FFmpeg build (1011) | Chromium: BSD-3-Clause plus bundled third-party licences. FFmpeg: LGPL-2.1-or-later build (**not verified**) | Separate binaries, installed by `scrapling install` (which runs `playwright install chromium`) or `python -m playwright install chromium`. Driven as a subprocess over CDP. Not in the repo or the Docker image | optional (`CRAWL_BROWSER=true`, JS-gated portals) |
| Camoufox | — | MPL-2.0 | **Not used by the installed Scrapling 0.4.8**, whose `install` command fetches Chromium only. Older Scrapling releases used Camoufox (a Firefox fork) for `StealthyFetcher` | not used |
| Public Suffix List | fetched by `tld` during `scrapling install` | MPL-2.0 | Data file fetched at install time | required (by Scrapling) |
| Tesseract OCR | system binary | Apache-2.0 | Subprocess via `pytesseract` | optional |
| Poppler (`pdftoppm`) | system binary | GPL-2.0 / GPL-3.0 | Subprocess via `pdf2image` (Tesseract and Azure paths only) | optional, see N3 |
| Fonts: Inter, IBM Plex Mono, Noto Sans | Google Fonts CSS URLs in `.streamlit/config.toml`, `frontend/theme.py`, `site/` | SIL OFL-1.1 (Inter and IBM Plex verified on GitHub; Noto Sans not verified) | Loaded by the viewer's browser from Google Fonts. **No font files are shipped in the repo** | UI only |
| three.js | `three@0.160.0` via esm.sh. Planet textures from `cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/` | MIT (GitHub, verified). The texture images' own provenance is **not verified** | Loaded by the viewer's browser in `frontend/components/geo/index.html`. The canvas fallback has no dependencies | UI only |
| World outline | `frontend/components/geo/world.json` (built from `world-atlas` 110m) | world-atlas: ISC (verified). Underlying Natural Earth data: public domain | Vendored data file | UI only |
| Bulma CSS | `site/theme/css/bulma.min.css`, `assets/nerfies/css/bulma.min.css` | MIT (verified) | Vendored in the project website | website only |
| bulma-carousel, bulma-slider | `*/js/bulma-*.min.js`, `*/css/bulma-*.min.css` | MIT (npm metadata, **not verified** from the vendored files) | Vendored in the project website | website only |
| Nerfies project-page template | `site/` layout and `assets/nerfies/css/index.css` | **CC BY-SA 4.0** (verified from the template's README) | Adapted for the project website. Attribution is already in the `site/index.html` footer | website only, see N2 |
| Web UI toolchain | `apps/web`: `typescript ^5.6` (Apache-2.0), `vite ^5.4` (MIT) | Permissive (lockfile: 55 MIT, 12 Apache-2.0 OR MIT, 1 each Apache-2.0 / BSD-3-Clause / ISC) | Build-time development dependencies | optional app shell |
| Desktop/mobile shell | `apps/shell`: Tauri 2 (`tauri`, `tauri-build`, `@tauri-apps/cli`: Apache-2.0 OR MIT). `Cargo.lock` resolves 429 crates | Mostly MIT/Apache. Includes MPL-2.0 crates `cssparser`, `cssparser-macros`, `selectors`, `dtoa-short`, `option-ext` | Statically linked into the Tauri binary if one is built | optional, see N5 |
| Declared LLM engine A | `deepseek/deepseek-v4-flash` (HF `deepseek-ai/DeepSeek-V4-Flash`) | MIT open weights (HF, verified) | Called over the OpenRouter HTTPS API. No weights are shipped | required for real grading (any provider will do) |
| Declared LLM engine B | `google/gemini-3.7-flash` | **Proprietary** (Google API terms) | Hosted API via OpenRouter. Nothing is shipped | optional alternative engine, see N7 |
| Second-pass verifier | `deepseek/deepseek-v4-pro-0813` (`verify_model`) | MIT open weights (HF, verified) | Hosted API via OpenRouter | optional (quote check) |
| Cross-check graders | `qwen/qwen3-30b-a3b-instruct-2507`, `openai/gpt-oss-120b` | Apache-2.0 (HF, verified) | Hosted API via OpenRouter | optional |
| Vision OCR fallback | `qwen/qwen3-vl-8b-instruct` (`vlm_ocr_model`) | Apache-2.0 (HF, verified) | Hosted API, or self-hosted through Ollama/vLLM | optional |
| Vision OCR, high accuracy | `google/gemini-3.1-pro-preview` (`vlm_ocr_model_high_accuracy`) | **Proprietary** | Hosted API, opt-in only | optional, see N7 |
| Other LLM providers | OpenRouter, OpenAI `gpt-4o`, Anthropic `claude-opus-4-8`, Gemini `gemini-2.0-flash`, Azure Document Intelligence | **Proprietary hosted services.** Their client SDKs are MIT/Apache | Called over HTTPS only when selected | optional |
| Local LLM default name | `llama3.1` (`local_llm_model`) via Ollama (MIT) | Llama 3.1 Community License (not an OSI licence) | Pulled by the user into their own Ollama. Nothing is shipped | optional, see N7 |
| Docker base image | `python:3.11-slim-bookworm` + apt `build-essential`, `git`, `libxml2`, `libgl1` … | Debian packages under their own licences (includes GPL tools) | Only relevant if the built image is distributed | deployment only, see N6 |

## Exceptions and notes

Each item is marked **compatible**, **needs review**, or **incompatible if distributed**. These
labels come from reading the licence terms. They are not legal advice.

**N1. Weak-copyleft Python packages on the required path. Compatible.**
- `certifi` (MPL-2.0: CA bundle, via httpx/requests/curl_cffi)
- `tqdm` (MPL-2.0 AND MIT)
- `orjson` (MPL-2.0 AND (Apache-2.0 OR MIT), via Scrapling)
- `tld` (MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later, via Scrapling; we rely on the MPL-1.1 or LGPL-2.1+ option)

All four are imported unmodified as separate packages and are not vendored into our source.
MPL's copyleft applies file by file and LGPL permits dynamic use, so our code can stay
Apache-2.0. Obligations arise only if we ship modified copies of their files.

**N2. Project website template (`site/`, `assets/nerfies/`): CC BY-SA 4.0. Needs review; declare as an exception.**
The Nerfies template is ShareAlike. The adapted website, meaning the HTML/CSS layout in `site/`
and `assets/nerfies/css/index.css`, must stay under CC BY-SA 4.0 and carry attribution. The
footer of `site/index.html` already does both. This does not affect the Python code. It does
mean that "the entire repository is Apache-2.0" is not literally true for those files.

**N3. GPL/LGPL components that are only optional. Compatible as used; incompatible only if bundled.**
- Poppler (GPL): a system binary that `pdf2image` calls as a subprocess, only on the
  Tesseract/Azure OCR paths. It is not installed by `requirements.txt` or the Dockerfile.
- `crc32c` (LGPLv2+), `python-bidi` (LGPL), `aistudio-sdk` (licence **UNKNOWN** in its
  metadata): these arrive only with the optional PaddleOCR stack
  (`paddlex` → `aistudio-sdk` → `bce-python-sdk`). The Dockerfile installs PaddleOCR on
  x86_64 as a non-fatal extra.
- `psycopg` (LGPL-3.0): only if Postgres is chosen.
- Playwright's FFmpeg build (LGPL, not verified): a downloaded binary, run as a separate process.

None of these is linked into our code. Recommendation: if a Docker image with PaddleOCR is
published, list these packages in the image's notices. Otherwise, no action.

**N4. `cross-encoder/ms-marco-MiniLM-L-6-v2`. Needs review for commercial use only.**
The model card is Apache-2.0. Its training data, MS MARCO, is distributed by Microsoft for
non-commercial research use. For a hackathon and research tool this is compatible.
A commercial deployment should review it or switch to the multilingual `bge-reranker-v2-m3`
(Apache-2.0).

**N5. Tauri shell (`apps/shell`). Needs review if a binary is distributed.**
The Rust dependency tree (429 crates) was not fully audited. It contains MPL-2.0 crates
(`cssparser`, `selectors`, `dtoa-short`, `option-ext`), which are compatible when used
unmodified. Run `cargo about` or `cargo deny check licenses` before releasing a built app.
The source code of the shell itself can stay Apache-2.0.

**N6. Docker image. Needs review if the image itself is distributed.**
On x86_64, `pip install torch==2.2.2` from PyPI pulls NVIDIA CUDA runtime wheels
(`nvidia-*-cu12`, NVIDIA proprietary licence) and `triton` (MIT). The image also bakes in the
two Apache-2.0 Hugging Face models and Debian GPL tools. This matters only if the image is
published. A source-code release is unaffected. Installing torch from
`https://download.pytorch.org/whl/cpu` would remove the NVIDIA libraries.

**N7. Proprietary hosted services. Compatible (no code or weights are distributed).**
Declared engine B `google/gemini-3.7-flash` and the opt-in `google/gemini-3.1-pro-preview` are
proprietary APIs, as are OpenRouter, OpenAI, Anthropic, Gemini and Azure Document Intelligence
when a user selects them. They are reached over HTTPS under the user's own API key and terms.
They are not part of the released code. Every function they serve can also be run on an
open-weight engine: engine A (DeepSeek V4 Flash, MIT) for grading and Qwen3-VL-8B
(Apache-2.0) for vision OCR. The `llama3.1` default for the local provider is under the Llama
Community License, which the user accepts when pulling it.

**N8. Housekeeping.**
- `python-docx` (MIT) is imported but missing from `requirements.txt`.
- `CLAUDE.md` still says `scrapling install` downloads Camoufox. With Scrapling 0.4.8 it
  downloads Chromium.
- The sample legislation under `data/samples/` and the ESCAP Database/template workbooks at
  the repo root are third-party documents under their publishers' terms, not Apache-2.0.

**NOTICE file.** There is none. Apache-2.0 §4(d) requires a NOTICE only when the redistributed
Work already includes one. We do not vendor any Apache-2.0 source that ships a NOTICE, and
Python dependencies are installed from PyPI rather than redistributed. So a NOTICE file is
optional for a source release. One would be useful if the Docker image or a Tauri binary is
distributed (N5, N6).
