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

    # crawl
    crawl_user_agent: str = "VeriTrade-Research/0.1 (+hackathon)"
    crawl_delay_seconds: float = 2.0
    crawl_timeout_seconds: float = 30.0

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


settings = Settings()
