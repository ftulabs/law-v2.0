"""Central configuration. All env-driven, all with safe defaults.

Nothing here hardcodes a provider — see `providers/` factories which read these
values. Importing this module never raises, so the app boots even with no `.env`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # env_file is ABSOLUTE, not ".env". A relative path is resolved against the CURRENT
    # WORKING DIRECTORY, so the file was found only when the process happened to start in the
    # repo root. Launch from anywhere else — `cd frontend && streamlit run app.py`, a systemd
    # unit, a scheduler, an IDE run-config — and pydantic-settings silently found no file:
    # llm_provider fell back to its "mock" default and openrouter_api_key to "". The run then
    # completed, with a lexical mock grader, and the only symptom was mappings that looked
    # like a bad key. Nothing raised. ROOT is derived from __file__, so it is the same path
    # whatever the cwd.
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # providers
    # Default OCR engine, changed from "markitdown" (2026-08-14). MarkItDown does not do
    # raster OCR at all — it re-reads a text layer — so on a genuinely scanned page it
    # returned little or nothing, and what it did return was MARKDOWN fed into a splitter
    # that only understands plain text. It also placed last on the 200-document
    # opendataloader benchmark (0.589 overall, 0.000 on headings) against pdf-inspector's
    # 0.875. Text-layer PDFs never reached it anyway: the pipeline tries pdfplumber first.
    # RapidOCR is real raster OCR, pip-only (no system binaries), Apache-2.0 code, and the
    # engine the bundled CER=1.11% measurement was made with. Still swappable via OCR_PROVIDER.
    ocr_provider: str = "rapidocr"
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
    # Chosen by measurement, not reputation — tools/bakeoff.py over the verified benchmark in
    # data/benchmarks/grader_bakeoff.json (58 cases, 16 hand-read positives, the production
    # prompt). Two independent runs, identical result:
    #   mistral-small-3.2-24b  F1 0.903  prec 0.933  rec 0.875  $0.304/1k   2.8s   <- default
    #   gpt-4o-mini            F1 0.812  prec 0.812  rec 0.812  $0.591/1k   2.2s
    #   gpt-oss-120b           F1 0.800  prec 0.857  rec 0.750  $0.256/1k  20.0s
    #   deepseek-v4-flash      F1 0.786  prec 0.917  rec 0.688  $0.303/1k  11.5s   <- was default
    # The change that matters is RECALL: 0.688 -> 0.875 at the same price and four times
    # faster. A miss is a row absent from the submission, which is the expensive direction.
    # mistral and gpt-oss reproduced their scores exactly across both runs; the other two moved
    # by ~0.05, so the ranking gap between second and fourth is inside the noise and only the
    # first place is a firm result.
    openrouter_model: str = "mistralai/mistral-small-3.2-24b-instruct"

    # ── the two declared engines (C4b, re-tested live as C5b) ─────────────────────────
    # Declared in Section 5 of the 30 September submission and frozen from that moment. They
    # live here rather than only in the README so the live-test screen, the run record and the
    # documentation cannot disagree about what was declared — and so a reviewer can see the
    # declaration in the configuration the tool actually reads.
    # At least one must be OPEN WEIGHT; engine B is, and is self-hostable on a single GPU.
    declared_engine_a_provider: str = "openrouter"
    declared_engine_a_model: str = "openai/gpt-4o-mini"                 # commercial, hosted
    declared_engine_b_provider: str = "openrouter"
    declared_engine_b_model: str = "mistralai/mistral-small-3.2-24b-instruct"   # open weights
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
    # Retries against the SAME model when it returns 429, before considering another one.
    # Five with jittered exponential backoff covers a burst from sixteen concurrent workers.
    # See llm_openrouter._is_rate_limited for why a rate limit must not trigger model failover.
    openrouter_rate_limit_retries: int = 5
    # Upper bound (seconds) of one backoff step. The 8 s default was tuned for deepseek's
    # burst limits; a busy free/stealth model can stay 429 for minutes, so raise it (env
    # OPENROUTER_BACKOFF_CAP) rather than letting the call fall through to failover.
    openrouter_backoff_cap: int = 8
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

    # Vision-model OCR — the fallback for scripts no local recognition model covers
    # (Mongolian and Kazakh Cyrillic, Vietnamese tone marks, Lao). OpenAI chat-completions
    # shape, so the same code reaches a hosted router or a local open-weights server: point
    # vlm_ocr_base_url at http://localhost:11434/v1 with an Ollama-served Qwen2.5-VL and the
    # pipeline uses no proprietary API at all, which is what the Section 3 declaration claims.
    vlm_ocr_base_url: str = "https://openrouter.ai/api/v1"
    vlm_ocr_api_key: str = ""
    # Chosen on MDPBench (3,400 real documents, 17 languages, digital and photographed), which
    # is the only public benchmark covering the scripts we actually need. Scores for this exact
    # model: 68.3 overall - Vietnamese 79.1, Indonesian 68.5, Thai 61.9, Russian 58.4,
    # Chinese 57.9.
    #
    # It replaces qwen/qwen2.5-vl-72b-instruct, which was picked on reputation: no benchmark
    # covers it, and it costs about four times as much per page ($2.50 against $0.64 per 1k).
    # Two things beyond the score decided it. The weights are Apache-2.0, so the same engine can
    # be self-hosted and the Section 3 "no proprietary API" declaration still holds. And 8B is
    # small enough that self-hosting is a real option rather than a formality.
    vlm_ocr_model: str = "qwen/qwen3-vl-8b-instruct"
    # Opt-in escalation for pages nothing else can read at all. The Gemini 3 Pro family tops
    # MDPBench at 86.4 overall (Russian 90.4, Vietnamese 91.6, Thai 85.5) - about 18 points
    # above the default, at roughly 23x the price, and proprietary. Worth it only where the
    # alternative is no text; never a default, and never on the core path.
    vlm_ocr_model_high_accuracy: str = "google/gemini-3.1-pro-preview"
    # Off by default: it bills per page and returns no confidence to grade, so it must be an
    # explicit choice. `vlm_ocr_auto_fallback` lets it rescue ONLY the case where the
    # alternative is a hard failure — no installed engine has a model for the script.
    vlm_ocr_auto_fallback: bool = True

    # confidence routing
    conf_auto_accept: float = 0.85
    conf_review_floor: float = 0.60

    # storage / outputs
    veritrade_db: str = "outputs/veritrade.db"
    output_dir: str = "outputs"
    # Cloud-ready storage: everything goes through SQLAlchemy, so moving to a hosted
    # Postgres is a one-line change — set DATABASE_URL=postgresql+psycopg://user:pw@host/db
    # (and pip install psycopg[binary]). Empty → the local SQLite file above.
    database_url: str = ""

    # auth / sessions
    auth_enabled: bool = True
    # Days a "stay signed in" session cookie stays valid before re-login is required.
    session_days: int = 14
    # Google sign-in is optional: it only appears when Streamlit's OIDC block is
    # configured in .streamlit/secrets.toml (see docs/AUTH.md). Email+password always works.
    google_auth_enabled: bool = True

    # crawl / fetch (Zone 1 live discovery)
    # A browser-like UA gets past the basic bot blocks some gov portals apply (SG SSO
    # returns 403 to unknown agents); override in .env to identify your crawler instead.
    crawl_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 VeriTrade-Research/0.2"
    )
    crawl_accept_language: str = "en,ms;q=0.8"
    crawl_delay_seconds: float = 2.0           # polite gap between requests to the SAME host
    # robots.txt is enforced, not merely read for its Sitemap line (pipeline/robots.py). ON by
    # default because a ministry running this tool should not have to configure politeness, and
    # because five tools read the same portals within the same hour on 15 October. Turning it
    # off is a deliberate act that names itself in the run log.
    crawl_respect_robots: bool = True
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
    # Candidate cap per (economy, pillar). MEASURED against the panel's own SG pillar-7 rows,
    # counting how many of the twelve laws they cite reach the shortlist:
    #
    #     cap 18 -> 6/12   (no Employment Act 1968, no Telecommunications Act 1999)
    #     cap 22 -> 8/12
    #     cap 26 -> 8/12
    #     cap 30 -> 8/12
    #
    # 22 is where the curve flattens, and it flattens because the four still missing are PDPC
    # guidance notes and an IMDA licence condition that are not published on sso.agc.gov.sg at
    # all — a catalogue gap, not a ranking one, and no cap reaches them.
    #
    # The old note said "18 covers all SCORED SG P6/P7 answers". That was true of a P6+P7 run,
    # where discovery runs ONCE PER PILLAR and the pillar-6 lane happened to carry the Companies
    # Act in on its own budget. A pillar-7-only run — which is what the judges may ask for — got
    # 18 documents total and left it out.
    #
    # Cost of the change is fetch and extraction, not grading: mapping is bounded by the
    # retrieval shortlist (`retrieve_max_top_k`) per indicator, not by corpus size.
    discovery_max_docs: int = 22

    # ── working translation of the evidence (backend/pipeline/translate.py) ──
    # On by default because the run it exists for — a non-English economy — is otherwise
    # unverifiable by the people producing it, and because it costs NOTHING on an economy
    # already in the target language: those are skipped without a call. Distinct law names are
    # translated once each and every result is disk-cached by source text, so a re-run of the
    # same economy spends nothing either.
    translation_enabled: bool = True
    #: The language the reviewer reads. English by default — it is what the panel reads and
    #: what the mapping rationale is already written in — but set TRANSLATION_TARGET_LANG to
    #: any language for an internal review pass.
    translation_target_lang: str = "English"
    #: Input cap per call. A snippet longer than this is a whole article the reviewer will
    #: open the source URL for; the cell is marked truncated rather than silently cut.
    translation_max_chars: int = 6000
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
    # final = alpha*bm25 + (1-alpha)*dense. 0.65 was MEASURED, not guessed: on the 382-law
    # evaluation corpus scored against the RDTII Round-1 Database, alpha 0.65 retrieves every
    # provision the panel cited (18/18) where 0.50 gets 17/18, and both ends of the range are
    # clearly worse (pure dense 16/18, pure BM25 16/18). See tools/sweep_retrieval.py.
    hybrid_alpha: float = 0.65
    cross_encoder: str = "auto"                # auto | on | off — cross-encoder rerank
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # ms-marco is English-ONLY. Scoring a Chinese or Mongolian provision with it does not
    # return a weak signal, it returns noise — and that noise is fused into the final ranking
    # with the same weight as BM25 and the embeddings. For a non-Latin economy we load this
    # multilingual reranker instead, and if it is unavailable we run with NO cross-encoder:
    # two good signals beat three when the third is arbitrary.
    cross_encoder_model_multilingual: str = "BAAI/bge-reranker-v2-m3"
    # …and it is OFF by default, because it is 25x slower and that is not a trade, it is a wall.
    # Measured on this machine: ms-marco-MiniLM-L-6-v2 scores 245 pairs/s, bge-reranker-v2-m3
    # scores 9.9 (568M parameters against 22M). The first full China run spent 40,462 seconds —
    # eleven hours — inside retrieval for 268 provisions, where Singapore spent 100 seconds for
    # 3,218. The live test allows sixty minutes total. So a non-Latin economy runs on BM25 +
    # dense embeddings unless someone turns this on deliberately, with a GPU or time to spare.
    cross_encoder_multilingual_enabled: bool = False
    rrf_k: int = 60                            # Reciprocal-Rank-Fusion constant
    # Cross-encoder cost controls. It is the slowest stage by an order of magnitude — 21
    # pairs/s on this CPU against ~45 embeddings/s — so these decide whether a precompute pass
    # takes an afternoon or a week.
    #   pool_mult  how many candidates get cross-encoded, as a multiple of the shortlist size.
    #              MEASURED both ways, and left at 3:
    #                • WIDENING is actively harmful. Scoring 400 / 1,350 / 4,000 / 12,000 / ALL
    #                  provisions changed statute recall by NOTHING (33/47 at every size) while
    #                  the median rank of a correct target fell from 241 to 477 — a bigger pool
    #                  mostly lifts noise above the answer. Cross-encoding the whole corpus
    #                  would have cost ~33 h to rank WORSE.
    #                • NARROWING to 1 scored identically end-to-end (law 23/23, provision
    #                  18/19) for a third of the work — but in the shipped configuration the
    #                  whole cross-encoder stage is only ~29 min for all three economies, so
    #                  that saves ~20 min of an ~8 h precompute. Not worth giving up the
    #                  headroom to promote a candidate from outside the top-K on economies we
    #                  have not measured. Revisit if a Finals corpus makes the stage expensive.
    #   batch_size 64 measured 1.22x faster than the library default of 32 on real provisions
    #              (pairs are ~300 tokens, so the default leaves the CPU underfed).
    #   cache      scores are deterministic in (model, query, provision text), and this was the
    #              only layer without a cache, so every experiment re-scored unchanged pairs.
    cross_encoder_pool_mult: int = 3
    cross_encoder_batch_size: int = 64
    cross_encoder_cache_enabled: bool = True

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
    # Shortlist size per indicator. RE-DERIVED FROM MEASUREMENT (see docs/retrieval-redesign.md):
    # on a 382-law corpus (36k provisions) scored against the judges' own Database, provision
    # recall is 0.833 at the old cap of 40, 0.944 at 150 and 1.000 at 300 — and FLAT from 300
    # to 1200, so 300 is the knee, not an arbitrary ceiling. Cost does not grow with the corpus:
    # the cap binds, so a 500k-provision national corpus still grades 300/indicator.
    retrieve_top_k: int = 40                    # floor — always grade at least this many/indicator
    retrieve_fraction: float = 0.05             # scale gently with corpus size
    # 450 (was 300) — RE-MEASURED 2026-08-19 against the panel's own evidence, per piece of
    # evidence rather than per indicator. The knee is sharp and sits exactly here: K=330/360/
    # 400/425 recover nothing over 300, K=450 recovers two more cited provisions, and 475/500
    # add nothing further. Indicator-level recall improves with it (law 22/23 -> 23/23,
    # provision 17/19 -> 18/19), and grading a 300-candidate sample of everything K=450 ADDS
    # over K=300 produced ZERO accepted mappings, so the extra budget costs money and not
    # precision. Every cleverer mechanism tried was dominated — see docs/retrieval-depth-proposal.md.
    retrieve_max_top_k: int = 450               # GLOBAL top-k/indicator (latency + cost ceiling)
    # Per-law reservation: give each law its own top-N slots before the global budget is spent.
    # MEASURED OFF (see docs/retrieval-redesign.md). Two independent problems:
    #   • at k=3 the reservation pass alone wants one slot per law, which on a multi-hundred-law
    #     corpus exceeds the whole budget — the shortlist degenerates into "one provision from
    #     each of the top-k laws", maximum breadth and zero depth, and provision recall falls;
    #   • the reservation ranks provisions WITHIN each law (BM25 is renormalised per law), so a
    #     mediocre provision from an off-topic Act outranks a strong one from the right Act.
    # End-to-end on the shipped code: per_law_k=0 -> 17/18 cited provisions retrieved, per_law_k=1
    # -> 16/18, with worse shortlist purity at 1 (density 0.133 vs 0.191 on AU). The guarantee
    # only pays if it is re-implemented against GLOBAL scores; until then, off.
    retrieve_per_law_k: int = 0
    # Semantic-recall floor: also pull the strongest pure bi-encoder (dense) matches into the
    # shortlist even when the cross-encoder demoted them — guards concept matches phrased in
    # unexpected words. Dense scores are mapped to [0,1]; ~0.55 is "clearly on-topic".
    dense_recall_floor: float = 0.55
    # How many such extra matches to admit. Was hardcoded to max(2, k//3). MEASURED INERT at
    # the current shortlist size: at k>=150 it changed provision recall by 0.000 while adding
    # ~10% more LLM calls — the budget already reaches deeper than the guarantee does. Default
    # 0; raise it if retrieve_max_top_k is ever lowered, where the guarantee earns its cost.
    dense_recall_extra: int = 0
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
    # written into the official 14-col submission CSV (see NOTES_FOR_JUDGES.md).
    scoring_enabled: bool = False

    @property
    def db_path(self) -> Path:
        p = (ROOT / self.veritrade_db) if not Path(self.veritrade_db).is_absolute() else Path(self.veritrade_db)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL when set (cloud Postgres), else the local SQLite file."""
        if self.database_url.strip():
            return self.database_url.strip()
        return f"sqlite:///{self.db_path.as_posix()}"

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
