"""Central configuration. All env-driven, all with safe defaults.

Nothing here hardcodes a provider — see `providers/` factories which read these
values. Importing this module never raises, so the app boots even with no `.env`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # providers
    ocr_provider: str = "markitdown"   # default doc-extraction engine (MS MarkItDown)
    llm_provider: str = "mock"

    # llm
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    # OpenRouter (free models). Key is read from env/.env/secrets — NEVER hardcode it
    # in committed code. Default is empty on purpose.
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    # Google Gemini (OpenAI-compatible endpoint). Key from env/.env/secrets — never commit.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    # Self-hosted / local LLM via any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio,
    # llama.cpp, LocalAI…). Point LOCAL_LLM_BASE_URL at the server's /v1. Ollama default
    # below; for a lab box set e.g. LOCAL_LLM_BASE_URL=http://gpu-lab:11434/v1 in .env.
    # Ollama ignores the key, so it stays empty.
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "llama3.1"
    local_llm_api_key: str = ""

    # azure ocr
    azure_vision_endpoint: str = ""
    azure_vision_key: str = ""

    # tesseract
    tesseract_cmd: str = ""
    poppler_path: str = ""

    # confidence routing
    conf_auto_accept: float = 0.85
    conf_review_floor: float = 0.60

    # storage / outputs
    veritrade_db: str = "outputs/veritrade.db"
    output_dir: str = "outputs"

    # crawl / fetch (Zone 1 live discovery)
    # A browser-like UA gets past the basic bot blocks some gov portals apply (SG SSO
    # returns 403 to unknown agents); override in .env to identify your crawler instead.
    crawl_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 VeriTrade-Research/0.2"
    )
    crawl_accept_language: str = "en,ms;q=0.8"
    crawl_delay_seconds: float = 2.0           # polite gap between requests to the SAME host
    crawl_timeout_seconds: float = 30.0
    cache_dir: str = "data/cache"              # downloaded law bodies live here (content-hashed)
    fetch_max_bytes: int = 60_000_000          # 60 MB hard cap per document
    discovery_max_docs: int = 12               # candidate cap per (economy, pillar)
    discovery_max_pages: int = 1               # search-result pages to walk per query

    # retrieval (Zone 1 ranking)
    dense_retrieval: str = "auto"              # auto | on | off — 'auto' = dense if installed
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    hybrid_alpha: float = 0.5                  # final = alpha*bm25 + (1-alpha)*dense
    cross_encoder: str = "auto"                # auto | on | off — cross-encoder rerank
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rrf_k: int = 60                            # Reciprocal-Rank-Fusion constant

    # Zone-2 retriever: auto | hybrid | lightrag.
    #   hybrid   = built-in BM25+dense+cross-encoder (fast, always available)
    #   lightrag = HKUDS LightRAG graph-RAG (semantic KG retrieval), citations preserved
    #   auto     = LightRAG when it's installed, an LLM key is set, AND the corpus is large
    #              enough to benefit (live-crawl scale); else hybrid. Tiny sample runs stay
    #              on hybrid so they don't pay the KG-build cost for no recall gain.
    retriever: str = "auto"
    lightrag_min_provisions: int = 40          # auto-threshold: below this, use hybrid
    lightrag_workdir: str = "data/cache/lightrag"

    # web-search discovery — keyless scraping rate-limits; a Serper key (serper.dev,
    # free tier) gives reliable Google deep-links. Falls back to DuckDuckGo/Mojeek.
    serper_api_key: str = ""

    # sample kit (RDTII Round-1 Database) for KNOWN/NEW tagging. Empty = auto-discover.
    sample_kit_path: str = ""

    @property
    def db_path(self) -> Path:
        p = (ROOT / self.veritrade_db) if not Path(self.veritrade_db).is_absolute() else Path(self.veritrade_db)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def output_path(self) -> Path:
        p = (ROOT / self.output_dir) if not Path(self.output_dir).is_absolute() else Path(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_path(self) -> Path:
        p = (ROOT / self.cache_dir) if not Path(self.cache_dir).is_absolute() else Path(self.cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
