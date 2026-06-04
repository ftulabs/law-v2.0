"""SQLite audit store — the spine of auditability.

Every run, document, provision, mapping, and human review action is persisted, so
any exported row can be traced back through the exact provision, retrieval log, OCR
metrics, and reviewer decisions that produced it. JSON blobs keep the schema simple
while preserving the full structured record.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import settings
from ..schemas import DiscoveredDoc, EvidenceMapping, Provision, RunMeta

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, economy TEXT, pillars TEXT, started_at TEXT,
    finished_at TEXT, ocr_provider TEXT, llm_provider TEXT, model_version TEXT,
    meta_json TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT, run_id TEXT, economy TEXT, title TEXT, source_url TEXT,
    portal TEXT, fmt TEXT, relevance REAL, discovery_tag TEXT, amendment_date TEXT,
    doc_json TEXT, PRIMARY KEY (doc_id, run_id)
);
CREATE TABLE IF NOT EXISTS provisions (
    provision_id TEXT, run_id TEXT, doc_id TEXT, law_name TEXT, article_section TEXT,
    prov_json TEXT, PRIMARY KEY (provision_id, run_id)
);
CREATE TABLE IF NOT EXISTS mappings (
    mapping_id TEXT PRIMARY KEY, run_id TEXT, economy TEXT, pillar INT,
    indicator_id TEXT, confidence REAL, review_status TEXT, human_note TEXT,
    mapping_json TEXT
);
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mapping_id TEXT, action TEXT,
    reviewer TEXT, note TEXT, ts TEXT, before_json TEXT, after_json TEXT
);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


# ─────────── writes ───────────
def start_run(run_id, economy, pillars, started_at, ocr_provider, llm_provider, model_version) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs(run_id,economy,pillars,started_at,ocr_provider,llm_provider,model_version,meta_json)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (run_id, economy, json.dumps(pillars), started_at, ocr_provider, llm_provider, model_version, "{}"),
        )


def finish_run(meta: RunMeta) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE runs SET finished_at=?, meta_json=? WHERE run_id=?",
            (meta.finished_at, meta.model_dump_json(), meta.run_id),
        )


def save_doc(run_id: str, d: DiscoveredDoc) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (d.doc_id, run_id, d.economy.value, d.title, d.source_url, d.portal, d.fmt.value,
             d.relevance_score, d.discovery_tag.value, d.amendment_date, d.model_dump_json()),
        )


def save_provision(run_id: str, p: Provision) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO provisions VALUES(?,?,?,?,?,?)",
            (p.provision_id, run_id, p.doc_id, p.law_name, p.article_section, p.model_dump_json()),
        )


def save_mapping(m: EvidenceMapping) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO mappings VALUES(?,?,?,?,?,?,?,?,?)",
            (m.mapping_id, m.run_id, m.economy.value, m.pillar, m.indicator_id,
             m.confidence_score, m.review_status.value, m.human_note, m.model_dump_json()),
        )


def log_review(mapping_id, action, reviewer, note, ts, before_json, after_json) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO review_log(mapping_id,action,reviewer,note,ts,before_json,after_json)"
            " VALUES(?,?,?,?,?,?,?)",
            (mapping_id, action, reviewer, note, ts, before_json, after_json),
        )


# ─────────── reads ───────────
def get_mapping(mapping_id: str) -> EvidenceMapping | None:
    with _conn() as c:
        row = c.execute("SELECT mapping_json FROM mappings WHERE mapping_id=?", (mapping_id,)).fetchone()
    return EvidenceMapping.model_validate_json(row["mapping_json"]) if row else None


def list_mappings(run_id: str | None = None, status: str | None = None) -> list[EvidenceMapping]:
    q, args = "SELECT mapping_json FROM mappings", []
    where = []
    if run_id:
        where.append("run_id=?"); args.append(run_id)
    if status:
        where.append("review_status=?"); args.append(status)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY confidence DESC"
    with _conn() as c:
        rows = c.execute(q, args).fetchall()
    return [EvidenceMapping.model_validate_json(r["mapping_json"]) for r in rows]


def get_run(run_id: str) -> RunMeta | None:
    with _conn() as c:
        row = c.execute("SELECT meta_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row or row["meta_json"] in (None, "{}"):
        return None
    return RunMeta.model_validate_json(row["meta_json"])


def list_runs() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT run_id,economy,pillars,started_at,finished_at FROM runs ORDER BY started_at DESC").fetchall()
    return [dict(r) for r in rows]
