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
    # OpenRouter (paid models only). Key is read from env/.env/secrets — NEVER hardcode it
    # in committed code. Default is empty on purpose.
    openrouter_api_key: str = ""
    # Paid default; `:free` tier removed from failover (429s daily even on funded keys).
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    # Cap completion tokens. Two constraints pull in opposite directions:
    #   • a cap keeps OpenRouter's per-request credit pre-authorisation small — with NO cap,
    #     16-way concurrent calls can 402 (pre-auth exceeds balance) even on a funded key;
    #   • REASONING models (deepseek-v4-flash emits ~4-5K thinking tokens before the JSON)
    #     spend the SAME budget on thinking. At the old 1024 cap the thinking alone hit the
    #     limit (finish_reason=length) on most calls → empty/truncated JSON → the mapping was
    #     silently lost. Confirmed live: 49Q/P6-I2 vanished from runs at ~2/3 frequency.
    # 8192 fits observed thinking + answer with ~1.7x headroom while still bounding pre-auth
    # (16 × 8192 tokens ≈ $0.02 at deepseek-v4-flash prices). complete_json also retries once
    # with 4× the cap if a response still comes back truncated/unparseable.
    openrouter_max_tokens: int = 8192
    # Cross-model second opinion on borderline REJECTIONS. When the primary grader rejects a
    # provision while itself signalling legal closeness (it names a better_sibling, or scores
    # legal_match >= 0.3 despite rejecting), a DIFFERENT model re-grades the same prompt in a
    # fully independent call (no shared context — so no anchoring/bias, unlike re-asking the
    # same model). Disagreement goes to a third model; majority (2-1) decides. This targets the
    # measured run-to-run flip-flops (e.g. MHR s77/P6-I2 pre-fix: satisfied 1/3 attempts) at a
    # bounded extra cost instead of voting on every call. openrouter-only (needs a second model
    # behind one gateway); a failover that lands the "second" opinion on the primary model
    # voids that vote (independence guard).
    crosscheck_enabled: bool = True
    crosscheck_model: str = "google/gemini-2.5-flash"
    crosscheck_tiebreak_model: str = "openai/gpt-4o-mini"
    crosscheck_max_calls: int = 40           # per-run cap on extra opinion calls
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
    # Reuse a cached body younger than this without any network round-trip (0 = always
    # revalidate). Scrapling has no conditional GET, so without a TTL every run re-downloads
    # every PDF in full — ~10 min of fetch on the slow MY portal.
    fetch_ttl_hours: float = 24.0
    # Full-result cache: a repeat run with identical inputs returns the stored result instantly.
    # Kept until the cache is cleared (result_cache_ttl_hours=0) or past the TTL if set >0.
    result_cache_enabled: bool = True
    result_cache_ttl_hours: float = 0.0
    crawl_timeout_seconds: float = 30.0
    # Zone-1 fetch engine: scrapling (default) | httpx | auto.
    #   scrapling = Scrapling primary (real-browser TLS impersonation — the more reliable
    #               crawler against bot-protected portals), httpx fallback
    #   httpx     = httpx primary, Scrapling escalation only when httpx is blocked
    #   auto      = Scrapling if installed, else httpx
    crawl_fetcher: str = "scrapling"
    # crawl_browser=true also allows Scrapling's stealth (Camoufox) browser for JS-gated
    # portals — needs `scrapling install` to download the browser first.
    crawl_browser: bool = False
    cache_dir: str = "data/cache"              # downloaded law bodies live here (content-hashed)
    fetch_max_bytes: int = 60_000_000          # 60 MB hard cap per document
    # Extraction (OCR/PDF-to-text) is the single biggest per-run cost bucket (~44% of wall-clock,
    # ahead of embedding and LLM grading combined — profiled on a live AU crawl). The fetched BODY
    # is already content-addressed and cached; this caches the RESULT of running MarkItDown/OCR on
    # it too, keyed by (content hash, ocr provider), so re-processing an already-seen document
    # (same bytes, common across repeat/nearby-in-time live runs within fetch_ttl_hours) skips the
    # OCR/pdfplumber pass entirely instead of re-parsing every page from scratch.
    extraction_cache_enabled: bool = True
    # Documents are extracted independently of each other — run them concurrently (was strictly
    # sequential) so wall-clock scales with the SLOWEST single document, not the sum of all of
    # them. I/O-bound (pdfplumber/MarkItDown release the GIL during parsing), so a thread pool is
    # enough; no process-pool complexity needed.
    extraction_concurrency: int = 8
    discovery_max_docs: int = 18               # candidate cap per (economy, pillar). Tunable knob:
                                               # raising it fetches+OCRs more law types (e.g. Banking/
                                               # financial, ~rank 30) but the FIRST run is linearly slower
                                               # (sequential polite fetch + OCR); cached after. 18 covers
                                               # all SCORED SG P6/P7 answers.
    discovery_max_pages: int = 1               # search-result pages to walk per query
    # Web-search discovery breadth. Results are collected ROUND-ROBIN across queries — each
    # query's top hit before any query's 2nd — so a specific law-type query ("companies act")
    # is never crowded out by abundant data-protection results. per_query caps results pulled
    # from each query; max_queries caps how many of the (deduped) keyword queries we fire (one
    # search engine call each). Set to cover a full single-pillar keyword list (~90) so no
    # indicator's queries are structurally truncated — esp. P7-I5 government-access law types.
    # Safe on a rate-limited free engine: websearch's circuit breaker stops firing once the
    # engine blocks (so a high cap never hangs), and a Serper key fires them all reliably.
    discovery_per_query: int = 4
    discovery_max_queries: int = 90

    # retrieval (Zone 1 ranking)
    dense_retrieval: str = "auto"              # auto | on | off — 'auto' = dense if installed
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Persist provision embeddings to disk (text-hash + model key) — re-runs and the second
    # pillar skip re-encoding (~250s saved); vectors are byte-identical so rankings don't change.
    embed_cache_enabled: bool = True
    # Opt-in speed knob: skip embedding provisions with no concept vocab AND no BM25 signal.
    # ~75% embed saving, but full-pipeline A/B showed it changes a handful of final rows
    # (shortlist cut-line shifts) — default OFF; enable for fast non-submission runs only.
    dense_concept_gate: bool = False
    hybrid_alpha: float = 0.5                  # final = alpha*bm25 + (1-alpha)*dense
    cross_encoder: str = "auto"                # auto | on | off — cross-encoder rerank
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rrf_k: int = 60                            # Reciprocal-Rank-Fusion constant

    # Zone-2 coverage: when a run has <= grade_all_max_provisions provisions, EVERY provision
    # is graded against EVERY indicator (no top-k cap) so nothing relevant is missed — the
    # rubric rewards coverage. Above that (full Acts at live-crawl scale) we fall back to a
    # retrieval shortlist whose size scales with the corpus (retrieve_fraction of provisions,
    # at least retrieve_top_k). A provision may map to several indicators either way.
    grade_all_max_provisions: int = 80
    # Large-corpus shortlist: how many top-ranked provisions per indicator go to the LLM. The
    # hybrid retriever (BM25 + dense + cross-encoder rerank) puts the relevant provisions in
    # the top handful (verified: AU Privacy Act APP 8 ranks #1 for P6-I4 out of 700+), so a
    # small recall-safe shortlist captures them — grading 30% of 1200 provisions (the old
    # default) was ~1400 LLM calls for no recall gain. Shortlist = clamp(corpus*fraction,
    # retrieve_top_k floor, retrieve_max_top_k cap); the cap bounds latency + cost.
    retrieve_top_k: int = 20                    # floor — always grade at least this many/indicator
    retrieve_fraction: float = 0.05             # scale gently with corpus size
    retrieve_max_top_k: int = 40                # GLOBAL top-k/indicator (latency + cost ceiling)
    # Per-law guarantee: also include each discovered law's top-N provisions for the indicator,
    # so a short but on-point Act (e.g. My Health Records s77 "records outside Australia") is
    # graded even when a verbose Act (Privacy Act, 485 provisions) would otherwise crowd the
    # global top-k. Divide-by-law → retrieve each → merge. 0 disables (pure global top-k).
    retrieve_per_law_k: int = 3
    # Semantic-recall floor: also pull the strongest pure bi-encoder (dense) matches into the
    # shortlist even when the cross-encoder demoted them — guards concept matches phrased in
    # unexpected words. Dense scores are mapped to [0,1]; ~0.55 is "clearly on-topic".
    dense_recall_floor: float = 0.55
    # Concurrent LLM grading calls. deepseek throughput plateaus ~12; 16 = headroom without
    # the regression seen at 24+. Tune via MAPPING_CONCURRENCY.
    mapping_concurrency: int = 16

    # Zone-2 retriever: auto | hybrid | lightrag.
    #   hybrid   = built-in BM25+dense+cross-encoder (fast, always available, no LLM)
    #   lightrag = HKUDS LightRAG graph-RAG (semantic KG retrieval), citations preserved.
    #              Forces LightRAG on every run regardless of corpus size — best with a funded
    #              or local (Ollama/vLLM) LLM. Degrades to hybrid on any failure, never crashes.
    #   auto     = LightRAG when it's installed, a real LLM key is set, AND the corpus is large
    #              enough to benefit (>= lightrag_min_provisions, live-crawl scale); else hybrid.
    #              Tiny sample runs stay on hybrid (grade-all already covers them) so they don't
    #              pay the KG-build cost for no recall gain.
    # Default HYBRID: it needs no LLM and is fast + reliable. LightRAG's KG build calls the
    # indexing LLM once per provision, so on a free/rate-limited key it stalls then yields an
    # empty graph ("KG empty → falling back to hybrid") — wasting minutes before the real
    # grading even starts. Opt into 'lightrag'/'auto' only with a funded or local LLM.
    retriever: str = "hybrid"
    lightrag_min_provisions: int = 40          # auto-threshold: below this, auto uses hybrid
    lightrag_workdir: str = "data/cache/lightrag"

    # web-search discovery — keyless scraping rate-limits; a Serper key (serper.dev,
    # free tier) gives reliable Google deep-links. Falls back to DuckDuckGo/Mojeek.
    serper_api_key: str = ""

    # sample kit (RDTII Round-1 Database) for KNOWN/NEW tagging. Empty = auto-discover.
    sample_kit_path: str = ""

    # Zone 3 (optional, OPT-IN) — assign each mapped measure an RDTII Raw Score (0/0.5/1) +
    # Impact, and emit the supplementary Database-shaped scored CSV. Off by default so the
    # mandatory flow stays lean (one extra LLM call per mapping); enable per run via the
    # dashboard toggle, the CLI --score flag, or SCORING_ENABLED=true. The score is NEVER
    # written into the official 13-col submission CSV (see NOTES_FOR_JUDGES.md).
    scoring_enabled: bool = False

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
