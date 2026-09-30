"""Verdict cache for the grading call — the one stage that had none.

Every other expensive stage in this pipeline is already content-hashed: fetched bodies
(`fetch.py`), extracted text (`ocr.get_document_text`), provision embeddings and cross-encoder
scores (`retrieval.py`). Grading was not, so it cost the same 151.4s on every run of the same
economy while everything around it collapsed to near zero — 76% of a warm Singapore pillar-7
run, measured 2026-09-14.

A grading verdict is a pure function of four things, and the key is all four:

    model_version  the model that answered — NOT the provider. An engine swap MUST miss.
    SYSTEM         the grading prompt; editing it invalidates every stored verdict.
    user prompt    which already contains the indicator's legal_test, every sibling's
                   legal_test, and the provision's verbatim snippet.
    format version bumped by hand when the STORED SHAPE changes (see CACHE_VERSION).

Temperature is 0 on every provider in `backend/providers`, so the same four inputs are meant
to produce the same JSON. "Meant to" is doing real work in that sentence — a hosted model can
be re-versioned behind a stable id, and vLLM's own batching makes bit-identical logits across
runs not guaranteed. That is precisely why `model_version` is in the key and why this is a
CACHE and not a record: a wrong entry can only ever be a verdict that model really did give
for that exact prompt.

WHY THE ENGINE-SWAP CASE IS SAFE, which is the one that matters for 15 October. The panel asks
for "a comparable output from the second engine" over the same documents. Because
`model_version` is in the key, engine B misses every entry engine A wrote and re-grades all of
it; the comparison stays honest and the cache simply does nothing. Reusing A's verdicts for B
would be the failure, and it cannot happen.

AND WHY THIS IS NOT THE RESULT CACHE. `PROJECT_STATE.md` §4 records the day the whole-run
result cache returned six economies in six seconds and the numbers were reported as "after the
fix". The difference is scope and visibility: this stores ONE verdict for ONE (model, prompt)
pair, never a run, never a document set, and `mapping` logs the hit count on every run — so a
cache-served run says so out loud instead of looking like a fast one.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from ..config import settings

# Bump when the STORED VALUE's shape changes — not when the prompt changes (the prompt is
# already in the key). v1: the grader's parsed JSON object, stored as-is.
CACHE_VERSION = "v1"

_DIRNAME = "_verdicts"
_lock = threading.Lock()
_stats = {"hit": 0, "miss": 0, "write": 0}


def _dir() -> Path:
    d = settings.cache_path / _DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def key(model_version: str, system: str, user: str) -> str:
    """Hash of everything that can change the answer."""
    h = hashlib.sha256()
    for part in (CACHE_VERSION, model_version or "unknown", system, user):
        h.update(part.encode("utf-8", "ignore"))
        h.update(b"\x00")          # length-delimited: no ambiguity between concatenations
    return h.hexdigest()[:32]


# Providers whose verdicts are never stored. The mock grader is FREE, so caching it buys
# nothing, and it is the offline demo's source of determinism — that determinism has to come
# from its code, or editing the mock would leave stale verdicts outliving the change with
# nothing to show for it. (It also stops two tests that pin different canned answers for one
# model id from reading each other's entries.)
_NEVER_CACHE = {"mock"}


def cacheable(provider_name: str | None) -> bool:
    return (provider_name or "").lower() not in _NEVER_CACHE


def get(model_version: str, system: str, user: str,
        provider_name: str | None = None) -> dict[str, Any] | None:
    """The stored verdict, or None. Never raises — a broken cache must not fail a run."""
    if not settings.grading_cache_enabled or not cacheable(provider_name):
        return None
    try:
        p = _dir() / f"{key(model_version, system, user)}.json"
        if not p.exists():
            with _lock:
                _stats["miss"] += 1
            return None
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:              # noqa: BLE001 — unreadable/corrupt entry: re-grade
        with _lock:
            _stats["miss"] += 1
        return None
    if not isinstance(obj, dict) or obj.get("_parse_error"):
        # Never serve a failure from cache. An unparseable response is a FAILED CALL, which
        # `mapping` counts against the circuit breaker; storing one would make a transient
        # truncation permanent for that provision.
        with _lock:
            _stats["miss"] += 1
        return None
    with _lock:
        _stats["hit"] += 1
    return obj


def put(model_version: str, system: str, user: str, graded: dict[str, Any],
        provider_name: str | None = None) -> None:
    """Store a verdict. Best-effort: a failed write costs a re-grade, never the run."""
    if (not settings.grading_cache_enabled or not isinstance(graded, dict)
            or not cacheable(provider_name)):
        return
    if graded.get("_parse_error") or not graded:
        return                     # see get(): a failed call is not a verdict
    try:
        p = _dir() / f"{key(model_version, system, user)}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(graded, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)             # atomic: 32 grading threads write here concurrently
        with _lock:
            _stats["write"] += 1
    except Exception:              # noqa: BLE001
        pass


def reset_stats() -> None:
    with _lock:
        _stats.update(hit=0, miss=0, write=0)


def stats() -> dict[str, int]:
    with _lock:
        return dict(_stats)
