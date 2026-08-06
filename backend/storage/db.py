"""Audit store — the spine of auditability.

Every run, document, provision, mapping, and human review action is persisted, so
any exported row can be traced back through the exact provision, retrieval log, OCR
metrics, and reviewer decisions that produced it. JSON blobs keep the schema simple
while preserving the full structured record.

Backed by SQLAlchemy (see `engine.py`), so the same code runs on the local SQLite
file today and on a hosted Postgres by setting `DATABASE_URL`. The public function
signatures below are unchanged from the original sqlite3 implementation — callers in
the pipeline, CLI, API and dashboard were not touched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..schemas import DiscoveredDoc, EvidenceMapping, Provision, RunMeta
from .engine import (
    documents, get_engine, init_schema, mappings, provisions, review_log, runs,
)


def _upsert(table, values: dict, pk_cols: list[str]):
    """INSERT … ON CONFLICT DO UPDATE, portable across SQLite and Postgres."""
    eng = get_engine()
    if eng.dialect.name == "sqlite":
        stmt = sqlite_insert(table).values(**values)
    else:  # postgresql
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(table).values(**values)
    update_cols = {k: v for k, v in values.items() if k not in pk_cols}
    return stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols) if update_cols else \
        stmt.on_conflict_do_nothing(index_elements=pk_cols)


def init_db() -> None:
    init_schema()


# ─────────── writes ───────────
def start_run(run_id, economy, pillars, started_at, ocr_provider, llm_provider, model_version,
              user_id: str | None = None) -> None:
    with get_engine().begin() as c:
        c.execute(_upsert(runs, {
            "run_id": run_id, "economy": economy, "pillars": json.dumps(pillars),
            "started_at": started_at, "ocr_provider": ocr_provider, "llm_provider": llm_provider,
            "model_version": model_version, "meta_json": "{}", "user_id": user_id,
        }, ["run_id"]))


def finish_run(meta: RunMeta) -> None:
    with get_engine().begin() as c:
        c.execute(update(runs).where(runs.c.run_id == meta.run_id).values(
            finished_at=meta.finished_at, meta_json=meta.model_dump_json()))


def save_doc(run_id: str, d: DiscoveredDoc) -> None:
    with get_engine().begin() as c:
        c.execute(_upsert(documents, {
            "doc_id": d.doc_id, "run_id": run_id, "economy": d.economy.value, "title": d.title,
            "source_url": d.source_url, "portal": d.portal, "fmt": d.fmt.value,
            "relevance": d.relevance_score, "discovery_tag": d.discovery_tag.value,
            "amendment_date": d.amendment_date, "doc_json": d.model_dump_json(),
        }, ["doc_id", "run_id"]))


def save_provision(run_id: str, p: Provision) -> None:
    with get_engine().begin() as c:
        c.execute(_upsert(provisions, {
            "provision_id": p.provision_id, "run_id": run_id, "doc_id": p.doc_id,
            "law_name": p.law_name, "article_section": p.article_section,
            "prov_json": p.model_dump_json(),
        }, ["provision_id", "run_id"]))


def save_mapping(m: EvidenceMapping) -> None:
    with get_engine().begin() as c:
        c.execute(_upsert(mappings, {
            "mapping_id": m.mapping_id, "run_id": m.run_id, "economy": m.economy.value,
            "pillar": m.pillar, "indicator_id": m.indicator_id, "confidence": m.confidence_score,
            "review_status": m.review_status.value, "human_note": m.human_note,
            "mapping_json": m.model_dump_json(),
        }, ["mapping_id"]))


def log_review(mapping_id, action, reviewer, note, ts, before_json, after_json) -> None:
    with get_engine().begin() as c:
        c.execute(insert(review_log).values(
            mapping_id=mapping_id, action=action, reviewer=reviewer, note=note, ts=ts,
            before_json=before_json, after_json=after_json))


# ─────────── reads ───────────
def get_mapping(mapping_id: str) -> EvidenceMapping | None:
    with get_engine().connect() as c:
        row = c.execute(select(mappings.c.mapping_json).where(
            mappings.c.mapping_id == mapping_id)).fetchone()
    return EvidenceMapping.model_validate_json(row[0]) if row else None


def list_mappings(run_id: str | None = None, status: str | None = None) -> list[EvidenceMapping]:
    q = select(mappings.c.mapping_json)
    if run_id:
        q = q.where(mappings.c.run_id == run_id)
    if status:
        q = q.where(mappings.c.review_status == status)
    q = q.order_by(mappings.c.confidence.desc())
    with get_engine().connect() as c:
        rows = c.execute(q).fetchall()
    return [EvidenceMapping.model_validate_json(r[0]) for r in rows]


def get_run(run_id: str) -> RunMeta | None:
    with get_engine().connect() as c:
        row = c.execute(select(runs.c.meta_json).where(runs.c.run_id == run_id)).fetchone()
    if not row or row[0] in (None, "{}"):
        return None
    return RunMeta.model_validate_json(row[0])


def list_runs(user_id: str | None = None, limit: int | None = None) -> list[dict]:
    """Run index, newest first. `user_id` scopes it to one account's history; omit it
    (CLI/API/admin) to list every run including the pre-accounts ones."""
    q = select(runs.c.run_id, runs.c.economy, runs.c.pillars, runs.c.started_at,
               runs.c.finished_at, runs.c.user_id)
    if user_id:
        q = q.where(runs.c.user_id == user_id)
    q = q.order_by(runs.c.started_at.desc())
    if limit:
        q = q.limit(limit)
    with get_engine().connect() as c:
        rows = c.execute(q).fetchall()
    return [dict(r._mapping) for r in rows]


def claim_run(run_id: str, user_id: str) -> None:
    """Attach a run to the account that launched it (set after the pipeline returns)."""
    with get_engine().begin() as c:
        c.execute(update(runs).where(runs.c.run_id == run_id).values(user_id=user_id))


def run_summary(user_id: str | None = None) -> dict:
    """Headline counts for the account's history panel."""
    from sqlalchemy import func
    q = select(func.count()).select_from(runs)
    if user_id:
        q = q.where(runs.c.user_id == user_id)
    mq = select(func.count()).select_from(mappings)
    if user_id:
        mq = mq.where(mappings.c.run_id.in_(select(runs.c.run_id).where(runs.c.user_id == user_id)))
    with get_engine().connect() as c:
        return {"runs": c.execute(q).scalar() or 0, "mappings": c.execute(mq).scalar() or 0}


def delete_run(run_id: str, user_id: str | None = None) -> bool:
    """Remove a run and everything traceable to it. When `user_id` is given the delete
    only lands if that account owns the run (so one user can't delete another's history)."""
    eng = get_engine()
    with eng.begin() as c:
        owner = c.execute(select(runs.c.user_id).where(runs.c.run_id == run_id)).fetchone()
        if not owner or (user_id is not None and owner[0] != user_id):
            return False
        for tbl in (documents, provisions, mappings):
            c.execute(delete(tbl).where(tbl.c.run_id == run_id))
        c.execute(delete(runs).where(runs.c.run_id == run_id))
    return True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
