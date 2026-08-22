"""End-to-end pipeline orchestration (Zone 1 → Zone 2 → outputs).

Ties the stages together, persists everything to the audit store, and returns a
RunResult. Designed to be called from the CLI, the FastAPI route, or the Streamlit
app. Pure function of its inputs + provider config — reproducible in mock mode.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from .. import metering
from ..config import settings
from ..providers import get_llm_provider, get_ocr_provider
from ..rdtii import get_indicators
from ..schemas import Economy, OCRReport, RunMeta, RunResult
from ..storage import db
from . import discovery, extraction, mapping, scoring
from .ocr import get_document_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _law_identity(name: str) -> str:
    """Normalised law-name key for same-law dedup. Folds case / punctuation / portal suffix
    and drops a TRAILING edition/enactment year, so all of 'CYBERSECURITY ACT 2018',
    'Cybersecurity Act 2018' and a title-less 'Cybersecurity Act' collapse together. The year
    is only stripped at the end, and 'Amendment' is kept, so the 2024 Amendment Act
    ('cybersecurity amendment act') never merges with the principal Act ('cybersecurity act')."""
    import re
    from .discovery import _clean_title
    n = re.sub(r"[^a-z0-9]+", " ", _clean_title(name or "").lower()).strip()
    return re.sub(r"\s+(?:19|20)\d{2}$", "", n).strip()


def _dedup_provisions_by_law(provisions, docs, log):
    """Drop duplicate documents that resolved to the same law, keeping the current version.

    Groups extracted provisions by their (resolved) law name and, within each group, keeps
    the document with the best version rank — a non-as-published URL beats a `/Published/`
    gazette snapshot; ties break toward the fuller (more-provisions) text, i.e. the
    consolidated edition. Provisions from the other documents are discarded."""
    from collections import defaultdict
    by_doc: dict[str, list] = defaultdict(list)
    for p in provisions:
        by_doc[p.doc_id].append(p)
    doc_by_id = {d.doc_id: d for d in docs}

    def _rank(doc_id: str) -> tuple:
        url = (doc_by_id[doc_id].source_url or "").lower() if doc_id in doc_by_id else ""
        not_aspublished = 0 if "/published/" in url else 1
        return (not_aspublished, len(by_doc[doc_id]))

    groups: dict[str, list[str]] = defaultdict(list)
    for doc_id, plist in by_doc.items():
        groups[_law_identity(plist[0].law_name) or doc_id].append(doc_id)

    kept: set[str] = set()
    for ids in groups.values():
        best = max(ids, key=_rank)
        kept.add(best)
        for i in ids:
            if i != best:
                log(f"[dedup] '{by_doc[i][0].law_name[:42]}' — dropped duplicate "
                    f"{doc_by_id[i].source_url[:58] if i in doc_by_id else i} "
                    f"({len(by_doc[i])} prov) for the current version")
    return [p for p in provisions if p.doc_id in kept]


def _no_evidence_placeholders(run_id, economy, indicators, mappings, log) -> list:
    """Explicit 'No evidence' row per indicator with no submittable mapping."""
    from ..schemas import DiscoveryTag, EvidenceMapping, ReviewStatus, SUBMITTABLE_STATUSES
    from .websearch import OFFICIAL_PORTAL

    covered = {m.indicator_id for m in mappings if m.review_status.value in SUBMITTABLE_STATUSES}
    portal = OFFICIAL_PORTAL.get(economy.value, "")
    out = []
    for ind in indicators:
        if ind.indicator_id in covered:
            continue
        out.append(EvidenceMapping(
            mapping_id=f"map-noevidence-{ind.indicator_id.lower()}",
            run_id=run_id, economy=economy, pillar=ind.pillar, indicator_id=ind.indicator_id,
            law_name="No provision found", law_number=None, last_amended=None,
            article_section="N/A", location_ref=None,
            # exact placeholder wording per the judges' Q&A (email 2026-07): snippet "No
            # evidence found"; Confidence and Discovery Tag render as "N/A" in the CSV.
            verbatim_snippet="No evidence found",
            mapping_rationale=(f"No active provision satisfying the legal test of {ind.indicator_id} "
                               f"({ind.title}) was identified on the official portal."),
            source_url=(f"https://{portal}/" if portal else ""),
            confidence_score=0.0, discovery_tag=DiscoveryTag.NEW,
            coverage=None,
            notes=("No evidence — the pipeline searched the official portal for this indicator "
                   "and found no active provision satisfying its legal test."),
            review_status=ReviewStatus.AUTO_ACCEPTED,
            provision_id=f"no-evidence-{ind.indicator_id.lower()}",
        ))
    if out:
        log(f"[placeholder] {len(out)} indicator(s) without evidence -> explicit 'No evidence' rows: "
            + ", ".join(m.indicator_id for m in out))
    return out


def _resolve_ocr(name, log, economy=None):
    """Resolve the OCR engine AND its recognition language, then say so in the log.

    `economy` selects the per-script model (see providers/ocr_languages.py). Without it the
    engine loads whatever dictionary it defaults to, which is invisible on Latin text and
    silently destructive on Thai/Cyrillic/Vietnamese — so the language is resolved here and
    printed, rather than being a setting nobody can confirm took effect.
    """
    from ..providers.ocr_languages import is_validated, ocr_code, profile_for

    eco = getattr(economy, "value", economy)
    try:
        provider = get_ocr_provider(name, economy=eco) if name else get_ocr_provider(economy=eco)
    except Exception as e:  # noqa: BLE001 — a judge experimenting must never crash a run
        log(f"[warn] OCR provider '{name}' unavailable ({e}); falling back to mock")
        return get_ocr_provider("mock")

    prof = profile_for(eco)
    code = ocr_code(provider.name, eco)
    if code is None and prof.rapidocr is None:
        # The configured engine has no model for this script at all.
        log(f"[ocr] {provider.name}: NO model for {prof.script} — recommended engine is "
            f"{prof.preferred[0] if prof.preferred else 'none'}; output will be unreliable")
    else:
        log(f"[ocr] engine={provider.name} script={prof.script} lang={code or 'default'}"
            f"{'' if is_validated(eco) else ' (accuracy UNVALIDATED for this script)'}")
    return provider


def _resolve_llm(name, model, api_key, log):
    try:
        return get_llm_provider(name, model=model, api_key=api_key) if name else get_llm_provider()
    except Exception as e:  # noqa: BLE001
        log(f"[warn] LLM provider '{name}' unavailable ({e}); falling back to mock")
        return get_llm_provider("mock")


def _result_cache_file(economy, pillars, use_samples, ocr, llm, top_k, do_score, pdf_path):
    import hashlib
    key = (f"{economy.value}|{sorted(pillars)}|{use_samples}|{ocr.name}|{llm.name}|"
           f"{llm.model_version}|{top_k}|{do_score}|{pdf_path or ''}")
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    d = settings.cache_path / "_results"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{economy.value}_P{''.join(map(str, sorted(pillars)))}_{h}.json"


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
    scoring_enabled: bool | None = None,
    use_result_cache: bool = True,
) -> RunResult:
    run_id = "run-" + uuid.uuid4().hex[:8]
    t0 = time.perf_counter()
    started = _now()
    # Cost is counted from here, by the providers themselves as they spend. The template wants
    # it "per run and per engine ... without manual arithmetic", and the arithmetic is the part
    # that cannot be done after the fact: token counts live only in the API response.
    meter = metering.start(run_id)

    # runtime-selected providers (dashboard) with safe fallback to mock
    ocr = _resolve_ocr(ocr_provider, log, economy)
    llm = _resolve_llm(llm_provider, llm_model, llm_api_key, log)
    log(f"[providers] OCR={ocr.name} LLM={llm.name} ({llm.model_version})")

    # full-result cache: identical inputs → return the stored result, no live run
    do_score = settings.scoring_enabled if scoring_enabled is None else scoring_enabled
    cache_f = _result_cache_file(economy, pillars, use_samples, ocr, llm, top_k, do_score, pdf_path)
    if use_result_cache and settings.result_cache_enabled and cache_f.exists():
        ttl = settings.result_cache_ttl_hours
        if ttl <= 0 or (time.time() - cache_f.stat().st_mtime) < ttl * 3600:
            try:
                result = RunResult.model_validate_json(cache_f.read_text(encoding="utf-8"))
                log(f"[cache] result cache hit ({cache_f.name}, run {result.meta.run_id}) — "
                    f"delete the file or use a fresh run to re-crawl live")
                return result
            except Exception as e:  # noqa: BLE001 — unreadable cache → run live
                log(f"[cache] result cache unreadable ({type(e).__name__}); running live")

    db.init_db()
    db.start_run(run_id, economy.value, pillars, started, ocr.name, llm.name, llm.model_version)

    # discover across all requested pillars (union) — or use a single provided file
    _t = time.perf_counter()
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
    log(f"[timing] discovery {time.perf_counter() - _t:.1f}s")

    # Zone 1b — fetch bodies for live-discovered docs (sample/file docs already have a path)
    _t = time.perf_counter()
    if not use_samples and not pdf_path:
        from .fetch import fetch_to_cache
        from .discovery import _resolve_pdf_url
        fetched = 0
        kept, by_content = [], {}   # sha256 -> doc already kept
        for d in docs:
            if d.local_path:
                kept.append(d)
                log(f"[doc] {d.title[:80]} | {d.source_url}")
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
                log(f"[fetch] skip duplicate body (same SHA as '{prior.title[:70]}'): {d.title[:70]}")
                continue
            by_content[fr.sha256] = d
            d.local_path, d.fmt = fr.local_path, fr.fmt
            fetched += 1
            kept.append(d)
            # A structured, parseable line (title + link) — the dashboard's "documents found so
            # far" panel renders these live, so a researcher can start reading source law while
            # the run continues instead of staring at a bare progress bar.
            log(f"[doc] {d.title[:80]} | {d.source_url}")
        dropped = len(docs) - len(kept)
        docs = kept
        log(f"[fetch] retrieved {fetched} bodies into cache"
            + (f" ({dropped} duplicate/failed dropped)" if dropped else ""))
        log(f"[timing] fetch/crawl {time.perf_counter() - _t:.1f}s")
    else:
        for d in docs:
            log(f"[doc] {d.title[:80]} | {d.source_url}")

    for d in docs:
        db.save_doc(run_id, d)

    # extraction (+OCR) → provisions. Documents are independent of each other, so this runs
    # concurrently (was strictly sequential) — extraction is the single biggest per-run cost
    # bucket, and wall-clock now scales with the slowest ONE document, not the sum of all of
    # them. Each worker only computes and returns its result; every shared list/dict mutation
    # and log line happens back on the main thread via _record_extraction, so nothing needs a
    # lock. as_completed() (not .map()) surfaces each document as soon as IT finishes, so the
    # per-document log lines below still stream out incrementally, in whatever order they land.
    _t = time.perf_counter()
    provisions, source_texts, doc_tags, ocr_reports = [], {}, {}, []

    def _extract_one(d):
        raw, ocr_metrics = get_document_text(d, ocr_provider=ocr)
        provs = extraction.extract_provisions(d, raw, ocr_metrics)
        return d, raw, ocr_metrics, provs

    def _record_extraction(d, raw, ocr_metrics, provs) -> None:
        source_texts[d.doc_id] = raw
        doc_tags[d.doc_id] = d.discovery_tag
        provisions.extend(provs)
        if ocr_metrics.notes == "js_app_shell":
            log(f"[extract] {d.title[:70]} -> JS-rendered page, no static law text "
                f"(set CRAWL_BROWSER=true + run `scrapling install` to render it)")
            return
        if ocr_metrics.used:
            cer_str = (f" CER={ocr_metrics.cer*100:.2f}% {'PASS<5%' if ocr_metrics.cer < 0.05 else 'OVER-5%'}"
                       if ocr_metrics.cer is not None else "")
            log(f"[ocr] {d.title[:70]} via {ocr_metrics.provider} conf={ocr_metrics.mean_confidence} pages={ocr_metrics.pages}{cer_str}")
            ocr_reports.append(OCRReport(
                doc_id=d.doc_id, title=d.title, source_url=d.source_url, fmt=d.fmt.value,
                ocr_used=True, provider=ocr_metrics.provider, pages=ocr_metrics.pages,
                mean_confidence=ocr_metrics.mean_confidence, cer=ocr_metrics.cer,
                cer_under_5pct=(ocr_metrics.cer < 0.05 if ocr_metrics.cer is not None else None),
            ))
        # Show the resolved law name (recovered from content when the discovery title was a
        # heading/UUID), so the log reflects what actually lands in the output CSV.
        shown = provs[0].law_name if provs else d.title
        log(f"[extract] {shown[:70]} -> {len(provs)} provisions")

    workers = max(1, min(settings.extraction_concurrency, len(docs) or 1))
    if workers > 1 and len(docs) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for fut in as_completed(ex.submit(_extract_one, d) for d in docs):
                _record_extraction(*fut.result())
    else:
        for d in docs:
            _record_extraction(*_extract_one(d))

    # Same-law dedup by resolved name. A portal serves one law under several URLs whose
    # bytes differ (an as-enacted gazette snapshot vs the current consolidated edition both
    # recover to "Cybersecurity Act 2018"), which content-SHA dedup can't catch. Collapse
    # them, keeping the CURRENT version: a non-as-published URL first, then the fuller text.
    provisions = _dedup_provisions_by_law(provisions, docs, log)
    for p in provisions:
        db.save_provision(run_id, p)
    log(f"[timing] extraction+OCR {time.perf_counter() - _t:.1f}s ({len(provisions)} provisions)")

    # mapping → evidence
    _t = time.perf_counter()
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
    log(f"[timing] mapping total {time.perf_counter() - _t:.1f}s")
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

    # Zone 3 (OPTIONAL, opt-in) — assign each measure its RDTII Raw Score (0/0.5/1) + Impact.
    # Off by default (settings.scoring_enabled) so the mandatory discover→extract→map flow stays
    # lean (fewer LLM calls on a rate-limited key); the caller (CLI flag / dashboard toggle) can
    # turn it on per run. Scoring runs AFTER mapping and never alters the mapping results.
    if do_score and mappings:
        log(f"[score] scoring {len(mappings)} measures (LLM={llm.name})")
        scoring.score_mappings(mappings, llm=llm, log=log)

    # indicators with no evidence still need an explicit placeholder row (blank = penalty)
    mappings.extend(_no_evidence_placeholders(run_id, economy, indicators, mappings, log))

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
        cost=meter.report(),
    )
    log(f"[cost] {meta.cost.get('total_usd', 0):.4f} USD"
        + ("" if meta.cost.get("total_is_complete") else
           f"  (floor — unpriced: {', '.join(meta.cost.get('unpriced', []))})"))
    db.finish_run(meta)
    result = RunResult(meta=meta, mappings=mappings)
    if settings.result_cache_enabled:
        try:
            cache_f.write_text(result.model_dump_json(), encoding="utf-8")
        except Exception:  # noqa: BLE001 — caching is best-effort
            pass
    return result
