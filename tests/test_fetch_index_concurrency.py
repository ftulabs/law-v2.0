"""The fetch-cache index must survive several processes writing it at once.

Measured 2026-09-25: with economies running in parallel, the index was saved from a copy
loaded before each download, so entries written meanwhile were erased — India's API-seeded
sections vanished, fetch fell through to the web front end, and 1,106 sections became one
"India Code" JS shell. Eight writers x 50 entries kept 3 of 400 before the fix.
"""
from __future__ import annotations

import json
from multiprocessing import get_context


def _writer(cache_dir: str, k: int) -> None:
    from pathlib import Path

    from backend.config import settings
    from backend.pipeline import fetch

    type(settings).cache_path = property(lambda self: Path(cache_dir))
    for i in range(50):
        fetch.seed_cache(f"https://x.test/{k}/{i}", f"<html>{k}-{i}</html>".encode(),
                         "text/html", log=lambda _m: None)


def test_parallel_writers_lose_no_entries(tmp_path):
    from backend.pipeline.fetch import _INDEX_NAME

    ctx = get_context("spawn")
    procs = [ctx.Process(target=_writer, args=(str(tmp_path), k)) for k in range(8)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(600)   # spawn re-imports the backend; slow on a loaded machine
        assert p.exitcode == 0
    idx = json.loads((tmp_path / _INDEX_NAME).read_text(encoding="utf-8"))
    assert len(idx) == 400


def test_a_cache_hit_still_follows_the_landing_page_to_the_instrument(tmp_path, monkeypatch):
    """Measured 2026-09-25: Indonesia's second run inside the 24h TTL got every body from the
    cache, the cache-hit branch skipped the landing-page -> PDF step the network branch takes,
    and 3,283 provisions became 62."""
    from pathlib import Path

    from backend.config import settings
    from backend.pipeline import fetch

    monkeypatch.setattr(type(settings), "cache_path", property(lambda self: Path(tmp_path)))
    monkeypatch.setattr(fetch.robots, "allowed", lambda *_a, **_k: (True, ""))
    seen = []

    def _resolve(url, res, idx, log):
        seen.append(url)
        return res

    monkeypatch.setattr(fetch, "_maybe_resolve_portal_body", _resolve)
    url = "https://peraturan.bpk.go.id/Details/1/landing"
    fetch.seed_cache(url, b"<html>landing</html>", "text/html", log=lambda _m: None)
    res = fetch.fetch_to_cache(url, log=lambda _m: None)
    assert res is not None and res.from_cache
    assert seen == [url]
