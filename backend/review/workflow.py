"""Human-in-the-loop review workflow.

Reviewers act on mappings the confidence router put in `pending_review` (and may
re-open `quarantined`/`auto_accepted`). Every action writes an immutable row to
review_log with before/after snapshots, so the human decision trail is itself
auditable. Corrections let a reviewer fix the indicator, snippet, or rationale.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import EvidenceMapping, ReviewStatus
from ..storage import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue(run_id: str | None = None) -> list[EvidenceMapping]:
    """Mappings awaiting a human decision."""
    return db.list_mappings(run_id=run_id, status=ReviewStatus.PENDING_REVIEW.value)


def _act(mapping_id: str, action: str, new_status: ReviewStatus, reviewer: str, note: str,
         mutate=None) -> EvidenceMapping | None:
    m = db.get_mapping(mapping_id)
    if m is None:
        return None
    before = m.model_dump_json()
    m.review_status = new_status
    m.human_note = note or m.human_note
    if mutate:
        mutate(m)
    db.save_mapping(m)
    db.log_review(mapping_id, action, reviewer, note, _now(), before, m.model_dump_json())
    return m


def approve(mapping_id: str, reviewer: str = "reviewer", note: str = "") -> EvidenceMapping | None:
    return _act(mapping_id, "approve", ReviewStatus.APPROVED, reviewer, note)


def reject(mapping_id: str, reviewer: str = "reviewer", note: str = "") -> EvidenceMapping | None:
    return _act(mapping_id, "reject", ReviewStatus.REJECTED, reviewer, note)


def correct(mapping_id: str, fields: dict, reviewer: str = "reviewer", note: str = "") -> EvidenceMapping | None:
    """Apply reviewer edits. Allowed: indicator_id, pillar, article_section,
    verbatim_snippet, mapping_rationale, scope_flag."""
    allowed = {"indicator_id", "pillar", "article_section", "verbatim_snippet", "mapping_rationale", "scope_flag"}

    def mutate(m: EvidenceMapping):
        for k, v in fields.items():
            if k in allowed:
                setattr(m, k, v)
    return _act(mapping_id, "correct", ReviewStatus.CORRECTED, reviewer, note, mutate)


def summary(run_id: str | None = None) -> dict:
    rows = db.list_mappings(run_id=run_id)
    counts: dict[str, int] = {}
    for m in rows:
        counts[m.review_status.value] = counts.get(m.review_status.value, 0) + 1
    return {"total": len(rows), "by_status": counts}
