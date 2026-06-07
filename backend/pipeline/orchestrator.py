"""End-to-end pipeline orchestration (Zone 1 → Zone 2 → outputs).

Ties the stages together, persists everything to the audit store, and returns a
RunResult. Designed to be called from the CLI, the FastAPI route, or the Streamlit
app. Pure function of its inputs + provider config — reproducible in mock mode.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from ..config import settings
from ..providers import get_llm_provider, get_ocr_provider
from ..rdtii import get_indicators
from ..schemas import Economy, OCRReport, RunMeta, RunResult
from ..storage import db
from . import discovery, extraction, mapping
from .ocr import get_document_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_ocr(name, log):
    """Resolve the requested OCR provider, falling back to mock (with a clear log)
    if the library/keys are missing — a judge experimenting must never crash a run."""
    try:
        return get_ocr_provider(name) if name else get_ocr_provider()
    except Exception as e:  # noqa: BLE001
        log(f"[warn] OCR provider '{name}' unavailable ({e}); falling back to mock")
        return get_ocr_provider("mock")


def _resolve_llm(name, model, api_key, log):
    try:
        return get_llm_provider(name, model=model, api_key=api_key) if name else get_llm_provider()
    except Exception as e:  # noqa: BLE001
        log(f"[warn] LLM provider '{name}' unavailable ({e}); falling back to mock")
        return get_llm_provider("mock")


def run_pipeline(
    economy: Economy,
    pillars: list[int],
    use_samples: bool = True,
    top_k: int = 5,
    log=print,
    ocr_provider: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    pdf_path: str | None = None,
) -> RunResult:
    run_id = "run-" + uuid.uuid4().hex[:8]
    t0 = time.perf_counter()
    started = _now()

    # runtime-selected providers (dashboard) with safe fallback to mock
    ocr = _resolve_ocr(ocr_provider, log)
    llm = _resolve_llm(llm_provider, llm_model, llm_api_key, log)
    log(f"[providers] OCR={ocr.name} LLM={llm.name} ({llm.model_version})")

    db.init_db()
    db.start_run(run_id, economy.value, pillars, started, ocr.name, llm.name, llm.model_version)

    # discover across all requested pillars (union) — or use a single provided file
    seen, docs = set(), []
    if pdf_path:
        log(f"[discovery] single file (crawler bypassed): {pdf_path}")
        docs = [discovery.doc_from_file(economy, pdf_path)]
    else:
        log(f"[discovery] economy={economy.value} pillars={pillars} samples={use_samples}")
        for pillar in pillars:
            for d in discovery.discover(economy, pillar, use_samples=use_samples):
                if d.doc_id not in seen:
                    seen.add(d.doc_id)
                    docs.append(d)
    log(f"[discovery] {len(docs)} documents (NEW={sum(d.discovery_tag=='NEW' for d in docs)})")

    # Zone 1b — fetch bodies for live-discovered docs (sample/file docs already have a path)
    if not use_samples and not pdf_path:
        from .fetch import fetch_to_cache
        from .discovery import _resolve_pdf_url
        fetched = 0
        kept, by_content = [], {}   # sha256 -> doc already kept
        for d in docs:
            if d.local_path:
                kept.append(d)
                continue
            fetch_url, _ = _resolve_pdf_url(d.economy, d.source_url)   # landing -> PDF body
            fr = fetch_to_cache(fetch_url, log=log)
            if not fr:
                continue
            # Content-level dedup: title normalisation can miss a law surfaced under two
            # very different search titles; here the fetched bytes are identical, so the
            # SHA-256 is the ground truth. Drop the duplicate so the same Act isn't
            # extracted and graded N times (the cause of the 1000+ provision blow-ups).
            prior = by_content.get(fr.sha256)
            if prior is not None:
                log(f"[fetch] skip duplicate body (same SHA as '{prior.title[:48]}'): {d.title[:48]}")
                continue
            by_content[fr.sha256] = d
            d.local_path, d.fmt = fr.local_path, fr.fmt
            fetched += 1
            kept.append(d)
        dropped = len(docs) - len(kept)
        docs = kept
        log(f"[fetch] retrieved {fetched} bodies into cache"
            + (f" ({dropped} duplicate/failed dropped)" if dropped else ""))

    for d in docs:
        db.save_doc(run_id, d)

    # extraction (+OCR) → provisions
    provisions, source_texts, doc_tags, ocr_reports = [], {}, {}, []
    for d in docs:
        raw, ocr_metrics = get_document_text(d, ocr_provider=ocr)
        source_texts[d.doc_id] = raw
        doc_tags[d.doc_id] = d.discovery_tag
        provs = extraction.extract_provisions(d, raw, ocr_metrics)
        provisions.extend(provs)
        if ocr_metrics.notes == "js_app_shell":
            log(f"[extract] {d.title[:48]} -> JS-rendered page, no static law text "
                f"(set CRAWL_BROWSER=true + run `scrapling install` to render it)")
            continue
        if ocr_metrics.used:
            cer_str = (f" CER={ocr_metrics.cer*100:.2f}% {'PASS<5%' if ocr_metrics.cer < 0.05 else 'OVER-5%'}"
                       if ocr_metrics.cer is not None else "")
            log(f"[ocr] {d.title[:48]} via {ocr_metrics.provider} conf={ocr_metrics.mean_confidence} pages={ocr_metrics.pages}{cer_str}")
            ocr_reports.append(OCRReport(
                doc_id=d.doc_id, title=d.title, source_url=d.source_url, fmt=d.fmt.value,
                ocr_used=True, provider=ocr_metrics.provider, pages=ocr_metrics.pages,
                mean_confidence=ocr_metrics.mean_confidence, cer=ocr_metrics.cer,
                cer_under_5pct=(ocr_metrics.cer < 0.05 if ocr_metrics.cer is not None else None),
            ))
        log(f"[extract] {d.title[:48]} -> {len(provs)} provisions")
    for p in provisions:
        db.save_provision(run_id, p)

    # mapping → evidence
    indicators = [i for pillar in pillars for i in get_indicators(pillar)]
    log(f"[map] {len(provisions)} provisions × {len(indicators)} indicators (LLM={llm.name})")
    mappings = mapping.map_provisions(
        run_id=run_id,
        provisions=provisions,
        pillar=None,
        indicators=indicators,
        source_texts=source_texts,
        doc_tags=doc_tags,
        llm=llm,
        top_k=top_k,
        log=log,
    )
    # KNOWN/NEW tagging against the judges' sample kit (law-level). NEW = found on our
    # own (worth the most points); KNOWN = the law was a sample-kit example.
    from . import sample_kit
    kit = sample_kit.load_known(settings.sample_kit_path or None)
    if kit is not None:
        from ..schemas import DiscoveryTag
        n_known = 0
        for m in mappings:
            known = sample_kit.is_known(m.economy.value, m.pillar, m.law_name, m.source_url, kit)
            m.discovery_tag = DiscoveryTag.KNOWN if known else DiscoveryTag.NEW
            n_known += known
        log(f"[tag] sample kit matched — KNOWN={n_known} NEW={len(mappings) - n_known}")

    for m in mappings:
        db.save_mapping(m)

    elapsed = round(time.perf_counter() - t0, 3)
    auto = sum(m.review_status == "auto_accepted" for m in mappings)
    review = sum(m.review_status == "pending_review" for m in mappings)
    quar = sum(m.review_status == "quarantined" for m in mappings)
    log(f"[done] {len(mappings)} mappings in {elapsed}s — auto={auto} review={review} quarantine={quar}")

    meta = RunMeta(
        run_id=run_id,
        economy=economy,
        pillars=pillars,
        started_at=started,
        finished_at=_now(),
        processing_time_seconds=elapsed,
        docs_discovered=len(docs),
        provisions_extracted=len(provisions),
        mappings_produced=len(mappings),
        ocr_provider=ocr.name,
        llm_provider=llm.name,
        model_version=llm.model_version,
        ocr_reports=ocr_reports,
    )
    db.finish_run(meta)
    return RunResult(meta=meta, mappings=mappings)
