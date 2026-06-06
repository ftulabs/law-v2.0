"""ZONE 2c (alt) — LightRAG-powered retrieval.

A drop-in alternative to retrieval.retrieve() backed by HKUDS LightRAG
(https://github.com/HKUDS/LightRAG): a graph-RAG that builds an entity/relation
knowledge graph over the corpus and does semantic (local/global/mix) retrieval. It
earns its keep at LIVE-CRAWL SCALE — when discovery returns dozens of laws and
hundreds of provisions, KG retrieval finds the right provision better than lexical
overlap. On the tiny offline sample the built-in hybrid retriever is enough, so the
orchestrator only switches to LightRAG above `settings.lightrag_min_provisions`.

CITATIONS ARE PRESERVED. We never let LightRAG synthesise an answer (that would break
the verbatim-citation requirement, 40% of the score). Each provision is inserted with
a `[PROV <id>]` marker; we query with `only_need_context=True`, then recover the exact
Provision (verbatim snippet, article, URL) from the markers in the retrieved context.
The LLM/grader stage downstream is unchanged — LightRAG only decides WHICH provisions
are seen.

Engines are plugged in WITHOUT vendor lock-in: the indexing LLM is the same provider
the pipeline already uses (OpenRouter/etc.), and embeddings are the local
sentence-transformers model — no OpenAI key required. Any failure (lib missing, KG
build error, rate-limit) returns None so the caller falls back to the hybrid retriever.
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from ..config import ROOT, settings
from ..schemas import Provision
from .retrieval import Retrieved

_PROV_RE = re.compile(r"\[PROV\s+(\S+?)\]")


def available() -> bool:
    import importlib.util
    return importlib.util.find_spec("lightrag") is not None


def _corpus_key(provisions: list[Provision]) -> str:
    h = hashlib.sha1()
    for p in provisions:
        h.update(p.provision_id.encode())
        h.update(p.verbatim_snippet[:200].encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


def _make_llm_func(llm):
    """Async LLM callable LightRAG uses for KG extraction, routed through OUR provider
    (OpenRouter/OpenAI/etc.) so there is no separate key and no vendor lock-in."""
    from openai import AsyncOpenAI

    base_url = getattr(llm, "base_url", None) or "https://openrouter.ai/api/v1"
    api_key = (settings.openrouter_api_key or settings.openai_api_key
               or settings.gemini_api_key or "sk-no-key")
    model = getattr(llm, "model_version", None) or settings.openrouter_model
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60.0, max_retries=1)

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for m in (history_messages or []):
            messages.append(m)
        messages.append({"role": "user", "content": prompt})
        resp = await client.chat.completions.create(model=model, messages=messages, temperature=0)
        return resp.choices[0].message.content or ""

    return llm_func


def _make_embedding_func():
    """Async embedding callable backed by the local sentence-transformers model — no API
    key, runs offline, multilingual (handles Malay/Thai for later economies)."""
    from lightrag.utils import EmbeddingFunc
    from .retrieval import _get_model

    model = _get_model()
    if model is None:
        return None
    dim = model.get_sentence_embedding_dimension()

    async def embed(texts: list[str]):
        import numpy as np
        vecs = await asyncio.to_thread(
            model.encode, texts, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype="float32")

    return EmbeddingFunc(embedding_dim=dim, max_token_size=8192, func=embed)


async def _run(indicators, provisions, top_k, llm, log):
    from lightrag import LightRAG, QueryParam
    from lightrag.kg.shared_storage import initialize_pipeline_status

    embedding_func = _make_embedding_func()
    if embedding_func is None:
        log("[lightrag] embedding model unavailable — falling back to hybrid")
        return None

    workdir = (ROOT / settings.lightrag_workdir / _corpus_key(provisions))
    workdir.mkdir(parents=True, exist_ok=True)
    by_id = {p.provision_id: p for p in provisions}

    rag = LightRAG(
        working_dir=str(workdir),
        llm_model_func=_make_llm_func(llm),
        embedding_func=embedding_func,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    # insert each provision as its own document, tagged so we can recover the citation
    docs = [f"[PROV {p.provision_id}] {p.law_name} — {p.article_section}\n{p.verbatim_snippet}"
            for p in provisions]
    await rag.ainsert(docs)
    log(f"[lightrag] indexed {len(docs)} provisions into KG ({workdir.name})")

    out: dict[str, list[Retrieved]] = {}
    for ind in indicators:
        query = f"{ind.title}. {ind.legal_test} {' '.join(ind.query_terms)}"
        try:
            ctx = await rag.aquery(
                query,
                param=QueryParam(mode="mix", only_need_context=True,
                                 top_k=max(top_k, 8), chunk_top_k=max(top_k, 8)),
            )
        except Exception as e:  # noqa: BLE001
            log(f"[lightrag] query failed for {ind.indicator_id} ({type(e).__name__}); skipping")
            out[ind.indicator_id] = []
            continue
        # recover provisions from the [PROV id] markers, in retrieved order, de-duped
        seen, ranked = set(), []
        for m in _PROV_RE.finditer(ctx or ""):
            pid = m.group(1)
            if pid in seen or pid not in by_id:
                continue
            seen.add(pid)
            p = by_id[pid]
            # rank score decays with retrieved order (LightRAG returns most-relevant first)
            score = round(max(0.15, 1.0 - 0.08 * len(ranked)), 3)
            ranked.append(Retrieved(provision=p, score=score, raw_context=p.verbatim_snippet,
                                    log=[f"lightrag mode=mix rank={len(ranked)} provision={pid}"]))
            if len(ranked) >= top_k:
                break
        out[ind.indicator_id] = ranked
    try:
        await rag.finalize_storages()
    except Exception:
        pass
    # If the KG produced nothing for ANY indicator the build was starved (commonly the
    # free LLM key's spend cap during entity extraction). Return None so the caller uses
    # the hybrid retriever rather than yielding zero candidates everywhere.
    if not any(out.values()):
        log("[lightrag] KG empty (indexing LLM unavailable / rate-limited) — "
            "falling back to hybrid. Use a funded or local LLM key for LightRAG mode.")
        return None
    return out


def retrieve_all(indicators, provisions: list[Provision], top_k: int = 5,
                 llm=None, log=lambda *_: None) -> dict[str, list[Retrieved]] | None:
    """Return {indicator_id: [Retrieved...]} via LightRAG, or None on any failure
    (caller falls back to the per-indicator hybrid retriever). Synchronous wrapper."""
    if not available() or not provisions:
        return None
    try:
        return asyncio.run(_run(indicators, provisions, top_k, llm, log))
    except (KeyboardInterrupt, SystemExit):
        raise
    except RuntimeError as e:
        # e.g. "asyncio.run() cannot be called from a running event loop" (Streamlit)
        if "running event loop" in str(e):
            try:
                import nest_asyncio  # LightRAG ships this; re-enter the loop safely
                nest_asyncio.apply()
                return asyncio.get_event_loop().run_until_complete(
                    _run(indicators, provisions, top_k, llm, log))
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e2:  # noqa: BLE001
                log(f"[lightrag] disabled ({type(e2).__name__}: {e2}); using hybrid retriever")
                return None
        log(f"[lightrag] disabled ({type(e).__name__}: {e}); using hybrid retriever")
        return None
    # BaseException (not just Exception): a free-model 429 storm during KG build surfaces as
    # asyncio.CancelledError / ExceptionGroup, which are NOT Exception subclasses — catching
    # only Exception let them crash the whole run. Fall back to the hybrid retriever instead.
    except BaseException as e:  # noqa: BLE001
        log(f"[lightrag] disabled ({type(e).__name__}: {e}); using hybrid retriever")
        return None
