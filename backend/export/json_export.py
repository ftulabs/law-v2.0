"""JSON export for technical reviewers.

Carries everything the CSV omits: processing_time, OCR quality metrics, raw_context,
source metadata, model version, retrieval logs, and the confidence-scoring
explanation per mapping. This is the machine-auditable artefact.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..schemas import EvidenceMapping, RunResult


def build_payload(result: RunResult) -> dict:
    from ..pipeline.scoring import aggregate_indicator_scores
    payload: dict = {
        "run": result.meta.model_dump(),
        "provider_versions": {
            "ocr_provider": result.meta.ocr_provider,
            "llm_provider": result.meta.llm_provider,
            "model_version": result.meta.model_version,
        },
        "summary": _summary(result.mappings),
        # document-level OCR proof (scanned PDFs): provider + measured CER vs reference,
        # independent of whether those provisions were mapped. Technical-judge audit path.
        "ocr_reports": [r.model_dump() for r in result.meta.ocr_reports],
        "mappings": [_mapping_payload(m) for m in result.mappings],
    }
    agg = aggregate_indicator_scores(result.mappings)
    if agg:
        payload["analytical_index"] = {
            "_note": "not part of the submission — RDTII index computation only",
            "aggregate_indicator_scores": {k: v for k, v in sorted(agg.items())},
        }
    return payload


def _summary(mappings: list[EvidenceMapping]) -> dict:
    by_status: dict[str, int] = {}
    for m in mappings:
        by_status[m.review_status.value] = by_status.get(m.review_status.value, 0) + 1
    return {"total": len(mappings), "by_status": by_status}


def _mapping_payload(m: EvidenceMapping) -> dict:
    ocr = m.ocr.model_dump()
    return {
        "mapping_id": m.mapping_id,
        "economy": m.economy.value,
        "pillar": m.pillar,
        "indicator_id": m.indicator_id,
        "law_name": m.law_name,
        "law_number": m.law_number,
        "last_amended": m.last_amended,
        "article_section": m.article_section,
        "location_reference": m.location_ref,
        "verbatim_snippet": m.verbatim_snippet,
        "source_url": m.source_url,
        "source_pdf_path": m.source_pdf_path,                    # local retrieved file
        "mapping_rationale": m.mapping_rationale,
        "raw_score": m.raw_score,                                # Zone-3 RDTII score (0/0.5/1)
        "impact": m.impact,                                      # Database "Impact or comments"
        "confidence_score": m.confidence_score,
        "confidence_breakdown": m.confidence.model_dump(),       # scoring explanation
        "discovery_tag": m.discovery_tag.value,
        "coverage": m.coverage,                                  # Horizontal | Sectoral
        "flag_for_review": m.review_status.value in ("pending_review", "quarantined"),
        "notes": m.notes,
        "review_status": m.review_status.value,
        "scope_flag": m.scope_flag,
        "provision_id": m.provision_id,
        "raw_context": m.raw_context,                            # what the model saw (HITL)
        "raw_context_before": m.raw_context_before,              # README extended field
        "raw_context_after": m.raw_context_after,                # README extended field
        "pdf_is_scanned": bool(ocr.get("used")),                 # OCR ran => image/scanned PDF
        # Measured CER vs ground-truth sidecar when available (raster-OCR engines); else a
        # confidence-derived proxy; null for deterministic text-layer extraction.
        "ocr_quality_cer": (round(ocr["cer"], 4) if ocr.get("cer") is not None
                            else round(1 - ocr["mean_confidence"], 4)
                            if ocr.get("mean_confidence") is not None else None),
        "ocr_cer_measured": ocr.get("cer") is not None,          # True = real CER vs reference
        "retrieval_method": "hybrid (BM25 + dense MiniLM) + cross-encoder rerank, RRF fusion",
        "ocr_quality": {                                         # OCR quality metrics (detail)
            "provider": ocr.get("provider"),
            "used": ocr.get("used"),
            "mean_confidence": ocr.get("mean_confidence"),
            "cer": ocr.get("cer"),                               # measured CER vs reference (or null)
            "pages": ocr.get("pages"),
            "low_conf_pages": ocr.get("low_conf_pages"),
        },
        "model_version": m.model_version,                        # LLM (+OCR) version used
        "retrieval_log": m.retrieval_log,                        # retrieval logs
        "human_note": m.human_note,
    }


def export_json(result: RunResult, out_dir: Path | None = None, out_stem: str | None = None) -> Path:
    out_dir = out_dir or settings.output_path
    path = Path(out_dir) / f"{out_stem or ('veritrade_' + result.meta.run_id)}.json"
    path.write_text(json.dumps(build_payload(result), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
