"""Corpus store — durable, law-scoped records (L0–L3), plus the DDL for L4/L5.

Why this exists at all: today every artefact is scoped to a *run*. A law fetched for the
Pillar-6 run is re-fetched, re-OCR'd and re-split for the Pillar-7 run, and again tomorrow.
Here the unit is a **law version**, so work is done once per version of a law and reused by
every query for as long as the portal reports that version as current.

Tables live on the same SQLAlchemy metadata as the audit store, so `DATABASE_URL` still
switches the whole app to Postgres in one line and the existing five tables are untouched.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Float, Index, Integer, String, Table, Text, func, select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..storage.engine import get_engine, metadata

# ── L0: one row per law, stable across amendments ──
corpus_law = Table(
    "corpus_law", metadata,
    Column("law_id", String, primary_key=True),
    Column("economy", String, index=True),
    Column("portal", String),
    Column("title", Text),
    Column("law_number", String),
    Column("source_url", Text),          # landing page (the citable URL)
    Column("body_url", Text),            # fetchable full-text URL, when it differs
    Column("collection", String),        # act | amendment | subsidiary | code_of_practice
    Column("status", String),            # active | repealed
    Column("first_seen", String),
    Column("last_checked", String),
    Column("catalogue_json", Text),      # raw portal record, for provenance
)

# ── L1–L3: one row per VERSION of a law; the unit of work ──
corpus_version = Table(
    "corpus_version", metadata,
    Column("version_id", String, primary_key=True),
    Column("law_id", String, index=True),
    Column("economy", String, index=True),
    Column("version_key", String),       # the portal's own version signal (compilation/reprint date)
    Column("amendment_date", String),
    Column("content_sha256", String, index=True),
    Column("body_path", Text),
    Column("fmt", String),
    Column("bytes", Integer),
    Column("pages", Integer),
    Column("chars", Integer),
    Column("fetched_at", String),
    Column("etag", String),
    Column("ocr_used", Integer),
    Column("ocr_provider", String),
    Column("cer", Float),
    Column("extraction_version", String),
    Column("provisions_n", Integer),
    Column("state", String, index=True),  # discovered|fetched|extracted|split|failed
    Column("error", Text),
    Column("superseded_by", String),
    Column("updated_at", String),
)

# ── L3 detail: provisions, verbatim, with spans back into the extracted text ──
corpus_provision = Table(
    "corpus_provision", metadata,
    Column("provision_id", String, primary_key=True),
    Column("version_id", String, index=True),
    Column("economy", String, index=True),
    Column("law_name", Text),
    Column("law_number", String),
    Column("article_section", Text),
    Column("location_ref", String),
    Column("char_start", Integer),
    Column("char_end", Integer),
    Column("chars", Integer),
    Column("text", Text),
)
Index("ix_corpus_provision_econ_ver", corpus_provision.c.economy, corpus_provision.c.version_id)

# ── L5 (DDL only — grading is pending the retrieval redesign) ──
corpus_evidence = Table(
    "corpus_evidence", metadata,
    Column("evidence_id", String, primary_key=True),
    Column("version_id", String, index=True),
    Column("provision_id", String, index=True),
    Column("economy", String, index=True),
    Column("indicator_id", String, index=True),
    Column("selector_version", String, index=True),
    Column("grader_version", String, index=True),
    Column("satisfied", Integer),
    Column("confidence", Float),
    Column("retrieval_score", Float),
    Column("rationale", Text),
    Column("raw_score", Float),
    Column("impact", Text),
    Column("confidence_json", Text),
    Column("graded_at", String),
)

# Distinguishes "graded and rejected" from "never looked at" — without it, an indicator with
# no evidence row is ambiguous, and the honesty statement cannot be written truthfully.
corpus_coverage = Table(
    "corpus_coverage", metadata,
    Column("version_id", String, primary_key=True),
    Column("indicator_id", String, primary_key=True),
    Column("selector_version", String, primary_key=True),
    Column("n_provisions", Integer),
    Column("n_candidates", Integer),
    Column("n_graded", Integer),
    Column("checked_at", String),
)

# Freshness audit trail — proves to a judge that an answer was revalidated against the portal.
corpus_check = Table(
    "corpus_check", metadata,
    Column("check_id", String, primary_key=True),
    Column("economy", String, index=True),
    Column("checked_at", String),
    Column("source", String),            # catalogue_sweep | cited_laws
    Column("watermark", String),
    Column("n_checked", Integer),
    Column("n_changed", Integer),
    Column("detail_json", Text),
)

EXTRACTION_VERSION = "split@v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def law_id(economy: str, url: str) -> str:
    return f"{economy.lower()}-" + hashlib.sha1(f"{economy}|{url}".encode()).hexdigest()[:14]


def version_id(law_id_: str, version_key: str | None, content_sha: str | None) -> str:
    tag = (version_key or "").strip() or (content_sha or "")[:12] or "v0"
    return f"{law_id_}@{hashlib.sha1(tag.encode()).hexdigest()[:10]}"


def init() -> None:
    metadata.create_all(get_engine())


def _retry_write(fn, attempts: int = 6, base_delay: float = 0.4):
    """SQLite allows one writer at a time. A corpus build is deliberately run per economy in
    parallel (three different portals, three fetch loops), so writers DO collide — and a
    collision must not lose a law that has already been fetched, extracted and split. Retry
    with backoff and jitter; only a genuinely stuck lock escapes. Harmless on Postgres."""
    import random
    import time as _t

    from sqlalchemy.exc import OperationalError
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError as e:
            if "locked" not in str(e).lower() or attempt == attempts - 1:
                raise
            _t.sleep(base_delay * (2 ** attempt) + random.random() * 0.25)


def _upsert(table, values: dict, pk: list[str]):
    eng = get_engine()
    if eng.dialect.name == "sqlite":
        stmt = sqlite_insert(table).values(**values)
    else:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(table).values(**values)
    upd = {k: v for k, v in values.items() if k not in pk}
    return (stmt.on_conflict_do_update(index_elements=pk, set_=upd) if upd
            else stmt.on_conflict_do_nothing(index_elements=pk))


# ─────────────────────────── writes ───────────────────────────
def save_laws(rows: list[dict]) -> int:
    """Upsert catalogue records. `first_seen` is preserved on re-sweep (it is only set on
    insert), so a law's discovery date survives every later catalogue run."""
    if not rows:
        return 0
    ts = now()
    eng = get_engine()
    with eng.begin() as c:
        existing = {r[0] for r in c.execute(select(corpus_law.c.law_id).where(
            corpus_law.c.economy == rows[0]["economy"]))}
        for r in rows:
            vals = dict(r)
            vals.setdefault("status", "active")
            vals["last_checked"] = ts
            if vals["law_id"] in existing:
                vals.pop("first_seen", None)      # keep the original discovery date
            else:
                vals["first_seen"] = ts
            c.execute(_upsert(corpus_law, vals, ["law_id"]))
    return len(rows)


def save_version(values: dict) -> None:
    """Insert/refresh a version and SUPERSEDE the law's other versions.

    Without this, a law that has been rebuilt (portal amended it, or an extraction bug was
    fixed) keeps every historical version in the store, and a retrieval pass over the economy
    sees the same provision several times — inflating recall and duplicating output rows. The
    old rows are kept for audit; they are simply no longer 'current'."""
    from sqlalchemy import update
    values = dict(values)
    values["updated_at"] = now()
    vid, lid = values.get("version_id"), values.get("law_id")

    def _w():
        with get_engine().begin() as c:
            c.execute(_upsert(corpus_version, values, ["version_id"]))
            if lid and vid:
                c.execute(update(corpus_version)
                          .where(corpus_version.c.law_id == lid,
                                 corpus_version.c.version_id != vid,
                                 corpus_version.c.superseded_by.is_(None))
                          .values(superseded_by=vid))
    _retry_write(_w)


def set_state(version_id_: str, state: str, error: str | None = None, **extra) -> None:
    vals = {"version_id": version_id_, "state": state, "updated_at": now(), **extra}
    if error is not None:
        vals["error"] = error[:2000]

    def _w():
        with get_engine().begin() as c:
            c.execute(_upsert(corpus_version, vals, ["version_id"]))
    _retry_write(_w)


def save_provisions(version_id_: str, economy: str, provisions: list) -> int:
    """Replace a version's provisions (a re-split must not leave stale rows behind).

    Provision ids are namespaced by VERSION. `extract_provisions` numbers provisions within a
    document (`<doc_id>#p12`), which is unique per run but collides the moment the same law is
    stored at two versions — and versions are the whole point of this store."""
    from sqlalchemy import delete
    rows = []
    for p in provisions:
        span = p.char_span or (0, 0)
        rows.append({
            "provision_id": f"{version_id_}::{p.provision_id.rsplit('#', 1)[-1]}",
            "version_id": version_id_, "economy": economy,
            "law_name": p.law_name, "law_number": p.law_number,
            "article_section": p.article_section, "location_ref": p.location_ref,
            "char_start": span[0], "char_end": span[1],
            "chars": len(p.verbatim_snippet), "text": p.verbatim_snippet,
        })
    def _w():
        with get_engine().begin() as c:
            c.execute(delete(corpus_provision).where(corpus_provision.c.version_id == version_id_))
            for i in range(0, len(rows), 500):
                if rows[i:i + 500]:
                    c.execute(corpus_provision.insert(), rows[i:i + 500])
    _retry_write(_w)
    return len(rows)


def log_check(economy: str, source: str, watermark: str | None,
              n_checked: int, n_changed: int, detail: dict | None = None) -> None:
    ts = now()
    with get_engine().begin() as c:
        c.execute(_upsert(corpus_check, {
            "check_id": hashlib.sha1(f"{economy}|{source}|{ts}".encode()).hexdigest()[:16],
            "economy": economy, "checked_at": ts, "source": source, "watermark": watermark,
            "n_checked": n_checked, "n_changed": n_changed,
            "detail_json": json.dumps(detail or {})[:200_000],
        }, ["check_id"]))


# ─────────────────────────── reads ───────────────────────────
def list_laws(economy: str, collection: str | None = None, status: str = "active") -> list[dict]:
    q = select(corpus_law).where(corpus_law.c.economy == economy)
    if collection:
        q = q.where(corpus_law.c.collection == collection)
    if status:
        q = q.where(corpus_law.c.status == status)
    with get_engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q)]


def get_law(law_id_: str) -> dict | None:
    with get_engine().connect() as c:
        r = c.execute(select(corpus_law).where(corpus_law.c.law_id == law_id_)).fetchone()
    return dict(r._mapping) if r else None


def versions_for(law_ids: list[str]) -> dict[str, dict]:
    """Latest known version row per law_id."""
    if not law_ids:
        return {}
    out: dict[str, dict] = {}
    with get_engine().connect() as c:
        for i in range(0, len(law_ids), 400):
            chunk = law_ids[i:i + 400]
            for r in c.execute(select(corpus_version).where(corpus_version.c.law_id.in_(chunk))):
                d = dict(r._mapping)
                prev = out.get(d["law_id"])
                if prev is None or (d.get("updated_at") or "") > (prev.get("updated_at") or ""):
                    out[d["law_id"]] = d
    return out


def load_provisions(economy: str, version_ids: list[str] | None = None,
                    current_only: bool = True) -> list[dict]:
    """Provisions for an economy. By default only CURRENT versions — a superseded version's
    provisions are still on disk for audit, but they must never re-enter retrieval."""
    q = select(corpus_provision).where(corpus_provision.c.economy == economy)
    if version_ids is not None:
        if not version_ids:
            return []
        q = q.where(corpus_provision.c.version_id.in_(version_ids))
    elif current_only:
        q = q.where(corpus_provision.c.version_id.in_(
            select(corpus_version.c.version_id).where(
                corpus_version.c.economy == economy,
                corpus_version.c.superseded_by.is_(None),
                corpus_version.c.state == "split")))
    with get_engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q)]


def stats(economy: str | None = None) -> dict:
    eng = get_engine()
    out: dict = {}
    with eng.connect() as c:
        for name, tbl, col in (("laws", corpus_law, corpus_law.c.economy),
                               ("versions", corpus_version, corpus_version.c.economy),
                               ("provisions", corpus_provision, corpus_provision.c.economy)):
            q = select(col, func.count()).group_by(col)
            rows = {r[0]: r[1] for r in c.execute(q)}
            out[name] = rows if economy is None else {economy: rows.get(economy, 0)}
        q = select(corpus_version.c.state, func.count()).group_by(corpus_version.c.state)
        if economy:
            q = q.where(corpus_version.c.economy == economy)
        out["states"] = {r[0]: r[1] for r in c.execute(q)}
    return out
