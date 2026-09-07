# Phase 1 — Discovery Observability and Cache Lifecycle: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every pre-retrieval failure loud, so that a run which discovers nothing says why instead of looking like an economy with no relevant law.

**Architecture:** Web-search engines stop swallowing their own failures — a dead key raises a typed `EngineUnavailable` that `search()` records and logs, distinct from an engine that legitimately returned zero results. The search cache gains a timestamp and a TTL, so a week-old cache can no longer masquerade as live discovery. Discovery that yields zero documents emits `[error]` lines naming the cause chain, which the Run screen already knows how to render. A `cache_gc` tool gives the 1.3 GB cache a lifecycle.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup/lxml, pytest, Streamlit (read-only here), Windows/PowerShell primary with a Bash tool available.

**Spec:** `docs/superpowers/specs/2026-09-07-pre-retrieval-discovery-design.md`

## Global Constraints

- **Robots compliance is not negotiable.** Never route around an operator's refusal. `flk.npc.gov.cn` returns `"download": 0` and that decision stands. Never send a named-crawler User-Agent to `peraturan.bpk.go.id`.
- **The live pipeline must never import `backend.corpus`.** `tests/test_pipeline_isolation.py` pins this; `FORBIDDEN = ("backend.corpus", "corpus.store", "corpus.build", "corpus.catalogue", "corpus.cli")`. Nothing in this plan touches that boundary.
- **Never record a number without where it was measured.** A comment claiming a figure must name the file or command that produced it.
- **Non-Latin text must survive logging.** Use `backend.console.safe_log` / `enable_utf8_stdio`; a log line must never end a run (`tests/test_console_encoding.py`).
- **Do not change retrieval parameters.** `hybrid_alpha=0.65`, `retrieve_max_top_k`, `retrieve_per_law_k` are measured, not tuned. Out of scope.
- **Tests live flat in `tests/`**, named `test_<topic>.py`, matching the existing layout.

### Correction to the spec, found while planning

The spec's Phase-1 item 1.3 says to "wire `[error]` into `frontend/runview.py`, which today has no branch for it". **That is wrong** — [`frontend/runview.py:133`](../../../frontend/runview.py) already has an `elif tag == "error":` branch that splits the pair (what happened, what to do) into `st_["problem"]`, and `new_state()` carries that field. The stale claim is in `PROJECT_STATE.md` §3. So Task 3 only has to make discovery *emit* the lines in that pair shape; no UI work, and the `PROJECT_STATE.md` line gets deleted rather than actioned.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/pipeline/websearch.py` | Engine calls, the fallback chain, the disk cache | Modify — add `EngineUnavailable`, raise it from engines, record diagnostics, add cache TTL + provenance |
| `backend/config.py` | Settings | Modify — add `search_cache_max_age_days` |
| `backend/pipeline/discovery.py` | Lane dispatch | Modify — add `explain_empty_discovery()` |
| `backend/pipeline/orchestrator.py` | End-to-end run | Modify — call `explain_empty_discovery()` when discovery returns nothing |
| `tools/probe_portals.py` | Portal reconnaissance | Modify — one line, `enable_utf8_stdio()` |
| `tools/cache_gc.py` | Cache lifecycle | **Create** |
| `tests/test_websearch_diagnostics.py` | Tasks 1–2 | **Create** |
| `tests/test_empty_discovery.py` | Task 3 | **Create** |
| `tests/test_cache_gc.py` | Task 5 | **Create** |

---

## Task 1: A search engine that cannot answer says so

**Files:**
- Modify: `backend/pipeline/websearch.py` (`_serper` ~line 64, `_ddg_html`/`_ddg_lite`/`_mojeek` ~line 86, `search()` ~line 165)
- Test: `tests/test_websearch_diagnostics.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class EngineUnavailable(Exception)` with attributes `.engine: str`, `.detail: str`
  - `def diagnostics() -> dict` returning `{"cache_hits": int, "network_queries": int, "empty_queries": int, "engine_failures": dict[str, str]}`
  - `reset_circuit()` also resets the diagnostics counters.

**Why:** `_serper()` reads `if r.status_code != 200: return []`. Measured 2026-09-07, Serper answers `HTTP 400 {"message":"Not enough credits"}`, so a spent key is indistinguishable from an economy with no such law.

- [ ] **Step 1: Write the failing test**

Create `tests/test_websearch_diagnostics.py`:

```python
"""A search engine that cannot answer must say so.

Measured 2026-09-07: Serper answered `HTTP 400 {"message":"Not enough credits"}` and
`_serper()` returned an empty list, so the run reported "no laws found" for Singapore —
whose only discovery lane is web search. A dead key and an economy with no relevant law
produced byte-identical output. These tests pin the difference.
"""
import json

import pytest

from backend.pipeline import websearch


class _Resp:
    """The parts of an httpx.Response the engines actually read."""

    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Client:
    def __init__(self, resp):
        self._resp = resp

    def post(self, *a, **kw):
        return self._resp

    def get(self, *a, **kw):
        return self._resp


def test_serper_out_of_credits_raises_engine_unavailable(monkeypatch):
    monkeypatch.setattr(websearch.settings, "serper_api_key", "deadbeef")
    client = _Client(_Resp(400, {"message": "Not enough credits", "statusCode": 400}))
    with pytest.raises(websearch.EngineUnavailable) as exc:
        websearch._serper(client, "pdpa singapore", 10)
    assert exc.value.engine == "serper"
    assert "400" in exc.value.detail
    assert "Not enough credits" in exc.value.detail


def test_serper_with_no_key_is_not_a_failure(monkeypatch):
    """No key configured is a choice, not a broken engine — it must not be reported."""
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    assert websearch._serper(_Client(_Resp(200, {"organic": []})), "q", 10) == []


def test_duckduckgo_challenge_page_raises(monkeypatch):
    """DuckDuckGo answers 202 with an anomaly/challenge page, not 200. Measured 2026-09-07."""
    client = _Client(_Resp(202, text="<html>anomaly ... challenge</html>"))
    with pytest.raises(websearch.EngineUnavailable) as exc:
        websearch._ddg_html(client, "pdpa singapore", 10)
    assert exc.value.engine == "ddg_html"
    assert "202" in exc.value.detail


def test_search_records_the_failure_and_keeps_going(monkeypatch, tmp_path):
    """One dead engine must not be fatal, but it must be REPORTED."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_circuit()

    def dead(client, q, n):
        raise websearch.EngineUnavailable("ddg_html", "HTTP 202 (challenge page)")

    def alive(client, q, n):
        return [("https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", "snippet")]

    monkeypatch.setattr(websearch, "_engines", lambda: [dead, alive])
    lines = []
    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lines.append)

    assert len(out) == 1, "a live engine after a dead one must still answer"
    diag = websearch.diagnostics()
    assert diag["engine_failures"]["ddg_html"] == "HTTP 202 (challenge page)"
    assert any("ddg_html" in ln and "unavailable" in ln for ln in lines)


def test_zero_results_is_not_an_engine_failure(monkeypatch, tmp_path):
    """An engine that answers with nothing is a different fact from an engine that is down."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_circuit()
    monkeypatch.setattr(websearch, "_engines", lambda: [lambda c, q, n: []])

    assert websearch.search("nothing matches this", log=lambda *_: None) == []
    diag = websearch.diagnostics()
    assert diag["engine_failures"] == {}
    assert diag["empty_queries"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_websearch_diagnostics.py -v`
Expected: FAIL — `AttributeError: module 'backend.pipeline.websearch' has no attribute 'EngineUnavailable'`

- [ ] **Step 3: Write minimal implementation**

In `backend/pipeline/websearch.py`, add after the imports (below `from ..schemas import Economy`):

```python
class EngineUnavailable(Exception):
    """An engine could not answer at all — a spent key, a rate limit, a challenge page.

    Deliberately distinct from an engine that answered with zero results. Collapsing the
    two is what made a dead Serper key read as "Singapore has no data-protection law":
    measured 2026-09-07, `_serper` returned [] on HTTP 400 "Not enough credits" and nothing
    anywhere recorded that the engine had failed.
    """

    def __init__(self, engine: str, detail: str):
        self.engine, self.detail = engine, detail
        super().__init__(f"{engine}: {detail}")


#: Per-run discovery provenance. Reset by `reset_circuit()` at the top of every run, so a
#: dashboard process that serves many runs cannot attribute one run's failures to the next.
_diag: dict = {"cache_hits": 0, "network_queries": 0, "empty_queries": 0,
               "engine_failures": {}}


def diagnostics() -> dict:
    """A copy of this run's search provenance — what came from cache, what hit the network,
    and which engines were unavailable. Read by `discovery.explain_empty_discovery`."""
    return {**_diag, "engine_failures": dict(_diag["engine_failures"])}
```

Replace `_serper`'s status check. The existing body is:

```python
    if r.status_code != 200:
        return []
```

with:

```python
    if r.status_code != 200:
        try:
            detail = r.json().get("message") or r.text[:120]
        except Exception:                                    # noqa: BLE001 — not JSON
            detail = r.text[:120]
        raise EngineUnavailable("serper", f"HTTP {r.status_code} — {detail}")
```

Replace the three keyless engines:

```python
def _ddg_html(client, q, n):
    r = client.post("https://html.duckduckgo.com/html/", data={"q": q})
    if r.status_code != 200:
        # 202 is DuckDuckGo's anomaly/challenge page, not an empty result set.
        raise EngineUnavailable("ddg_html", f"HTTP {r.status_code}"
                                            f"{' (challenge page)' if r.status_code == 202 else ''}")
    return _parse(r.text, "a.result__a", n)


def _ddg_lite(client, q, n):
    r = client.post("https://lite.duckduckgo.com/lite/", data={"q": q})
    if r.status_code != 200:
        raise EngineUnavailable("ddg_lite", f"HTTP {r.status_code}"
                                            f"{' (challenge page)' if r.status_code == 202 else ''}")
    return _parse(r.text, "a.result-link", n)


def _mojeek(client, q, n):
    r = client.get("https://www.mojeek.com/search", params={"q": q})
    if r.status_code != 200:
        raise EngineUnavailable("mojeek", f"HTTP {r.status_code}")
    return _parse(r.text, "a.title, ul.results-standard li a", n)
```

In `reset_circuit()`, clear the diagnostics too:

```python
def reset_circuit() -> None:
    _circuit["empties"] = 0
    _diag.update(cache_hits=0, network_queries=0, empty_queries=0)
    _diag["engine_failures"] = {}
```

In `search()`, replace the engine loop:

```python
        for engine in _engines():
            try:
                results = engine(client, q, max_results)
            except EngineUnavailable as e:
                _diag["engine_failures"][e.engine] = e.detail
                log(f"[websearch] {e.engine} unavailable — {e.detail}")
                results = []
            except Exception as e:  # noqa: BLE001
                log(f"[websearch] {engine.__name__} error ({type(e).__name__})")
                results = []
            if results:
                break
```

and in the same function, count what happened — after the `with httpx.Client(...)` block, in the `if results:` / `else:` branches:

```python
    if results:
        _circuit["empties"] = 0
        cache[q] = results
        _cache_file().write_text(json.dumps(cache, indent=1), encoding="utf-8")
    else:
        _circuit["empties"] += 1
        _diag["empty_queries"] += 1
        msg = f"[websearch] all engines empty for '{q}'"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_websearch_diagnostics.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Run the existing suite for regressions**

Run: `python -m pytest tests/test_discovery.py tests/test_console_encoding.py -q`
Expected: PASS. The engines now raise where they returned `[]`; `search()` catches it, so no caller sees a new exception.

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/websearch.py tests/test_websearch_diagnostics.py
git commit -m "websearch: a spent key stopped looking like an economy with no law

Serper answers HTTP 400 'Not enough credits' and _serper() returned [],
so Singapore -- whose only discovery lane is web search -- reported no
laws found. A dead engine and an empty result set produced identical
output and nothing recorded which had happened.

Engines now raise EngineUnavailable, search() records it per run and
logs it, and diagnostics() exposes the provenance discovery needs to
explain itself. An engine answering with zero results is still an empty
result, counted separately.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The search cache stops passing week-old results off as live discovery

**Files:**
- Modify: `backend/config.py` (near `serper_api_key`, ~line 463)
- Modify: `backend/pipeline/websearch.py` (`_load_cache`, `search()`)
- Test: `tests/test_websearch_diagnostics.py` (append)

**Interfaces:**
- Consumes: `diagnostics()`, `_diag` from Task 1.
- Produces:
  - `settings.search_cache_max_age_days: float` (default `7.0`)
  - Cache entries as `{"results": [[url, title, snippet], …], "fetched_at": "<ISO-8601 UTC>", "engine": "<name>"}`
  - `def _entry_results(entry, now=None) -> list | None` — `None` means "expired or unusable, treat as a miss"

**Why:** `data/cache/_search.json` held 890 queries last written 2026-08-31 with no TTL, while document bodies expire after 24h (`fetch_ttl_hours`). Singapore's runs were replaying that file. The panel's live test is sealed; a warm cache is not a live run.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_websearch_diagnostics.py`:

```python
import datetime as _dt


def _iso(days_ago: float) -> str:
    return (_dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(days=days_ago)).isoformat()


def test_fresh_cache_entry_is_served_without_touching_the_network(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data site:sso.agc.gov.sg": {
            "results": [["https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", ""]],
            "fetched_at": _iso(1), "engine": "serper"}}), encoding="utf-8")

    def explode(client, q, n):
        raise AssertionError("a fresh cache hit must not reach the network")

    monkeypatch.setattr(websearch, "_engines", lambda: [explode])
    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lambda *_: None)
    assert out == [("https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", "")]
    assert websearch.diagnostics()["cache_hits"] == 1


def test_stale_cache_entry_is_a_miss(monkeypatch, tmp_path):
    """The entry that made Singapore look alive was eight days old."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data site:sso.agc.gov.sg": {
            "results": [["https://sso.agc.gov.sg/Act/PDPA2012", "PDPA", ""]],
            "fetched_at": _iso(8), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://fresh", "Fresh", "")]])

    out = websearch.search("personal data", site="sso.agc.gov.sg", log=lambda *_: None)
    assert out == [("https://fresh", "Fresh", "")], "stale entry must not be served"
    assert websearch.diagnostics()["network_queries"] == 1


def test_legacy_bare_list_entry_is_treated_as_expired(monkeypatch, tmp_path):
    """Every one of the 890 entries written before this change is a bare list with no
    timestamp. It cannot be shown to be fresh, so it must never be served as live."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "personal data": [["https://old", "Old", ""]]}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://fresh", "Fresh", "")]])

    assert websearch.search("personal data", log=lambda *_: None) == \
        [("https://fresh", "Fresh", "")]


def test_ttl_of_zero_disables_the_cache_entirely(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 0.0)
    websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "q": {"results": [["https://cached", "C", ""]],
              "fetched_at": _iso(0), "engine": "serper"}}), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, qq, n: [("https://fresh", "Fresh", "")]])

    assert websearch.search("q", log=lambda *_: None) == [("https://fresh", "Fresh", "")]


def test_a_written_entry_carries_its_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    websearch.reset_circuit()

    def named(client, q, n):
        return [("https://x", "X", "")]

    named.__name__ = "_serper"
    monkeypatch.setattr(websearch, "_engines", lambda: [named])
    websearch.search("q", log=lambda *_: None)

    entry = json.loads((tmp_path / "_search.json").read_text(encoding="utf-8"))["q"]
    assert entry["engine"] == "_serper"
    assert entry["fetched_at"].startswith(str(_dt.datetime.now(_dt.timezone.utc).year))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_websearch_diagnostics.py -v -k "cache or ttl or legacy or provenance"`
Expected: FAIL — the four new tests error with `ValueError: "Settings" object has no field "search_cache_max_age_days"`, because the setting does not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `backend/config.py`, immediately after `serper_api_key: str = ""`:

```python
    # Search results are cached to disk so one run's repeated queries do not re-hit a
    # rate-limited engine. They had NO expiry, while document bodies expire after
    # fetch_ttl_hours — so on 2026-09-07 `data/cache/_search.json` held 890 queries last
    # written 2026-08-31, and Singapore (whose only lane is web search) was replaying them
    # while every live engine was down. A week-old cache is not a live run, and the panel's
    # 15 October test is sealed. 0 disables the cache entirely.
    search_cache_max_age_days: float = 7.0
```

In `backend/pipeline/websearch.py`, add above `_load_cache`:

```python
def _entry_results(entry, now: float | None = None) -> list | None:
    """Usable results from a cache entry, or None meaning "treat as a miss".

    Entries written before 2026-09-07 are a bare list with no timestamp. They cannot be
    shown to be fresh, so they expire by construction rather than being trusted by default —
    that default is what let a week-old cache stand in for live discovery.
    """
    import datetime as _dt

    max_age = settings.search_cache_max_age_days
    if max_age <= 0 or not isinstance(entry, dict):
        return None
    stamp = entry.get("fetched_at")
    rows = entry.get("results")
    if not stamp or not isinstance(rows, list):
        return None
    try:
        age_days = ((now or _dt.datetime.now(_dt.timezone.utc).timestamp())
                    - _dt.datetime.fromisoformat(stamp).timestamp()) / 86400.0
    except (ValueError, TypeError):
        return None
    if age_days > max_age:
        return None
    return [(r[0], r[1], r[2] if len(r) > 2 else "") for r in rows]
```

Replace the cache-hit block in `search()`:

```python
    cache = _load_cache()
    hit = _entry_results(cache.get(q))
    if hit is not None:                             # fresh hit — no network, no rate-limit
        _diag["cache_hits"] += 1
        return hit
    if _circuit["empties"] >= _HARD and not settings.serper_api_key:
        return []                                   # circuit open — engines blocked, skip network
    _diag["network_queries"] += 1
```

Replace the cache write:

```python
    if results:
        _circuit["empties"] = 0
        import datetime as _dt
        cache[q] = {"results": [list(r) for r in results],
                    "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    "engine": getattr(engine, "__name__", "?")}
        _cache_file().write_text(json.dumps(cache, indent=1), encoding="utf-8")
```

Note: `engine` is the loop variable from the `for engine in _engines():` block, still bound to the engine that produced the results because the loop `break`s on success.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_websearch_diagnostics.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Confirm the real cache is now correctly treated as expired**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from backend.pipeline import websearch as w; from backend.config import settings; import json; d=json.loads((settings.cache_path/'_search.json').read_text(encoding='utf-8')); print('entries:', len(d)); print('still usable:', sum(w._entry_results(v) is not None for v in d.values()))"
```
Expected: `entries: 890`, `still usable: 0` — every existing entry is a legacy bare list.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/pipeline/websearch.py tests/test_websearch_diagnostics.py
git commit -m "websearch: the cache had no expiry, so a week-old file stood in for live discovery

data/cache/_search.json held 890 queries last written 2026-08-31 and no
TTL at all, while document bodies expire after 24h. Singapore's only
discovery lane is web search, so its runs were replaying that file --
which is why SG looked healthy on 2026-09-07 while every live engine was
down and Laos and Timor-Leste, with cold caches, returned zero.

Entries now carry fetched_at and the engine that produced them, and
expire after search_cache_max_age_days (7). The 890 pre-existing entries
are bare lists with no timestamp: they cannot be shown to be fresh, so
they expire by construction rather than being trusted by default.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Discovery that finds nothing says why

**Files:**
- Modify: `backend/pipeline/discovery.py` (add `explain_empty_discovery`, near `discover_live`)
- Modify: `backend/pipeline/orchestrator.py:356` (after the document-count log line)
- Test: `tests/test_empty_discovery.py`

**Interfaces:**
- Consumes: `websearch.diagnostics()` (Task 1), `discovery.load_sources()` (existing).
- Produces: `def explain_empty_discovery(economy: Economy, log=print) -> list[str]` — returns the `[error]` lines and also logs them. The final line always begins `[error] what to do:`, which is the pair shape `frontend/runview.py` parses.

**Why:** Zero documents is currently a successful run with an empty CSV. `frontend/runview.py:133` already renders `[error]` as (what happened, what to do); nothing in discovery emits it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_empty_discovery.py`:

```python
"""A run that discovers nothing must say why.

Zero documents is currently indistinguishable from an economy with no relevant law: the
run completes, exports an empty CSV and exits 0. On 2026-09-07 every search engine was
down and that is exactly what Thailand, Laos and Timor-Leste produced.

`frontend/runview.py` already renders `[error]` lines as a (what happened, what to do)
pair. These tests pin that discovery emits them in that shape.
"""
from backend.pipeline import discovery, websearch
from backend.schemas import Economy


def _reset():
    websearch.reset_circuit()


def test_a_dead_search_engine_is_named_as_the_cause(monkeypatch):
    _reset()
    websearch._diag["engine_failures"]["serper"] = "HTTP 400 — Not enough credits"
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)

    assert all(ln.startswith("[error] ") for ln in lines)
    assert any("serper" in ln and "Not enough credits" in ln for ln in lines)
    assert lines[-1].startswith("[error] what to do:")


def test_an_economy_with_no_portal_lane_says_so(monkeypatch):
    """Singapore's only lane is websearch, so a dead engine costs it the whole economy."""
    _reset()
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "SG", "name": "Singapore Statutes Online", "adapter": "websearch"}])
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)
    joined = " ".join(lines)
    assert "no portal-native lane" in joined
    assert "SG" in joined


def test_an_economy_with_a_portal_lane_does_not_blame_the_search_engine(monkeypatch):
    _reset()
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "MY", "name": "Laws of Malaysia (AGC)", "adapter": "my_catalogue"}])
    lines = discovery.explain_empty_discovery(Economy.MY, log=lambda *_: None)
    assert "no portal-native lane" not in " ".join(lines)
    assert any("my_catalogue" in ln or "Laws of Malaysia" in ln for ln in lines)


def test_the_provenance_counts_are_reported(monkeypatch):
    _reset()
    websearch._diag["cache_hits"] = 12
    websearch._diag["network_queries"] = 3
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"economy": "TH", "name": "x", "adapter": "websearch"}])
    joined = " ".join(discovery.explain_empty_discovery(Economy.TH, log=lambda *_: None))
    assert "12" in joined and "3" in joined


def test_the_lines_are_logged_not_just_returned():
    _reset()
    out = []
    discovery.explain_empty_discovery(Economy.LA, log=out.append)
    assert out and out == discovery.explain_empty_discovery(Economy.LA, log=lambda *_: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_empty_discovery.py -v`
Expected: FAIL — `AttributeError: module 'backend.pipeline.discovery' has no attribute 'explain_empty_discovery'`

- [ ] **Step 3: Write minimal implementation**

In `backend/pipeline/discovery.py`, add after `discover_live`:

```python
def explain_empty_discovery(economy: Economy, log=print) -> list[str]:
    """Say why discovery found nothing, as `[error]` pairs the Run screen can render.

    Zero documents used to be a successful run with an empty CSV — indistinguishable from
    an economy that genuinely has no such law. Measured 2026-09-07: every search engine was
    unavailable at once (Serper out of credits, DuckDuckGo serving challenge pages) and
    three economies reported "no provision found" with nothing in any log to say otherwise.

    The last line always begins "what to do:", because `frontend/runview.py` reads these as
    a (what happened, what to do) pair and an error with no recovery path is a dead end.
    """
    from . import websearch

    diag = websearch.diagnostics()
    srcs = [s for s in load_sources() if s.get("economy") == economy.value]
    portal_lanes = [s for s in srcs
                    if s.get("adapter") and s.get("adapter") != "websearch"]

    out = [f"[error] discovery found no documents for {economy.value}. This is a failure of "
           f"the search, not an economy without relevant law."]
    for eng, why in diag["engine_failures"].items():
        out.append(f"[error] search engine '{eng}' was unavailable: {why}")
    if portal_lanes:
        names = ", ".join(f"{s.get('name', '?')} ({s.get('adapter')})" for s in portal_lanes)
        out.append(f"[error] portal lanes tried and returned nothing: {names}")
    else:
        out.append(f"[error] {economy.value} has no portal-native lane — every document must "
                   f"arrive through web search, so a dead engine costs the whole economy.")
    out.append(f"[error] lanes configured: {len(srcs)} · queries sent to the network: "
               f"{diag['network_queries']} · answered from cache: {diag['cache_hits']} · "
               f"queries that came back empty: {diag['empty_queries']}")

    if diag["engine_failures"]:
        fix = ("restore a working search engine — set a funded SERPER_API_KEY in .env "
               "(check the current one with: curl -H \"X-API-KEY: $SERPER_API_KEY\" "
               "-X POST https://google.serper.dev/search -d '{\"q\":\"test\"}')")
    elif not portal_lanes:
        fix = (f"give {economy.value} a portal-native lane in data/sources.yaml — every "
               f"engine answered, none had anything for this portal")
    else:
        fix = ("check the portal lanes above against the live site with "
               f"`python tools/probe_portals.py --economy {economy.value}`")
    out.append(f"[error] what to do: {fix}")

    for line in out:
        log(line)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_empty_discovery.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Wire it into the run**

In `backend/pipeline/orchestrator.py`, the line at ~356 currently reads:

```python
    log(f"[discovery] {len(docs)} documents (NEW={sum(d.discovery_tag=='NEW' for d in docs)})")
```

Add immediately after it:

```python
    if not docs and not use_samples:
        # An empty live discovery is a failure with a knowable cause, not an economy
        # without law. Sample mode is excluded: an empty sample corpus is a packaging
        # problem with a different fix, and it never reaches a judge.
        discovery.explain_empty_discovery(economy, log=log)
```

- [ ] **Step 6: Verify the wiring end to end**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from backend.pipeline import discovery, websearch; from backend.schemas import Economy; websearch.reset_circuit(); websearch._diag['engine_failures']['serper']='HTTP 400 - Not enough credits'; [print(l) for l in discovery.explain_empty_discovery(Economy.TL, log=lambda *_: None)]"
```
Expected: five or six `[error]` lines, the last beginning `[error] what to do:`, and Timor-Leste reported as having no portal-native lane.

- [ ] **Step 7: Commit**

```bash
git add backend/pipeline/discovery.py backend/pipeline/orchestrator.py tests/test_empty_discovery.py
git commit -m "discovery: zero documents is a failure with a cause, not an empty economy

A live run that discovered nothing completed, exported an empty CSV and
exited 0. On 2026-09-07 every search engine was unavailable at once and
that is exactly what Thailand, Laos and Timor-Leste produced -- output
identical to an economy with no relevant law.

explain_empty_discovery names the cause chain: which engines were
unavailable and why, which portal lanes ran, how many queries reached
the network versus the cache, and what to do about it. It emits the
[error] pair shape runview.py has rendered since 2026-08-29 -- so this
needed no UI work, contrary to the open item in PROJECT_STATE.md.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `probe_portals.py` survives a non-Latin portal name on Windows

**Files:**
- Modify: `tools/probe_portals.py` (imports, and the top of `main()`)
- Test: covered by the existing `tests/test_console_encoding.py` contract; verified by running the tool

**Interfaces:**
- Consumes: `backend.console.enable_utf8_stdio` (exists — see `tests/test_console_encoding.py`).
- Produces: nothing new.

**Why:** The tool died with `UnicodeEncodeError: 'charmap' codec can't encode characters` while printing a portal name, on RU and ID — the two economies that most needed probing. This is the same defect `backend/console.py` was written to fix; the tool simply never called it.

- [ ] **Step 1: Reproduce the crash**

Run: `python tools/probe_portals.py --economy RU`
Expected: it prints the first portal, then `UnicodeEncodeError: 'charmap' codec can't encode characters in position 87-102`

- [ ] **Step 2: Apply the fix**

In `tools/probe_portals.py`, after the existing `sys.path.insert(...)` line and alongside the other `backend` imports, add:

```python
from backend.console import enable_utf8_stdio                  # noqa: E402
```

and as the first statement inside `main()`:

```python
    # Portal names are Russian, Chinese and Mongolian. Windows hands a process the console's
    # ANSI code page (cp1252 here), so printing one killed the tool on exactly the two
    # economies it existed to investigate. Same defect, same fix, as tests/test_console_encoding.py.
    enable_utf8_stdio()
```

- [ ] **Step 3: Verify the crash is gone**

Run: `python tools/probe_portals.py --economy RU`
Expected: both Russian lanes print with their Cyrillic names, a SUMMARY block follows, exit code 0.

- [ ] **Step 4: Verify the other economy it killed**

Run: `python tools/probe_portals.py --economy ID`
Expected: both Indonesian lanes print and a SUMMARY block follows (previously: no output at all).

- [ ] **Step 5: Commit**

```bash
git add tools/probe_portals.py
git commit -m "tools: probe_portals died on the two portals it existed to investigate

Printing a portal name raised UnicodeEncodeError under the Windows
console code page, so the tool produced a partial report for Russia and
no output whatsoever for Indonesia -- the two economies whose lanes were
least understood.

backend/console.enable_utf8_stdio already existed for exactly this, from
the Mongolia run that died the same way in the dashboard. The tool just
never called it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: The cache gets a lifecycle

**Files:**
- Create: `tools/cache_gc.py`
- Test: `tests/test_cache_gc.py`

**Interfaces:**
- Consumes: `settings.cache_path` (existing property).
- Produces:
  - `def plan_gc(root: Path, max_age_days: float, max_gb: float, keep_engines: bool) -> list[Reclaim]`
  - `@dataclass Reclaim: path: Path; bytes: int; reason: str`
  - `def main() -> int` — CLI, `--dry-run` is the default.

**Why:** `data/cache` is 1.3 GB and nothing ever prunes it: 843 PDFs, 2,155 HTML, 2,854 extraction results holding *both* `_rapidocr_v4` and `_rapidocr_v5` outputs for the same document, 210 MB of embedding caches, and 53 MB of LightRAG artefacts that `RETRIEVER=hybrid` never reads.

**Constraint that shapes this:** the panel requires re-processing already-downloaded documents without re-fetching, so `_extracted/` is a *mechanism*, not waste. Only superseded engine versions of the same document may go. Deleting is opt-in: `--dry-run` is the default and `--apply` is explicit.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cache_gc.py`:

```python
"""The cache had no lifecycle, so it grew to 1.3 GB and kept every engine version forever.

What must NOT be reclaimed matters more than what must: the panel requires the tool to
re-process already-downloaded documents without re-fetching, so extraction results are a
mechanism, not waste. Only SUPERSEDED versions of the same document may go.
"""
import json
import time
from pathlib import Path

from tools.cache_gc import Reclaim, plan_gc


def _write(p: Path, size: int, age_days: float = 0.0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        import os
        os.utime(p, (old, old))
    return p


def test_superseded_engine_output_is_reclaimed_and_the_newest_is_kept(tmp_path):
    ex = tmp_path / "_extracted"
    _write(ex / "abc123_rapidocr_v4.json", 100)
    _write(ex / "abc123_rapidocr_v5.json", 100)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0, keep_engines=False)
    paths = {r.path.name for r in plan}
    assert "abc123_rapidocr_v4.json" in paths
    assert "abc123_rapidocr_v5.json" not in paths, "the newest engine output must survive"


def test_a_document_with_only_one_engine_version_is_never_reclaimed(tmp_path):
    ex = tmp_path / "_extracted"
    _write(ex / "solo_rapidocr_v5.json", 100)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0, keep_engines=False)
    assert not [r for r in plan if r.path.name == "solo_rapidocr_v5.json"]


def test_lightrag_is_reclaimed_only_when_the_retriever_does_not_use_it(tmp_path, monkeypatch):
    _write(tmp_path / "lightrag" / "graph.graphml", 5000)
    from tools import cache_gc
    monkeypatch.setattr(cache_gc.settings, "retriever", "hybrid")
    assert any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))
    monkeypatch.setattr(cache_gc.settings, "retriever", "lightrag")
    assert not any("lightrag" in str(r.path) for r in plan_gc(tmp_path, 0, 0, False))


def test_old_document_bodies_are_reclaimed_by_age(tmp_path):
    _write(tmp_path / "old.pdf", 1000, age_days=90)
    _write(tmp_path / "new.pdf", 1000, age_days=1)
    names = {r.path.name for r in plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False)}
    assert "old.pdf" in names and "new.pdf" not in names


def test_embedding_caches_are_never_reclaimed_by_age(tmp_path):
    """Measured at 16x on repeat runs (CLAUDE.md, retrieval perf findings) and rebuilt only
    at real CPU cost. Age is the wrong axis for these."""
    _write(tmp_path / "_emb_model_2048.npz", 1000, age_days=365)
    _write(tmp_path / "_ce_baai-bge-reranker-v2-m3.npz", 1000, age_days=365)
    assert plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False) == []


def test_the_search_cache_is_never_reclaimed_by_this_tool(tmp_path):
    """It expires per entry (search_cache_max_age_days), which preserves the provenance
    a stale-vs-fresh decision needs. Deleting the file wholesale would hide that."""
    _write(tmp_path / "_search.json", 1000, age_days=365)
    assert plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False) == []


def test_size_cap_reclaims_oldest_first(tmp_path):
    _write(tmp_path / "a.pdf", 3_000_000, age_days=10)
    _write(tmp_path / "b.pdf", 3_000_000, age_days=5)
    _write(tmp_path / "c.pdf", 3_000_000, age_days=1)
    plan = plan_gc(tmp_path, max_age_days=0, max_gb=0.006, keep_engines=False)
    assert [r.path.name for r in plan] == ["a.pdf"]


def test_every_reclaim_states_a_reason(tmp_path):
    _write(tmp_path / "old.pdf", 1000, age_days=90)
    plan = plan_gc(tmp_path, max_age_days=30, max_gb=0, keep_engines=False)
    assert plan and all(isinstance(r, Reclaim) and r.reason for r in plan)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cache_gc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.cache_gc'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/cache_gc.py`:

```python
"""Give data/cache a lifecycle. It had none, and grew to 1.3 GB.

Measured 2026-09-07: 843 PDFs, 2,155 HTML pages, 2,854 extraction results — holding BOTH
`_rapidocr_v4` and `_rapidocr_v5` output for the same documents — 210 MB of embedding
caches and 53 MB of LightRAG artefacts that `RETRIEVER=hybrid` never reads.

What this tool must NOT reclaim is the more important half:

  _extracted/   the panel requires re-processing already-downloaded documents without
                re-fetching ("the live test may require it"). This IS that mechanism. Only
                SUPERSEDED engine versions of a document go; the newest always stays, and a
                document with a single version is never touched.
  _emb_*.npz    measured at a 16x speedup on repeat runs and rebuilt only at real CPU cost.
  _ce_*.npz     same.
  _search.json  expires per ENTRY (settings.search_cache_max_age_days), which keeps the
                provenance a stale-vs-fresh decision needs. Deleting the file hides that.

    python tools/cache_gc.py                       # what would go, and why (default)
    python tools/cache_gc.py --apply               # actually delete
    python tools/cache_gc.py --max-age-days 30 --max-gb 2 --apply
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                            # noqa: E402
from backend.console import enable_utf8_stdio                  # noqa: E402

#: Never reclaimed by age or size — see the module docstring for why each one earns it.
_PROTECTED = ("_search.json", "_index.json")
_PROTECTED_PREFIX = ("_emb_", "_ce_")

#: `<doc-hash>_<engine>_<version>.json` in _extracted/. The version is what makes one
#: output supersede another for the same document.
_EXTRACTED = re.compile(r"^(?P<doc>[0-9a-f]+)_(?P<engine>[a-z0-9]+)_v(?P<ver>\d+)\.json$")


@dataclass
class Reclaim:
    path: Path
    bytes: int
    reason: str


def _protected(p: Path) -> bool:
    return p.name in _PROTECTED or p.name.startswith(_PROTECTED_PREFIX)


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def plan_gc(root: Path, max_age_days: float, max_gb: float,
            keep_engines: bool) -> list[Reclaim]:
    """What would be reclaimed, and why. Pure — it never deletes."""
    out: list[Reclaim] = []
    now = time.time()
    if not root.exists():
        return out

    # 1. LightRAG artefacts, when the configured retriever cannot read them.
    lr = root / "lightrag"
    if lr.is_dir() and (settings.retriever or "hybrid").lower() != "lightrag":
        size = _dir_size(lr)
        if size:
            out.append(Reclaim(lr, size,
                               f"RETRIEVER={settings.retriever} never reads LightRAG artefacts"))

    # 2. Superseded engine outputs in _extracted/ — newest version per (document, engine) stays.
    ex = root / "_extracted"
    if ex.is_dir() and not keep_engines:
        newest: dict[tuple[str, str], int] = {}
        rows: list[tuple[Path, str, str, int]] = []
        for f in ex.glob("*.json"):
            m = _EXTRACTED.match(f.name)
            if not m:
                continue
            key = (m["doc"], m["engine"])
            ver = int(m["ver"])
            rows.append((f, m["doc"], m["engine"], ver))
            newest[key] = max(newest.get(key, -1), ver)
        for f, doc, engine, ver in rows:
            if ver < newest[(doc, engine)]:
                out.append(Reclaim(f, f.stat().st_size,
                                   f"{engine} v{ver} superseded by "
                                   f"v{newest[(doc, engine)]} for the same document"))

    reclaimed = {r.path for r in out}
    bodies = [f for f in root.iterdir()
              if f.is_file() and not _protected(f) and f not in reclaimed]

    # 3. Document bodies past the age cap. They are content-hashed and re-fetchable.
    if max_age_days > 0:
        for f in bodies:
            age = (now - f.stat().st_mtime) / 86400.0
            if age > max_age_days:
                out.append(Reclaim(f, f.stat().st_size,
                                   f"cached body {age:.0f} days old (cap {max_age_days:g})"))

    # 4. Size cap, oldest first, on whatever the age pass left behind.
    if max_gb > 0:
        left = sorted((f for f in bodies if f not in {r.path for r in out}),
                      key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in left)
        budget = int(max_gb * 1024 ** 3)
        for f in left:
            if total <= budget:
                break
            size = f.stat().st_size
            out.append(Reclaim(f, size, f"over the {max_gb:g} GB cap, oldest first"))
            total -= size
    return out


def main() -> int:
    enable_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="cache directory (default: settings.cache_path)")
    ap.add_argument("--max-age-days", type=float, default=30.0)
    ap.add_argument("--max-gb", type=float, default=0.0, help="0 = no size cap")
    ap.add_argument("--keep-engines", action="store_true",
                    help="keep superseded engine outputs in _extracted/")
    ap.add_argument("--apply", action="store_true", help="delete (default is a dry run)")
    a = ap.parse_args()

    root = Path(a.root) if a.root else settings.cache_path
    plan = plan_gc(root, a.max_age_days, a.max_gb, a.keep_engines)
    if not plan:
        print(f"nothing to reclaim in {root}")
        return 0

    by_reason: dict[str, tuple[int, int]] = {}
    for r in plan:
        kind = r.reason.split(" for the same document")[0].split(" (")[0]
        n, b = by_reason.get(kind, (0, 0))
        by_reason[kind] = (n + 1, b + r.bytes)
    total = sum(r.bytes for r in plan)
    for kind, (n, b) in sorted(by_reason.items(), key=lambda x: -x[1][1]):
        print(f"  {b / 1024**2:9.1f} MB  {n:5d} file(s)  {kind}")
    print(f"  {'-' * 9}")
    print(f"  {total / 1024**2:9.1f} MB  {len(plan):5d} file(s)  TOTAL")

    if not a.apply:
        print("\ndry run — nothing deleted. Re-run with --apply to reclaim.")
        return 0
    for r in plan:
        shutil.rmtree(r.path, ignore_errors=True) if r.path.is_dir() else r.path.unlink(missing_ok=True)
    print(f"\nreclaimed {total / 1024**2:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cache_gc.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Dry-run against the real cache**

Run: `python tools/cache_gc.py --max-age-days 30`
Expected: a table naming what would go and why, ending in `dry run — nothing deleted`. The LightRAG line (~53 MB) and superseded `_rapidocr_v4` outputs should appear; no `_emb_*`, `_ce_*` or `_search.json` may appear.

- [ ] **Step 6: Commit**

```bash
git add tools/cache_gc.py tests/test_cache_gc.py
git commit -m "tools: the cache had no lifecycle, so it grew to 1.3 GB

843 PDFs, 2,155 HTML pages, 2,854 extraction results holding BOTH
rapidocr v4 and v5 for the same documents, 210 MB of embedding caches
and 53 MB of LightRAG artefacts that RETRIEVER=hybrid never reads.

What the tool refuses to touch is the point. The panel requires
re-processing already-downloaded documents without re-fetching, so
_extracted/ is that mechanism, not waste: only superseded engine
versions go, the newest always stays, and a document with one version is
never touched. Embedding and cross-encoder caches are measured at 16x on
repeat runs and are exempt from age. _search.json expires per entry, so
deleting the file wholesale would hide the provenance.

Dry run is the default.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Retire the stale claims this phase disproved

**Files:**
- Modify: `PROJECT_STATE.md` (§3, the `[error]` item and the MY robots item)
- Modify: `data/sources.yaml` (the TH and LA entries)

**Interfaces:** none — documentation only.

**Why:** `PROJECT_STATE.md` rule 4 says *"Whenever an entry in §4 stops being true, delete it rather than annotating it — a stale warning is worse than none."* Three entries stopped being true, and two of them cost this session real time to disprove.

- [ ] **Step 1: Delete the `[error]` item from `PROJECT_STATE.md` §3**

Remove this bullet under "Cost and reliability":

```markdown
- [ ] Surface `[error]` lines on the Run screen. `frontend/runview.py` has no branch for that
      tag, so the breaker's plain-English cause reaches only the raw log — which is why a
      zero-row run still *looks* like an empty economy. UI work → invoke `ui-ux-pro-max` first.
```

It has a branch, at `frontend/runview.py:133`, and `new_state()` carries `problem`.

- [ ] **Step 2: Delete the MY robots item from `PROJECT_STATE.md` §3**

Remove:

```markdown
- [ ] MY robots carve-out — `lom.agc.gov.my/robots.txt` returns HTTP 500 and the fetcher reads
      "unreadable" as "disallowed", so every statute PDF on the primary portal is skipped.
      India already has the RFC 9309 §2.3.1.4 carve-out; MY needs the same.
```

The carve-out is present in `backend/pipeline/robots.py` `UNREACHABLE_OVERRIDE` under
`"lom.agc.gov.my"`, and §2 of the same file already records the result (489 → 5,931 provisions).

- [ ] **Step 3: Verify both claims before deleting them**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from backend.pipeline.robots import UNREACHABLE_OVERRIDE as U; print('lom.agc.gov.my' in U)"
grep -n 'elif tag == \"error\"' frontend/runview.py
```
Expected: `True`, and a line number around 133.

- [ ] **Step 4: Correct the TH entry in `data/sources.yaml`**

Replace the `krisdika.go.th` entry's `reachable:` and `note:` with:

```yaml
    reachable: "2026-09-07: TLS connects, but /, /th/ and /web/guest/law all return HTTP 404 with a 2,150-byte body — the site was restructured and this is no longer the TLS problem recorded on 2026-08-21. Superseded by the law.go.th lane."
    note: >-
      SUPERSEDED, kept because the error was expensive. This entry said "Thai statutes are
      published as PDF, frequently scanned … this is the OCR-heavy lane." That is FALSE, and
      it is why Thailand was ranked among the hardest economies for a fortnight. Thailand's
      central legal system (law.go.th) returns clean full text as JSON — no PDF, no OCR, no
      scan. See the TH API entry below and §2.1 of
      docs/superpowers/specs/2026-09-07-pre-retrieval-discovery-design.md.
```

- [ ] **Step 5: Correct the LA entry in `data/sources.yaml`**

Replace the Lao gazette entry's `reachable:` line with:

```yaml
    reachable: "2026-09-07: HTTP 200, 110 KB, 12,477 Lao characters, fully paginated. The 2026-08-21 reading 'URLError — host does not resolve' was wrong or transient; the host is a Yii app with ?r=site/index&Document_page=N listing, ?r=site/display&id=N detail, PDFs under /kcfinder/upload/files/, and an English toggle at ?r=site/switchpage&lc=en"
```

and delete the sentence *"Weakest coverage of the nine on every axis"* from its `note:`, keeping the rest (the OCR and legacy-font hazards are still true).

- [ ] **Step 6: Commit**

```bash
git add PROJECT_STATE.md data/sources.yaml
git commit -m "docs: retire three claims this phase disproved

PROJECT_STATE's own rule 4 says a stale warning is worse than none, and
two of these cost a session real time to disprove.

  - '[error] has no branch in runview.py' -- it has had one since
    2026-08-29, at runview.py:133, and new_state() carries `problem`.
  - 'MY needs the robots carve-out' -- lom.agc.gov.my has been in
    robots.UNREACHABLE_OVERRIDE for a week, and section 2 of the same
    file already records the 489 -> 5,931 provision result.
  - sources.yaml called Thailand the OCR-heavy scanned-PDF lane and
    Laos the weakest economy on every axis. Both are false: law.go.th
    serves clean full text as JSON, and the Lao gazette answers 200
    with full pagination.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Prove the phase holds together

**Files:** none modified — this is the phase gate.

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Note the baseline before starting the phase; no test that passed before may fail now.

- [ ] **Step 2: Confirm the corpus firewall is intact**

Run: `python -m pytest tests/test_pipeline_isolation.py tests/test_labels_and_budget.py -q`
Expected: PASS — nothing in this phase imports `backend.corpus`.

- [ ] **Step 3: Prove a dead engine and a cold cache now fail loudly**

Run:
```bash
python -c "
import sys, tempfile; sys.path.insert(0,'.')
from backend.config import settings
settings.cache_dir = tempfile.mkdtemp()      # cold cache
settings.serper_api_key = ''                 # no keyed engine
from backend.pipeline import websearch, discovery
from backend.schemas import Economy
websearch.reset_circuit()
websearch._diag['engine_failures']['ddg_html'] = 'HTTP 202 (challenge page)'
for line in discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None): print(line)
"
```
Expected: `[error]` lines naming the unavailable engine, stating that Singapore has no
portal-native lane, and ending with an actionable `what to do:`.

- [ ] **Step 4: Record the phase in `PROJECT_STATE.md` §5**

Add under "Recently done", one line, with where each number was measured:

```markdown
- [x] **Phase 1 — pre-retrieval failures made loud** (2026-09-07). Serper answered HTTP 400
      "Not enough credits" and `_serper()` returned `[]`, so a spent key read as an economy
      with no law; `data/cache/_search.json` held 890 entries last written 2026-08-31 with no
      TTL, and Singapore (websearch-only) was replaying them. Engines now raise
      `EngineUnavailable`, cache entries carry `fetched_at` + engine and expire after
      `search_cache_max_age_days=7`, and `discovery.explain_empty_discovery` emits the
      `[error]` pair. `tools/cache_gc.py` gives the 1.3 GB cache a lifecycle.
      `tests/test_websearch_diagnostics.py`, `test_empty_discovery.py`, `test_cache_gc.py`.
```

- [ ] **Step 5: Commit**

```bash
git add PROJECT_STATE.md
git commit -m "docs: record Phase 1 in the project state

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## What Phase 1 deliberately does not do

- **It does not restore web search.** The Serper key stays spent. That is the point: after
  this phase a run *says* the engine is down instead of reporting an empty economy, and
  Phase 2 removes the dependency for ten of the eleven economies.
- **It does not write any adapter.** Phase 2 does, in its own plan, and it must be planned
  *after* this one lands — because until a run can distinguish "the portal gave nothing"
  from "the cache was warm", no adapter measurement means anything.
- **It does not delete anything from the cache.** `--dry-run` is the default; reclaiming is
  a decision the user makes with the numbers in front of them.
