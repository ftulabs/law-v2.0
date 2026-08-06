"""SQLAlchemy engine + table definitions — the portable storage spine.

Why SQLAlchemy: the audit store started as raw `sqlite3`, which pinned us to one
file on one box. Everything now goes through a single engine built from
`settings.sqlalchemy_url`, so moving to a hosted Postgres is a one-line change
(`DATABASE_URL=postgresql+psycopg://…`) with no query rewrites.

The five original tables keep their EXACT historical column layout so an existing
`outputs/veritrade.db` (hundreds of runs, ~220k provisions) keeps reading without a
migration. New in this phase: `users` + `user_sessions`, and a nullable
`runs.user_id` so every run is traceable to whoever launched it.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    create_engine, inspect, text,
)
from sqlalchemy.engine import Engine

from ..config import settings

metadata = MetaData()

# ── original audit tables (column order/names frozen for backward compatibility) ──
runs = Table(
    "runs", metadata,
    Column("run_id", String, primary_key=True),
    Column("economy", String), Column("pillars", Text), Column("started_at", String),
    Column("finished_at", String), Column("ocr_provider", String),
    Column("llm_provider", String), Column("model_version", String),
    Column("meta_json", Text),
    Column("user_id", String, index=True),   # added this phase; NULL for historical runs
)
documents = Table(
    "documents", metadata,
    Column("doc_id", String, primary_key=True), Column("run_id", String, primary_key=True),
    Column("economy", String), Column("title", Text), Column("source_url", Text),
    Column("portal", String), Column("fmt", String), Column("relevance", Float),
    Column("discovery_tag", String), Column("amendment_date", String), Column("doc_json", Text),
)
provisions = Table(
    "provisions", metadata,
    Column("provision_id", String, primary_key=True), Column("run_id", String, primary_key=True),
    Column("doc_id", String), Column("law_name", Text), Column("article_section", Text),
    Column("prov_json", Text),
)
mappings = Table(
    "mappings", metadata,
    Column("mapping_id", String, primary_key=True), Column("run_id", String, index=True),
    Column("economy", String), Column("pillar", Integer), Column("indicator_id", String),
    Column("confidence", Float), Column("review_status", String), Column("human_note", Text),
    Column("mapping_json", Text),
)
review_log = Table(
    "review_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mapping_id", String), Column("action", String), Column("reviewer", String),
    Column("note", Text), Column("ts", String), Column("before_json", Text), Column("after_json", Text),
)

# ── accounts ──
users = Table(
    "users", metadata,
    Column("user_id", String, primary_key=True),
    Column("email", String, unique=True, nullable=False, index=True),
    Column("name", String),
    Column("organisation", String),
    # NULL for accounts that only ever sign in with Google (no local password to store)
    Column("password_hash", String),
    Column("auth_provider", String, default="password"),   # "password" | "google"
    Column("created_at", DateTime), Column("last_login_at", DateTime),
    Column("is_active", Integer, default=1),
)
user_sessions = Table(
    "user_sessions", metadata,
    # the raw token never lands in the DB — only its SHA-256, so a database leak
    # cannot be replayed as a login
    Column("token_hash", String, primary_key=True),
    Column("user_id", String, index=True, nullable=False),
    Column("created_at", DateTime), Column("expires_at", DateTime),
)

_engine: Engine | None = None


def get_engine() -> Engine:
    """Process-wide engine. SQLite needs check_same_thread=False because Streamlit
    serves each session from its own thread."""
    global _engine
    if _engine is None:
        url = settings.sqlalchemy_url
        kwargs: dict = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            # concurrent dashboard reads while a run writes
            with _engine.begin() as c:
                c.execute(text("PRAGMA journal_mode=WAL"))
    return _engine


def init_schema() -> None:
    """Create anything missing, then add columns introduced after a DB was first
    created (SQLAlchemy's create_all never ALTERs an existing table)."""
    eng = get_engine()
    metadata.create_all(eng)
    insp = inspect(eng)
    if "runs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("runs")}
        if "user_id" not in cols:
            with eng.begin() as c:
                c.execute(text("ALTER TABLE runs ADD COLUMN user_id VARCHAR"))
