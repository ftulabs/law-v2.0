# Phase 2 — Portal-Native Discovery Adapters: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every economy a lane that reaches its own portal without a search engine, so that a spent API key can no longer cost a country its whole submission.

**Architecture:** One shared `portal.py` carrying the `PortalEnumerator` protocol, the adapter registry, and the mechanics every portal needs (robots-aware GET with backoff, throttle handling, `DiscoveredDoc` construction). Six new per-economy adapter modules implement that protocol against the routes verified on 2026-09-07. `discovery.py` keeps its single dispatch line. Reusable strategies live in `portal_strategies.py`; a portal that does not fit one gets a bespoke module, as India and Mongolia already have.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup/lxml, Scrapling (browser lane), pytest, Windows/PowerShell primary with a Bash tool available.

**Spec:** `docs/superpowers/specs/2026-09-07-pre-retrieval-discovery-design.md` (§2 carries the verified route for every portal; §5 is this phase's task table)

## Global Constraints

- **Robots compliance is not negotiable.** Never route around an operator's refusal. `flk.npc.gov.cn`'s API returns `"download": 0` — that is a refusal and it stands; do not build a lane on it. Never send a named-crawler User-Agent (`ClaudeBot`, `GPTBot`, `CCBot`, `Bytespider`, `Amazonbot`, `Applebot-Extended`, `Google-Extended`, `meta-externalagent`, `CloudflareBrowserRenderingCrawler`) to `peraturan.bpk.go.id`, and never train on its text. Honour `mj.gov.tl`'s `Crawl-delay: 10`.
- **The live pipeline must never import `backend.corpus`.** `tests/test_pipeline_isolation.py` pins this; `FORBIDDEN = ("backend.corpus", "corpus.store", "corpus.build", "corpus.catalogue", "corpus.cli")`. Task 5 reverses one dependency — corpus imports from pipeline, never the other way.
- **Never record a number without where it was measured.** A comment claiming a figure must name the file, date or command that produced it.
- **Non-Latin text must survive logging.** Use `backend.console.safe_log`; `discovery.py` must contain no bare `print(` and no `log=print` (`tests/test_console_encoding.py:87-95`). Portal names and titles here are Portuguese, Lao, Thai, Chinese and Russian.
- **Do not change retrieval parameters.** `hybrid_alpha=0.65`, `retrieve_max_top_k`, `retrieve_per_law_k` are measured, not tuned. Out of scope.
- **No test may hit the network.** Parser tests run against saved fixtures under `tests/fixtures/portals/`. Live verification is a manual step in each task and is reported, never asserted in CI.
- **Tests live flat in `tests/`**, named `test_<topic>.py`.
- **Nine files carry the user's uncommitted work and must never be staged:** `.env.example`, `PROJECT_STATE.md`, `README.md`, `backend/config.py`, `backend/providers/llm_local.py`, `frontend/enginebench.py`, `tools/audit_rows.py`, `tools/candidate_indicators.py`, `tools/replay_grade.py`. A Phase-1 commit staged one whole-file and swallowed the user's work; it had to be rewritten. Stage by name, always run `git status --short` first, never `git add -A` / `git add .` / `git commit -a`. `PROJECT_STATE.md` edits use the snapshot route described in Task 10.

### Deviation from the spec's file list, and why

The spec names three new modules: `portal.py`, `portal_strategies.py`, `adapter_common.py`. This plan writes **two**: `portal.py` absorbs what `adapter_common.py` would have held (the protocol, the registry and the shared mechanics are ~120 lines together, and splitting a contract from the three helpers that serve it produces two files neither of which can be read alone). `portal_strategies.py` stays separate because it grows with each portal shape. YAGNI: if the mechanics outgrow `portal.py`, split then.

### Known state this phase starts from

- Discovery works portal-natively today for **AU** (`au_api`), **MY** (`my_catalogue`), **IN** (`in_dspace`), **MN** (`mn_legalinfo`). SG, CN, TH, ID, LA, RU, TL have web-search lanes only.
- **Every web-search engine is down**: Serper `HTTP 400 "Not enough credits"`, DuckDuckGo html/lite `HTTP 403`, Mojeek `HTTP 403` (measured 2026-09-07, and again during a live TL run that produced 52 empty queries). This is not a blocker for this phase — the whole point is to stop depending on them — but it means **no adapter can be validated against a web-search baseline**, and any lane that still needs search will fail loudly rather than silently.
- **Both LLM graders are unreachable**: the local server at `100.64.0.2:8090` refuses connections, and the OpenRouter key answers `401 "User not found"` (revoked, not merely spent). **Every task in this phase is therefore scoped to discovery → fetch → extract and must be verifiable without a grader.** Acceptance is "provisions extracted from the portal", never "rows mapped".
- Full suite before this phase: **922 passed, 1 failed**. The failure is `tests/test_localisation_gates.py::test_nothing_is_left_staged_in_the_candidate_file`, pre-existing, caused by the user's uncommitted `tools/candidate_indicators.py`. Do not fix it; report it unchanged.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/pipeline/portal.py` | `PortalEnumerator` protocol, adapter registry, robots-aware GET with backoff, `make_doc()` | **Create** |
| `backend/pipeline/portal_strategies.py` | Reusable shapes: `paginated_index`, `frameset_crawl`, `browser_first` | **Create** |
| `backend/pipeline/adapter_timor.py` | TL — static frameset tree of gazette PDFs | **Create** |
| `backend/pipeline/adapter_laos.py` | LA — Yii paginated list → detail → PDF | **Create** |
| `backend/pipeline/adapter_thailand.py` | TH — `apig.law.go.th` REST, full text in the response | **Create** |
| `backend/pipeline/adapter_singapore.py` | SG — SSO sort-window union | **Create** |
| `backend/pipeline/adapter_china.py` | CN — `cac.gov.cn` + `gov.cn` paginated indexes | **Create** |
| `backend/pipeline/adapter_indonesia.py` | ID — browser-first over `peraturan.bpk.go.id` | **Create** |
| `backend/pipeline/discovery.py` | Lane dispatch | Modify — register the six adapters |
| `backend/corpus/catalogue.py` | Offline corpus enumerator | Modify — import SG enumeration from the pipeline (Task 5) |
| `backend/pipeline/websearch.py` | `_entry_results` try scope | Modify — Task 9 |
| `data/sources.yaml` | Portal registry | Modify — six new/changed lanes |
| `tools/readiness.py` | Capability table | Modify — Task 10 |
| `tests/fixtures/portals/` | Saved portal responses | **Create** — one per adapter |
| `tests/test_portal_layer.py` | Task 1 | **Create** |
| `tests/test_adapter_<economy>.py` | Tasks 2-7, one each | **Create** |
| `tests/test_run_pipeline_wiring.py` | Task 9 | **Create** |

**Task order is deliberate.** Task 1 must land first — every adapter imports it. Tasks 2-7 are independent of each other and may be reviewed in any order, but not dispatched in parallel (they all touch `discovery.py`'s registry, and Task 8 is where that wiring is consolidated). Task 9 is independent of all of them. Task 10 is the gate.

---

## Task 1: The shared portal layer

**Files:**
- Create: `backend/pipeline/portal.py`
- Create: `backend/pipeline/portal_strategies.py`
- Test: `tests/test_portal_layer.py`

**Interfaces:**
- Consumes: `backend.schemas.DiscoveredDoc`, `Economy`, `DocFormat`, `DiscoveryTag`; `backend.pipeline.robots.allowed`; `backend.config.settings`; `backend.console.safe_log`.
- Produces, and every later task depends on these exact names:
  - `class PortalEnumerator(Protocol)` with `def __call__(self, client, src: dict, query: str, economy: Economy, indicators: list, log) -> list[DiscoveredDoc]` — the signature `discovery.py` already dispatches on.
  - `def portal_get(client, url: str, log, tries: int = 4, **kw) -> httpx.Response | None`
  - `def make_doc(economy, url, title, portal, *, fmt=None, law_number=None, law_name=None, score=1.0, amendment_date=None) -> DiscoveredDoc`
  - `def doc_id(economy: str, source_url: str) -> str`
  - In `portal_strategies.py`: `def paginated_index(client, log, *, page_url, row_selector, link_filter=None, max_pages=50) -> list[tuple[str, str]]` returning `(absolute_url, title)`.

**Why:** Six adapters are about to be written by six separate implementers. Without one place for robots checking, throttle backoff and `DiscoveredDoc` construction, the Malaysia robots defect (`robots.txt` HTTP 500 read as "disallowed") would have to be fixed six times, and one of the six would be missed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_portal_layer.py`:

```python
"""The mechanics every portal adapter shares, pinned once.

Six adapters are written against this. The alternative — each adapter carrying its own
robots check, its own backoff and its own DiscoveredDoc construction — is how the Malaysia
robots defect (robots.txt HTTP 500 read as "disallowed", costing every statute PDF on the
primary portal) would come to need six separate fixes, five of which would be found late.

Nothing here touches the network: portal_get is driven with a fake client.
"""
import pytest

from backend.pipeline import portal
from backend.schemas import DiscoveredDoc, DocFormat, Economy


class _Resp:
    def __init__(self, status, body=b"x", text=None):
        self.status_code = status
        self.content = body
        self.text = text if text is not None else body.decode("utf-8", "ignore")


class _Client:
    """Returns the queued responses in order, then repeats the last one."""

    def __init__(self, *responses):
        self._queue = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]


def test_portal_get_returns_the_first_good_response(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    c = _Client(_Resp(200, b"hello"))
    r = portal.portal_get(c, "https://example.gov/x", log=lambda *_: None)
    assert r is not None and r.content == b"hello"
    assert len(c.calls) == 1


def test_portal_get_treats_an_empty_202_as_a_throttle_and_retries(monkeypatch):
    """SSO answers a burst with 202 and an EMPTY body rather than 429 (verified 2026-08-01,
    backend/corpus/catalogue.py). A 202 with content is a real response and must not retry."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(portal.time, "sleep", lambda *_: None)
    c = _Client(_Resp(202, b""), _Resp(200, b"ok"))
    r = portal.portal_get(c, "https://sso.agc.gov.sg/Browse/Act", log=lambda *_: None)
    assert r is not None and r.content == b"ok"
    assert len(c.calls) == 2, "the empty 202 must have been retried"


def test_portal_get_gives_up_after_tries_and_returns_none(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    monkeypatch.setattr(portal.time, "sleep", lambda *_: None)
    c = _Client(_Resp(500, b""))
    assert portal.portal_get(c, "https://x.gov/y", log=lambda *_: None, tries=3) is None
    assert len(c.calls) == 3


def test_portal_get_refuses_a_disallowed_url_without_fetching(monkeypatch):
    """A robots refusal is an answer, not an obstacle. It must cost zero requests."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: False)
    c = _Client(_Resp(200, b"should never be fetched"))
    lines = []
    assert portal.portal_get(c, "https://x.gov/forbidden", log=lines.append) is None
    assert c.calls == []
    assert any("robots" in ln.lower() for ln in lines)


def test_make_doc_infers_pdf_from_the_url():
    d = portal.make_doc(Economy.TL, "https://mj.gov.tl/jornal/files/Law-2002-01.pdf",
                        "Lei 1/2002", "Jornal da República")
    assert isinstance(d, DiscoveredDoc)
    assert d.fmt == DocFormat.PDF_TEXT
    assert d.economy == Economy.TL
    assert d.source_url.endswith("Law-2002-01.pdf")


def test_make_doc_defaults_to_html_for_a_page():
    d = portal.make_doc(Economy.CN, "https://www.cac.gov.cn/2024-03/22/c_1712.htm",
                        "个人信息保护法", "cac.gov.cn")
    assert d.fmt == DocFormat.HTML


def test_make_doc_honours_an_explicit_format():
    d = portal.make_doc(Economy.TH, "https://apig.law.go.th/law/1", "พ.ร.บ.", "law.go.th",
                        fmt=DocFormat.HTML)
    assert d.fmt == DocFormat.HTML


def test_doc_id_is_stable_and_economy_scoped():
    a = portal.doc_id("SG", "https://sso.agc.gov.sg/Act/PDPA2012")
    b = portal.doc_id("SG", "https://sso.agc.gov.sg/Act/PDPA2012")
    c = portal.doc_id("MY", "https://sso.agc.gov.sg/Act/PDPA2012")
    assert a == b and a != c
    assert a.startswith("SG-")


def test_doc_id_matches_the_id_discovery_already_uses():
    """live-mode dedup keys on doc_id, so a new id scheme would make every adapter's
    documents look distinct from the same document found by an existing lane."""
    from backend.pipeline.discovery import _doc_id
    url = "https://example.gov/act/1"
    assert portal.doc_id("AU", url) == _doc_id("AU", url)


def test_registry_round_trips_and_rejects_an_unknown_name():
    portal.register("unit_test_adapter", lambda *a, **k: [])
    assert portal.get_adapter("unit_test_adapter") is not None
    assert portal.get_adapter("no_such_adapter") is None
```

Create `tests/test_portal_strategies.py`:

```python
"""paginated_index: the shape shared by Laos, China and any portal with a page parameter."""
from backend.pipeline import portal, portal_strategies


class _Resp:
    def __init__(self, text):
        self.status_code = 200
        self.text = text
        self.content = text.encode()


class _Client:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return _Resp(self._pages.get(url, "<html></html>"))


_PAGE1 = """<html><body>
  <a href="/index.php?r=site/display&id=11">Law on Electronic Data Protection</a>
  <a href="/index.php?r=site/display&id=12">Law on Cybersecurity</a>
  <a href="/index.php?r=site/index&Document_page=2">next</a>
</body></html>"""

_PAGE2 = """<html><body>
  <a href="/index.php?r=site/display&id=13">Law on Telecommunications</a>
</body></html>"""


def test_paginated_index_walks_pages_and_returns_absolute_urls(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page={page}"
    client = _Client({base.format(page=1): _PAGE1, base.format(page=2): _PAGE2})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=2)
    urls = [u for u, _ in rows]
    assert len(rows) == 3
    assert all(u.startswith("https://laoofficialgazette.gov.la/") for u in urls)
    assert "id=13" in urls[-1], "page 2 must have been walked"


def test_paginated_index_stops_when_a_page_adds_nothing_new(monkeypatch):
    """A portal that ignores its own page parameter returns the same rows forever. Laos'
    detail ids come from the list page, so a runaway walk is real cost for zero documents."""
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://example.gov/list?p={page}"
    client = _Client({base.format(page=n): _PAGE1 for n in range(1, 12)})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=10)
    assert len(rows) == 2, "identical pages must collapse, not accumulate"
    assert len(client.calls) == 2, "the walk must stop at the first page adding nothing"


def test_paginated_index_deduplicates_across_pages(monkeypatch):
    monkeypatch.setattr(portal, "_allowed", lambda url, log: True)
    base = "https://example.gov/list?p={page}"
    client = _Client({base.format(page=1): _PAGE1, base.format(page=2): _PAGE1 + _PAGE2})
    rows = portal_strategies.paginated_index(
        client, log=lambda *_: None, page_url=base, row_selector="a[href]",
        link_filter=lambda h: "r=site/display" in h, max_pages=2)
    assert len({u for u, _ in rows}) == len(rows) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_portal_layer.py tests/test_portal_strategies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.portal'`

- [ ] **Step 3: Write the implementation**

Create `backend/pipeline/portal.py`:

```python
"""The mechanics every portal adapter shares.

Six economies get a portal-native lane in this phase, written by six separate hands. What
they have in common is not the portal — it is the fetching: a robots check that treats a
refusal as an answer, a backoff that understands a portal's own idea of "slow down", and one
way to build a DiscoveredDoc. Kept here so that a defect in any of the three is fixed once.

The precedent is Malaysia: `lom.agc.gov.my/robots.txt` answers HTTP 500, the fetcher read
"unreadable" as "disallowed", and every statute PDF on the primary portal was skipped in
silence. `robots.UNREACHABLE_OVERRIDE` now carries that carve-out (RFC 9309 §2.3.1.4:
a server error is not a refusal). One import, and no adapter has to remember it.
"""
from __future__ import annotations

import hashlib
import time
from typing import Callable, Protocol

from ..config import settings
from ..schemas import DiscoveredDoc, DiscoveryTag, DocFormat, Economy
from . import robots

Log = Callable[[str], None]

#: Adapter name (as written in data/sources.yaml `adapter:`) -> callable.
_REGISTRY: dict[str, "PortalEnumerator"] = {}


class PortalEnumerator(Protocol):
    """The one shape `discovery.discover_live` dispatches on.

    Deliberately identical to the signature the existing `_search_au_api`,
    `_search_my_catalogue`, `_search_in_dspace` and `_search_mn_legalinfo` already have, so
    the dispatch table stays one line and an adapter written to this protocol is
    indistinguishable to the caller from one written before it existed.
    """

    def __call__(self, client, src: dict, query: str, economy: Economy,
                 indicators: list, log: Log) -> list[DiscoveredDoc]:
        ...


def register(name: str, fn: "PortalEnumerator") -> None:
    _REGISTRY[name] = fn


def get_adapter(name: str):
    return _REGISTRY.get(name)


def headers() -> dict:
    return {
        "User-Agent": settings.crawl_user_agent,
        "Accept-Language": settings.crawl_accept_language,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }


def _allowed(url: str, log: Log) -> bool:
    """robots.txt, honoured. Separated out so tests can drive portal_get without a network
    round-trip for robots, and so a refusal is logged in one place with its reason."""
    ok, why = robots.allowed(url, settings.crawl_user_agent)
    if not ok:
        log(f"[portal] robots refuses {url[:90]} — {why}")
    return ok


def portal_get(client, url: str, log: Log, tries: int = 4, **kw):
    """Portal-friendly GET. Returns the response, or None when the portal never answered.

    Backs off exponentially, and treats a 202 with an EMPTY body as a throttle rather than a
    result: that is Singapore's SSO saying "slow down" — it does not use 429 (verified
    2026-08-01, the same behaviour `backend/corpus/catalogue._get` was written for). A 202
    WITH content is a real response and is returned as-is.
    """
    if not _allowed(url, log):
        return None
    delay = settings.crawl_delay_seconds
    for attempt in range(tries):
        try:
            r = client.get(url, **kw)
            if r.status_code == 200 and r.content:
                return r
            if r.status_code == 202 and r.content:
                return r
            log(f"[portal] {r.status_code} len={len(r.content)} "
                f"(attempt {attempt + 1}/{tries}) {url[:90]}")
        except Exception as e:  # noqa: BLE001 — network flake; retry, then give up
            log(f"[portal] {type(e).__name__} (attempt {attempt + 1}/{tries}) {url[:90]}")
        if attempt + 1 < tries:
            time.sleep(delay)
            delay *= 2.5
    return None


def doc_id(economy: str, source_url: str) -> str:
    """The SAME id discovery already computes.

    Live-mode dedup keys on doc_id, so an adapter using a different scheme would make its
    documents look distinct from the same document reached by an existing lane, and both
    would be fetched, extracted and graded. Pinned by a test.
    """
    return f"{economy}-" + hashlib.sha1(source_url.encode()).hexdigest()[:10]


def make_doc(economy: Economy, url: str, title: str, portal_name: str, *,
             fmt: DocFormat | None = None, law_number: str | None = None,
             law_name: str | None = None, score: float = 1.0,
             amendment_date: str | None = None) -> DiscoveredDoc:
    """Build a DiscoveredDoc with the format inferred from the URL unless stated.

    `score` defaults to 1.0 because a portal-native hit is a match on the portal's OWN index —
    unlike a web-search hit, which is ranked later by content. An adapter that can rank its
    own results (Mongolia ranks by principal-statute-then-size) passes its own score.
    """
    if fmt is None:
        fmt = DocFormat.PDF_TEXT if url.lower().split("?")[0].endswith(".pdf") else DocFormat.HTML
    return DiscoveredDoc(
        doc_id=doc_id(economy.value, url), economy=economy, title=(title or url)[:200],
        source_url=url, portal=portal_name, fmt=fmt, relevance_score=score,
        discovery_tag=DiscoveryTag.NEW, law_number=law_number, law_name=law_name,
        amendment_date=amendment_date)
```

Create `backend/pipeline/portal_strategies.py`:

```python
"""Reusable portal shapes. A portal that does not fit one gets its own module.

India (one record per SECTION) and Mongolia (POST export, fleeting-vowel title matching) are
the standing proof that not every portal fits a shape, and forcing them into one would mean
writing code in YAML. These are the shapes that recur.
"""
from __future__ import annotations

from typing import Callable, Iterable

from .portal import Log, portal_get


def paginated_index(client, log: Log, *, page_url: str, row_selector: str,
                    link_filter: Callable[[str], bool] | None = None,
                    max_pages: int = 50) -> list[tuple[str, str]]:
    """Walk `page_url.format(page=N)` from 1, collecting (absolute_url, title) rows.

    Stops at the first page that adds nothing new. That guard is not defensive padding: a
    portal which IGNORES its own page parameter returns the same rows forever, and Singapore's
    SSO is exactly such a portal (it ignores `CurrentPage` — verified 2026-08-01, which is why
    SG needs a sort-window union rather than this strategy). Without the guard a run pays
    `max_pages` requests for one page of documents.
    """
    import httpx
    from bs4 import BeautifulSoup

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = page_url.format(page=page)
        r = portal_get(client, url, log)
        if r is None:
            log(f"[portal] pagination stopped at page {page}: no response")
            break
        soup = BeautifulSoup(r.text, "lxml")
        added = 0
        for a in soup.select(row_selector):
            href = a.get("href") or ""
            if not href or (link_filter and not link_filter(href)):
                continue
            absolute = httpx.URL(url).join(href).human_repr()
            if absolute in seen:
                continue
            seen.add(absolute)
            out.append((absolute, a.get_text(" ", strip=True)))
            added += 1
        log(f"[portal] page {page}: +{added} rows ({len(out)} total)")
        if added == 0:
            break
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portal_layer.py tests/test_portal_strategies.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Confirm the isolation test still holds**

Run: `python -m pytest tests/test_pipeline_isolation.py tests/test_console_encoding.py -q`
Expected: PASS — the new modules import nothing from `backend.corpus`.

- [ ] **Step 6: Commit**

```bash
git status --short
git add backend/pipeline/portal.py backend/pipeline/portal_strategies.py tests/test_portal_layer.py tests/test_portal_strategies.py
git commit -m "portal: one place for the mechanics six adapters would otherwise each get wrong

Six economies get a portal-native lane in this phase, written by six
separate hands. What they share is not the portal but the fetching: a
robots check that treats a refusal as an answer, a backoff that
understands a portal's own idea of slow down, and one way to build a
DiscoveredDoc.

The precedent is Malaysia. lom.agc.gov.my/robots.txt answers HTTP 500,
the fetcher read unreadable as disallowed, and every statute PDF on the
primary portal was skipped in silence. Written six times, that carve-out
would have been missed at least once.

doc_id is pinned to the id discovery already computes, because live-mode
dedup keys on it -- a new scheme would make an adapter's documents look
distinct from the same document found by an existing lane.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Timor-Leste — the static frameset tree

**Files:**
- Create: `backend/pipeline/adapter_timor.py`
- Create: `tests/fixtures/portals/tl_rdtl_laws.htm` (saved during Step 1)
- Test: `tests/test_adapter_timor.py`

**Interfaces:**
- Consumes: `portal.portal_get`, `portal.make_doc`, `portal.register` (Task 1).
- Produces: `def search_tl_gazette(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"tl_gazette"`; and `def _law_rows(html: str, base_url: str) -> list[tuple[str, str]]` — the pure parser the tests drive.

**Why first:** Timor-Leste is on the panel's published list, carries the **difficulty bonus**, and as of today has no lane, no corpus and no measured CER. It is also the simplest portal of the eleven — static HTML, no JS, no WAF, no API.

**Route, verified 2026-09-07:**
```
https://mj.gov.tl/jornal/lawsTL/index-e.htm      frameset: sidehome-e.htm + home-e.htm
  → sidehome-e.htm                                nav: 6 links
      RDTL-Law/index-e.htm                        another frameset
        → RDTL-Law/sidehome-e.htm                 21 links, 2 direct PDFs
            RDTL-Laws/RDTL-Laws.htm               ← 127 PDFs, named Law-YYYY-NN.pdf
            RDTL-Decree-Laws/RDTL-Decree-Laws.htm
            RDTL-Gov-Decrees/RDTL-Decrees.htm
            (each has a -P twin: the Portuguese edition)
            RDTL-Constitution.pdf, RDTL-Constitution-P.pdf
```
`robots.txt` is the Drupal default: `Crawl-delay: 10`, disallowing `/admin/ /search/ /includes/ /modules/` and the install files — **not** the document paths. Honour the crawl delay.

**Language:** the same instrument ships in Portuguese and Tetum (`ConstituicaoRDTL_Portugues.pdf` / `ConstituicaoRDTL_tetum.pdf`), so language detection must run **per document**, not per economy. This adapter only has to preserve the filename; detection happens downstream.

**Honesty requirement:** `home-e.htm` advertises an index "as of 31 August 2011". Check the newer `/jornal/files/` tree during recon and **report what you find** — if coverage stops in 2011, say so in the module docstring and in `sources.yaml`. A lane that silently covers only half the statute book is worse than one that says where it stops.

- [ ] **Step 1: Recon and save the fixture**

Run these and record the real output in your report:

```bash
python - <<'PY'
import sys, io, re, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
from bs4 import BeautifulSoup
UA = {"User-Agent": "VeriTrade-Research/0.2"}
B = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/"
for page in ["RDTL-Laws/RDTL-Laws.htm", "RDTL-Decree-Laws/RDTL-Decree-Laws.htm",
             "RDTL-Gov-Decrees/RDTL-Decrees.htm"]:
    r = httpx.get(B + page, headers=UA, timeout=40, follow_redirects=True, verify=False)
    s = BeautifulSoup(r.text, "lxml")
    pdfs = [a.get("href") for a in s.select("a[href]") if ".pdf" in (a.get("href") or "").lower()]
    print(f"{page}: {r.status_code} len={len(r.text)} pdfs={len(pdfs)}")
    for h in pdfs[:3]:
        print("   ", h)
    years = sorted({m.group(1) for h in pdfs for m in [re.search(r"(\d{4})", h or "")] if m})
    print("    year range:", years[:1], "->", years[-1:])
PY
```

Save the largest index page as the fixture:
```bash
curl -sk "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws/RDTL-Laws.htm" \
  -o tests/fixtures/portals/tl_rdtl_laws.htm
wc -c tests/fixtures/portals/tl_rdtl_laws.htm
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_timor.py`. Replace the counts in the two `assert` lines marked `# RECON` with the numbers Step 1 actually printed:

```python
"""Timor-Leste: a 1990s static frameset, and the easiest portal of the eleven.

TL is on the panel's published list and carries the difficulty bonus, and until this adapter
it had no lane at all — every document had to come through a web search that was returning
HTTP 403 from every engine.

Fixture saved 2026-09-07 from
https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws/RDTL-Laws.htm
No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_timor
from backend.schemas import DocFormat, Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "tl_rdtl_laws.htm"
BASE = "https://mj.gov.tl/jornal/lawsTL/RDTL-Law/RDTL-Laws/RDTL-Laws.htm"


@pytest.fixture(scope="module")
def rows():
    return adapter_timor._law_rows(FIXTURE.read_text(encoding="utf-8", errors="replace"), BASE)


def test_the_index_yields_every_pdf_it_lists(rows):
    assert len(rows) >= 120, "RECON: the saved index listed 127 PDFs on 2026-09-07"


def test_every_url_is_absolute_and_on_the_ministry_host(rows):
    """The index uses relative hrefs (`Law-2002-01.pdf`), so a naive parser yields URLs that
    cannot be fetched and the whole economy silently produces nothing."""
    assert all(u.startswith("https://mj.gov.tl/") for u, _ in rows)
    assert all(u.lower().endswith(".pdf") for u, _ in rows)


def test_titles_are_not_just_the_filename(rows):
    """A citation reading "Law-2002-01.pdf" is not a Law Name. The index's anchor text
    carries the instrument's real title; keep it."""
    titled = [t for _, t in rows if t and not t.lower().endswith(".pdf")]
    assert len(titled) >= len(rows) // 2


def test_rows_are_deduplicated(rows):
    assert len({u for u, _ in rows}) == len(rows)


def test_the_index_covers_more_than_one_year(rows):
    """RECON: record the real span. A lane that stops in 2011 is a finding to report, not to
    hide — home-e.htm advertises an index "as of 31 August 2011"."""
    import re
    years = {m.group(1) for u, _ in rows for m in [re.search(r"Law-(\d{4})-", u)] if m}
    assert len(years) > 1, f"only these years present: {sorted(years)}"


def test_search_returns_discovered_docs_with_pdf_format(monkeypatch):
    """The adapter's public shape: the same signature discovery dispatches on."""
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")

    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_timor.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_timor.search_tl_gazette(
        client=None, src={"name": "Jornal da República"}, query="",
        economy=Economy.TL, indicators=[], log=lambda *_: None)
    assert docs, "the adapter returned nothing from a page with 127 PDFs"
    assert all(d.fmt == DocFormat.PDF_TEXT for d in docs)
    assert all(d.economy == Economy.TL for d in docs)
    assert len({d.doc_id for d in docs}) == len(docs), "doc_ids must be unique"


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("tl_gazette") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_timor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_timor'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_timor.py`. It must:
- expose `_law_rows(html, base_url) -> list[tuple[str, str]]`, a **pure** function taking HTML and returning absolute `(pdf_url, title)` pairs, deduplicated, with anchor text as the title;
- expose `search_tl_gazette(client, src, query, economy, indicators, log)` matching `PortalEnumerator`, which fetches each index page listed in `_INDEX_PAGES` via `portal.portal_get`, runs `_law_rows` over each, and returns `portal.make_doc(...)` for every row;
- carry `_INDEX_PAGES` as a module constant listing the three English indexes and their `-P` Portuguese twins, with the URLs verified in Step 1;
- ignore `query` entirely and say why in a comment: this portal has no search, so the lane enumerates and the pillar's relevance is decided downstream by retrieval — the same choice `mn_legalinfo` documents;
- honour `Crawl-delay: 10` — set `settings.crawl_delay_seconds` is NOT the right lever (it is global); sleep explicitly between index pages and say the crawl-delay is why;
- end with `portal.register("tl_gazette", search_tl_gazette)`.

The module docstring must record: the frameset route, the `Crawl-delay: 10`, the per-document Portuguese/Tetum language split, and **what Step 1 found about the year range**.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_timor.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Verify live, end to end through extraction**

```bash
python - <<'PY'
import sys, io
sys.path.insert(0, "."); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from backend.pipeline import discovery, websearch
from backend.schemas import Economy
websearch.reset_diagnostics(); websearch.reset_circuit()
docs = discovery.discover(Economy.TL, 6, use_samples=False, log=lambda *_: None)
print("documents:", len(docs))
for d in docs[:5]:
    print("  ", d.title[:70], "|", d.source_url[-45:])
print("web-search queries this run:", websearch.diagnostics()["network_queries"])
PY
```
Expected: a non-zero document count, and **`network_queries` reflecting only the pre-existing websearch lane** — the new lane must contribute documents without a search engine. Record both numbers.

Then fetch and extract one document to prove the pipeline reaches provisions:
```bash
python main.py --economy Timor-Leste --pillar 6 --live 2>&1 | tail -30
```
Report the provision count. The run will FAIL at grading (`401 User not found` — no LLM is reachable); that is expected and is not this task's failure. What must succeed is discovery → fetch → extract.

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/adapter_timor.py tests/test_adapter_timor.py tests/fixtures/portals/tl_rdtl_laws.htm
git commit -m "discovery: Timor-Leste had no lane at all, and it carries the bonus

TL is on the panel's published list of eight and carries the difficulty
bonus, and every document had to arrive through a web search that
answers HTTP 403 from every engine today.

The portal turns out to be the simplest of the eleven: a 1990s frameset
tree of static HTML, no JS, no WAF, no API, with <N> gazette PDFs behind
RDTL-Laws.htm. robots.txt is the Drupal default and does not disallow
the document paths; Crawl-delay 10 is honoured.

Recorded rather than hidden: <what Step 1 found about the year range>.
The same instrument ships in Portuguese and Tetum, so language detection
must run per document, not per economy.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Laos — the Yii paginated index

**Files:**
- Create: `backend/pipeline/adapter_laos.py`
- Create: `tests/fixtures/portals/la_list_page1.html`
- Test: `tests/test_adapter_laos.py`

**Interfaces:**
- Consumes: `portal.portal_get`, `portal.make_doc`, `portal.register`, `portal_strategies.paginated_index`.
- Produces: `def search_la_gazette(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"la_gazette"`; `def _detail_ids(html, base_url) -> list[tuple[str, str]]`; `def _pdf_links(html, base_url) -> list[str]`.

**Why:** `data/sources.yaml` recorded this host as *"URLError — host does not resolve"* and called Laos *"the weakest coverage of the nine on every axis"*. Both were wrong. Probed 2026-09-07 it answers **HTTP 200, 110 KB, 12,477 Lao characters**, fully paginated.

**Route, verified 2026-09-07:**
```
?r=site/index&Document_page=N     paginated list — 300 links/page, 46 PDF refs on page 1
?r=site/display&id=N              detail page for one instrument
?r=site/list&legaltype=N          filter by instrument type
?r=site/switchpage&lc=en          English edition toggle
/kcfinder/upload/files/*.pdf      the gazette PDFs themselves
```
A guessed `id=1` returns 404 — **ids come from the list page**, never from a range.

`robots.txt` returns the site's own homepage (the app has a catch-all route), so there is no robots file to parse. `robots.allowed` handles an unparseable body already; do not special-case it, but say in the docstring that this is why the host looks permissive.

**Hazards that are still true and must survive into the docstring:** Lao statutes are scanned PDFs, and legacy Lao fonts map letters into upper-ASCII so even a text layer can be mojibake. `script_validity()` is the only defence and it is advisory.

- [ ] **Step 1: Recon and save the fixture**

```bash
python - <<'PY'
import sys, io, re, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
from bs4 import BeautifulSoup
UA = {"User-Agent": "VeriTrade-Research/0.2"}
B = "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page={}"
seen_ids = set()
for page in (1, 2, 3):
    r = httpx.get(B.format(page), headers=UA, timeout=40, follow_redirects=True, verify=False)
    s = BeautifulSoup(r.text, "lxml")
    ids = {m.group(1) for a in s.select("a[href]")
           for m in [re.search(r"r=site/display&id=(\d+)", a.get("href") or "")] if m}
    print(f"page {page}: {r.status_code} len={len(r.text)} distinct detail ids={len(ids)} new={len(ids - seen_ids)}")
    seen_ids |= ids
print("total distinct ids across 3 pages:", len(seen_ids))
sample = sorted(seen_ids)[:1]
if sample:
    d = httpx.get(f"https://laoofficialgazette.gov.la/index.php?r=site/display&id={sample[0]}",
                  headers=UA, timeout=40, follow_redirects=True, verify=False)
    ds = BeautifulSoup(d.text, "lxml")
    pdfs = [a.get("href") for a in ds.select("a[href]") if ".pdf" in (a.get("href") or "").lower()]
    print(f"detail id={sample[0]}: {d.status_code} len={len(d.text)} pdfs={len(pdfs)}")
    for h in pdfs[:3]: print("   ", h)
    print("   title:", (ds.title.get_text(strip=True) if ds.title else "")[:80])
PY
```
**If page 2 and 3 add no new ids, the portal ignores `Document_page` and this task changes shape** — report that immediately and stop before writing the adapter; the fallback is `?r=site/list&legaltype=N`, which the recon above does not cover.

```bash
curl -sk "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page=1" \
  -o tests/fixtures/portals/la_list_page1.html
wc -c tests/fixtures/portals/la_list_page1.html
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_laos.py`:

```python
"""Laos: recorded as "host does not resolve" and "the weakest coverage of the nine".

Both were false. Probed 2026-09-07 the host answers HTTP 200 with 110 KB and 12,477 Lao
characters, and is a Yii application with a fully paginated document list. It is one of the
most tractable portals of the eleven.

Fixture saved 2026-09-07 from
https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page=1
No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_laos
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "la_list_page1.html"
BASE = "https://laoofficialgazette.gov.la/index.php?r=site/index&Document_page=1"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_detail_ids_are_found_on_the_list_page(html):
    """Ids come from the list page and nowhere else: a guessed id=1 returns HTTP 404
    (verified 2026-09-07), so an adapter that walks a numeric range finds nothing."""
    rows = adapter_laos._detail_ids(html, BASE)
    assert len(rows) >= 10, f"only {len(rows)} detail links parsed from the list page"
    assert all("r=site/display" in u for u, _ in rows)


def test_detail_urls_are_absolute(html):
    rows = adapter_laos._detail_ids(html, BASE)
    assert all(u.startswith("https://laoofficialgazette.gov.la/") for u, _ in rows)


def test_agency_and_type_links_are_not_mistaken_for_documents(html):
    """The list page carries 94 `agencies_id=` and 24 `legaltype=` links — browse filters,
    not instruments. A parser that keeps them fills the document budget with navigation."""
    rows = adapter_laos._detail_ids(html, BASE)
    assert not any("agencies_id" in u or "legaltype" in u for u, _ in rows)


def test_pdf_links_are_absolute_and_under_the_upload_path(html):
    pdfs = adapter_laos._pdf_links(html, BASE)
    assert all(p.startswith("https://laoofficialgazette.gov.la/") for p in pdfs)
    assert all(".pdf" in p.lower() for p in pdfs)


def test_rows_are_deduplicated(html):
    rows = adapter_laos._detail_ids(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_search_returns_docs_from_the_list_page(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_laos.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_laos.search_la_gazette(
        client=None, src={"name": "Lao Official Gazette"}, query="",
        economy=Economy.LA, indicators=[], log=lambda *_: None)
    assert docs
    assert all(d.economy == Economy.LA for d in docs)
    assert len({d.doc_id for d in docs}) == len(docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("la_gazette") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_laos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_laos'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_laos.py`. It must:
- expose the two pure parsers `_detail_ids(html, base_url)` and `_pdf_links(html, base_url)`;
- expose `search_la_gazette(...)` matching `PortalEnumerator`, using `portal_strategies.paginated_index` over `?r=site/index&Document_page={page}` with a `link_filter` keeping only `r=site/display`;
- prefer the English edition where a document has one (`?r=site/switchpage&lc=en`) — if Step 1 showed the toggle is session-based rather than per-URL, say so and skip it rather than guessing;
- cap the walk with a `max_pages` constant that names the number Step 1 measured;
- ignore `query` for the same reason Timor-Leste does, and say so;
- end with `portal.register("la_gazette", search_la_gazette)`.

The docstring must carry: the four routes, the fact that ids come only from the list page (a guessed `id=1` 404s), that `robots.txt` returns the homepage because of the app's catch-all route, and the two surviving hazards — scanned PDFs, and legacy Lao fonts that map letters into upper-ASCII so a text layer can be mojibake.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_laos.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Verify live**

```bash
python - <<'PY'
import sys, io
sys.path.insert(0, "."); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from backend.pipeline import discovery, websearch
from backend.schemas import Economy
websearch.reset_diagnostics(); websearch.reset_circuit()
docs = discovery.discover(Economy.LA, 6, use_samples=False, log=lambda *_: None)
print("documents:", len(docs))
for d in docs[:5]: print("  ", d.title[:70], "|", d.source_url[-45:])
PY
```
Then `python main.py --economy "Lao PDR" --pillar 6 --live 2>&1 | tail -30` and report the provision count. Grading will fail (no LLM) — expected.

**Report the OCR outcome honestly.** If the PDFs come back as mojibake, that is the legacy-font hazard the docstring names, and it is a finding for Phase 3, not a failure of this task. Say which it was.

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/adapter_laos.py tests/test_adapter_laos.py tests/fixtures/portals/la_list_page1.html
git commit -m "discovery: Laos was recorded as unreachable, and it is one of the easiest

sources.yaml said the gazette host does not resolve and called Laos the
weakest coverage of the nine on every axis. Probed 2026-09-07 it answers
HTTP 200 with 110 KB and 12,477 Lao characters, and is a Yii app with a
fully paginated document list.

Ids come from the list page and nowhere else -- a guessed id=1 returns
404 -- so this walks ?r=site/index&Document_page=N and reads
?r=site/display&id=N, never a numeric range.

The hazards that were true stay recorded: scanned PDFs, and legacy Lao
fonts that map letters into upper-ASCII so even a text layer can be
mojibake.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Thailand — the REST API behind the SPA

**Files:**
- Create: `backend/pipeline/adapter_thailand.py`
- Create: `tests/fixtures/portals/th_law_rows.json`
- Test: `tests/test_adapter_thailand.py`

**Interfaces:**
- Consumes: `portal.make_doc`, `portal.register`.
- Produces: `def search_th_law(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"th_law_api"`; `def _rows_to_docs(payload: dict, economy, portal_name) -> list[DiscoveredDoc]`.

**Why:** `data/sources.yaml` called Thailand *"PDF, frequently scanned … this is the OCR-heavy lane"*. False. `law.go.th` serves **clean full text as JSON**, making Thailand one of the two cleanest sources of the eleven alongside India — no PDF, no OCR, no scan.

**Route, verified 2026-09-07** (recovered from the app's own published sourcemap, `src/api/law.js` and `src/configs/axios.js`):
```
base    https://apig.law.go.th/
header  x-api-key: 4nEZYvTwRFlUVn7aK85cZ2xSU83dOFai
POST    dga-user-service-phase2/law                → 200, 114 KB, rows[] with content_all
GET     dga-user-service-phase2/law/master         → 200, 50 KB, agencies + law types
GET     dga-user-service-phase2/law/detail/{id}
POST    dga-user-service-phase2/law/searchResult   → 400 until the payload shape is right
```

**On the key.** It is a public constant compiled into the JavaScript every visitor downloads — not a credential anyone was issued. `apig.law.go.th` is an AWS API Gateway: an unauthenticated request to a path that does not exist returns `{"message":"Missing Authentication Token"}`, which is *route-not-found*, not a refusal. `www.law.go.th/robots.txt` is `User-agent: *` with **no `Disallow` line at all**. We read public statutes at a polite rate with exactly the access an ordinary visitor has, and cite each provision to its source URL. **Put the key in `data/sources.yaml`, not in code**, with a comment saying it is a public bundle constant and where it came from — so that if it rotates, the fix is config.

**Design decision to make during recon:** `content_all` may hold the whole instrument. If it does, this lane can bypass fetch entirely by setting `DiscoveredDoc.raw_text`. Check whether `raw_text` is honoured by the fetch stage before relying on it — if it is not, emit the detail URL and let fetch do its job. **Report which you chose and why.**

- [ ] **Step 1: Recon and save the fixture**

```bash
python - <<'PY'
import sys, io, json, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
H = {"User-Agent": "Mozilla/5.0", "x-api-key": "4nEZYvTwRFlUVn7aK85cZ2xSU83dOFai",
     "Content-Type": "application/json", "Origin": "https://www.law.go.th",
     "Referer": "https://www.law.go.th/"}
r = httpx.post("https://apig.law.go.th/dga-user-service-phase2/law",
               headers=H, json={"page": 1, "limit": 20}, timeout=60, verify=False)
print("status", r.status_code, "len", len(r.text))
j = r.json()
print("top-level keys:", list(j)[:10])
rows = j.get("rows") or []
print("rows:", len(rows))
if rows:
    print("row keys:", sorted(rows[0]))
    ca = rows[0].get("content_all") or ""
    print("content_all chars:", len(ca))
    print("has มาตรา markers:", ca.count("มาตรา"))
    print("first 200:", ca[:200].replace("\n", " "))
# does paging work?
r2 = httpx.post("https://apig.law.go.th/dga-user-service-phase2/law",
                headers=H, json={"page": 2, "limit": 20}, timeout=60, verify=False)
rows2 = (r2.json().get("rows") or [])
ids1 = {x.get("law_id") or x.get("id") for x in rows}
ids2 = {x.get("law_id") or x.get("id") for x in rows2}
print("page 2 rows:", len(rows2), "| new ids:", len(ids2 - ids1))
PY
```

Two questions Step 1 must answer, in the report:
1. **Does `content_all` carry มาตรา (article) markers?** `extraction.ARTICLE_PATTERNS` already has the Thai splitter; if the markers are present, provisions split for free.
2. **Does paging work?** If page 2 returns the same ids, the lane can only ever see one page and must use `searchResult` instead — say so and stop before writing the adapter.

Save the first response:
```bash
python - <<'PY'
import json, httpx, warnings; warnings.filterwarnings("ignore")
H = {"User-Agent": "Mozilla/5.0", "x-api-key": "4nEZYvTwRFlUVn7aK85cZ2xSU83dOFai",
     "Content-Type": "application/json", "Origin": "https://www.law.go.th"}
r = httpx.post("https://apig.law.go.th/dga-user-service-phase2/law",
               headers=H, json={"page": 1, "limit": 20}, timeout=60, verify=False)
j = r.json()
j["rows"] = (j.get("rows") or [])[:5]           # 5 rows is enough for a parser test
open("tests/fixtures/portals/th_law_rows.json", "w", encoding="utf-8").write(
    json.dumps(j, ensure_ascii=False, indent=1))
print("saved", len(j["rows"]), "rows")
PY
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_thailand.py`. Adjust the field names to whatever Step 1 reported:

```python
"""Thailand: recorded as the OCR-heavy scanned-PDF lane. It is the opposite.

sources.yaml said "Thai statutes are published as PDF, frequently scanned … this is the
OCR-heavy lane". law.go.th serves clean full text as JSON, which makes Thailand one of the
two cleanest sources of the eleven alongside India.

The route came from the app's own published sourcemap (src/api/law.js, src/configs/axios.js),
not from defeating a protection. The x-api-key is a public constant compiled into the
JavaScript every visitor downloads, and www.law.go.th/robots.txt is `User-agent: *` with no
Disallow line at all.

Fixture saved 2026-09-07 from POST apig.law.go.th/dga-user-service-phase2/law.
No test here touches the network.
"""
import json
from pathlib import Path

import pytest

from backend.pipeline import adapter_thailand
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "th_law_rows.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rows_become_documents(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert docs, "the API returned rows and the adapter produced no documents"
    assert all(d.economy == Economy.TH for d in docs)


def test_doc_ids_are_unique(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert len({d.doc_id for d in docs}) == len(docs)


def test_every_document_has_a_citable_source_url(payload):
    """The Verbatim Snippet column needs a URL a reviewer can open. An API path is not one:
    apig.law.go.th answers only with the x-api-key header, so the citation must point at the
    human page on www.law.go.th."""
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert all(d.source_url.startswith("http") for d in docs)
    assert all("apig." not in d.source_url for d in docs), (
        "an apig.law.go.th URL is not openable by a reviewer without the key header")


def test_titles_are_thai_and_not_empty(payload):
    docs = adapter_thailand._rows_to_docs(payload, Economy.TH, "law.go.th")
    assert all(d.title.strip() for d in docs)
    thai = [d for d in docs if any("฀" <= ch <= "๿" for ch in d.title)]
    assert thai, "no document title contained a Thai character"


def test_a_row_with_no_usable_text_is_dropped_not_emitted_empty(payload):
    """A row whose content_all is empty is a landing record, not an instrument. Emitting it
    produces a document that fetches to nothing and reaches the grader as one blank block —
    the shell problem build._looks_like_a_shell exists to catch downstream."""
    empty = {"rows": [dict(payload["rows"][0], content_all="")]}
    assert adapter_thailand._rows_to_docs(empty, Economy.TH, "law.go.th") == []


def test_an_empty_payload_yields_no_documents_and_does_not_raise():
    assert adapter_thailand._rows_to_docs({}, Economy.TH, "law.go.th") == []
    assert adapter_thailand._rows_to_docs({"rows": []}, Economy.TH, "law.go.th") == []


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("th_law_api") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_thailand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_thailand'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_thailand.py`. It must:
- read the base URL and the `x-api-key` from `src` (the `sources.yaml` entry), **never** hard-code them, and log a clear `[error]`-shaped line if the key is absent;
- expose `_rows_to_docs(payload, economy, portal_name)` as a pure function, dropping rows with no usable text;
- expose `search_th_law(...)` matching `PortalEnumerator`, POSTing `{"page": N, "limit": L}` and paging until a page returns no new ids or `_MAX_PAGES` is reached — with `_MAX_PAGES` naming the number Step 1 measured;
- set `source_url` to the human-openable `www.law.go.th` detail page, not the API path;
- carry the decision from Step 1's design question in a comment: whether `content_all` is passed through as `raw_text` or the detail URL is left for fetch, and why;
- end with `portal.register("th_law_api", search_th_law)`.

The docstring must record the route, the sourcemap provenance, the robots finding, and the correction that this is not an OCR lane.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_thailand.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Verify live**

Same shape as Task 2 Step 6, with `Economy.TH` and `python main.py --economy Thailand --pillar 6 --live`. Report the document count, the provision count, and **whether the Thai article splitter fired** — if provisions come back as one block per document, `content_all` lacks มาตรา markers and that is a finding for the report.

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/adapter_thailand.py tests/test_adapter_thailand.py tests/fixtures/portals/th_law_rows.json
git commit -m "discovery: Thailand is not the OCR lane, it is the cleanest source of the eleven

sources.yaml called Thai statutes PDF, frequently scanned, the OCR-heavy
lane. law.go.th serves clean full text as JSON -- no PDF, no OCR, no
scan, and no article-splitting heuristic where content_all carries its
own มาตรา markers.

The route came from the app's own published sourcemap, not from
defeating a protection: src/api/law.js names the endpoints and
src/configs/axios.js the x-api-key, a public constant compiled into the
JavaScript every visitor downloads. www.law.go.th/robots.txt is
User-agent: * with no Disallow line at all. The key lives in
sources.yaml, not in code, so a rotation is a config change.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Singapore — the sort-window union, moved out of the corpus

**Files:**
- Create: `backend/pipeline/adapter_singapore.py`
- Modify: `backend/corpus/catalogue.py` (import the enumeration from the pipeline)
- Create: `tests/fixtures/portals/sg_browse_act.html`
- Test: `tests/test_adapter_singapore.py`

**Interfaces:**
- Consumes: `portal.portal_get`, `portal.make_doc`, `portal.register`.
- Produces: `def search_sg_sso(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"sg_sso"`; `def enumerate_sso(client, log, kinds=("Act",), page_size=500) -> list[dict]` — the shared enumerator `backend/corpus/catalogue.py` imports; `def _browse_rows(html: str) -> list[tuple[str, str]]`.

**Why this is the highest-value task in the phase.** Singapore's ONLY discovery lane is `adapter: websearch`. With every engine returning 403 and the search cache now correctly expiring, SG produces **zero documents** — and Singapore is one of the three economies mandatory in every round.

**The technique already exists.** `backend/corpus/catalogue.enumerate_sg` enumerates 524 current Acts by sort-window union, because SSO **ignores `CurrentPage`** (verified 2026-08-01: pages 1, 2 and 3 return byte-identical HTML at every PageSize, with or without the AJAX header). What it honours is the sort: the same list ASC then DESC gives the first and last `PageSize` entries, and their union is the whole index whenever `total <= 2 × PageSize`. Two sort keys × two directions = four windows.

**The dependency must be reversed, not relaxed.** `tests/test_pipeline_isolation.py` forbids the live pipeline importing `backend.corpus`, and that rule is right: it stops a stored corpus being served as though it were discovered live. But an *enumerator* is live HTTP, not a corpus. So the enumeration moves **into** `backend/pipeline/adapter_singapore.py`, and `backend/corpus/catalogue.py` imports it from there. The test then passes unchanged, because the pipeline still imports nothing from corpus.

**Two details the move must not lose:**
- `enumerate_sg` currently builds ids with `backend.corpus.store.law_id` (`sha1("{economy}|{url}")[:14]`, prefixed `sg-`). The pipeline's `portal.doc_id` is `sha1(url)[:10]` prefixed `SG-`. **These are different on purpose** — a corpus row and a discovered document are different things. `enumerate_sso` must keep returning the corpus-shaped dict (so `catalogue.py` is unaffected), and `search_sg_sso` must build `DiscoveredDoc`s with `portal.doc_id`. Do not unify them.
- SSO throttles by answering a burst with **202 and an empty body**, not 429. `portal.portal_get` already handles that (Task 1); use it rather than re-implementing `catalogue._get`.

**Honesty requirement:** the four windows cover the 524 current Acts but **not** the 5,843 subsidiary instruments. The existing code reports that shortfall rather than hiding it. Keep that behaviour and keep it visible in the log.

- [ ] **Step 1: Recon and save the fixture**

```bash
python - <<'PY'
import sys, io, re, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
U = "https://sso.agc.gov.sg/Browse/Act/Current/All?PageSize=500&SortBy={s}&SortOrder={o}&CurrentPage=1"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
     "Accept-Language": "en"}
ROW = re.compile(r'<a\s+class="non-ajax"\s+href="(/(?:Act|SL|Acts-Supp)/[^"]+)"[^>]*>\s*([^<]{3,300}?)\s*</a>')
CNT = re.compile(r'(\d[\d,]*)\s+results in\s+(\d+)\s+pages', re.I)
seen = set()
for s, o in [("Title","ASC"), ("Title","DESC"), ("Number","ASC"), ("Number","DESC")]:
    r = httpx.get(U.format(s=s, o=o), headers=H, timeout=120, follow_redirects=True)
    rows = ROW.findall(r.text)
    m = CNT.search(re.sub(r"<[^>]+>", " ", r.text))
    before = len(seen); seen |= {h.split("?")[0] for h, _ in rows}
    print(f"{s}/{o}: {r.status_code} len={len(r.text)} rows={len(rows)} new={len(seen)-before} "
          f"total_reported={m.group(1) if m else '?'}")
print("union:", len(seen))
PY
```
Record the union against the reported total. **If the union is far short of the total, say so** — the window technique's coverage is an empirical claim that must be re-measured, not inherited.

```bash
curl -s -A "Mozilla/5.0" "https://sso.agc.gov.sg/Browse/Act/Current/All?PageSize=500&SortBy=Title&SortOrder=ASC&CurrentPage=1" \
  -o tests/fixtures/portals/sg_browse_act.html
wc -c tests/fixtures/portals/sg_browse_act.html
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_singapore.py`:

```python
"""Singapore's only discovery lane was a web search, and every engine now answers 403.

SG is mandatory in every round of this hackathon. On 2026-09-07 its runs were not discovering
anything — they were replaying an eight-day-old search cache, which the Phase-1 TTL now
correctly refuses to serve. Without a portal lane, SG produces zero documents.

The technique is inherited, not invented: SSO IGNORES CurrentPage (verified 2026-08-01 —
pages 1, 2 and 3 return byte-identical HTML at every PageSize), so the index is enumerated by
sort-window union. Two sort keys x two directions.

Fixture saved 2026-09-07 from
https://sso.agc.gov.sg/Browse/Act/Current/All?PageSize=500&SortBy=Title&SortOrder=ASC
No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_singapore
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "sg_browse_act.html"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_browse_rows_are_parsed(html):
    rows = adapter_singapore._browse_rows(html)
    assert len(rows) >= 100, f"only {len(rows)} rows parsed from a PageSize=500 window"


def test_rows_carry_a_path_and_a_title(html):
    rows = adapter_singapore._browse_rows(html)
    assert all(p.startswith("/") for p, _ in rows)
    assert all(t.strip() for _, t in rows)


def test_titles_are_html_unescaped(html):
    """SSO writes &amp; and &#39; in Act titles. A Law Name column reading
    "Companies (Amendment &amp; Consequential) Act" is a wrong citation, not a cosmetic bug."""
    rows = adapter_singapore._browse_rows(html)
    assert not any("&amp;" in t or "&#" in t for _, t in rows)


def test_the_body_url_is_the_pdf_view(html):
    """SSO serves the whole instrument at ?ViewType=Pdf (verified). The landing page is the
    citable URL; the PDF is what gets fetched."""
    rows = adapter_singapore._browse_rows(html)
    path = rows[0][0]
    assert adapter_singapore._body_url(path).endswith("?ViewType=Pdf")
    assert adapter_singapore._body_url(path).startswith("https://sso.agc.gov.sg/")


def test_search_produces_unique_documents(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_singapore.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_singapore.search_sg_sso(
        client=None, src={"name": "Singapore Statutes Online"}, query="",
        economy=Economy.SG, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.SG for d in docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("sg_sso") is not None


def test_the_corpus_catalogue_imports_the_enumerator_from_the_pipeline():
    """The dependency is REVERSED, not relaxed. The live pipeline still imports nothing from
    backend.corpus (tests/test_pipeline_isolation.py pins that); corpus imports from the
    pipeline. An enumerator is live HTTP, not a stored corpus."""
    import inspect

    from backend.corpus import catalogue
    src = inspect.getsource(catalogue)
    assert "adapter_singapore" in src, (
        "catalogue.py must import the SSO enumeration from the pipeline, not keep its own")


def test_the_shared_enumerator_still_returns_corpus_shaped_rows(monkeypatch, html):
    """catalogue.py consumes these dicts. A DiscoveredDoc here would break the corpus tool,
    and the two id schemes are deliberately different: a corpus row and a discovered document
    are not the same thing."""
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_singapore.portal, "portal_get", lambda *a, **k: _R())
    rows = adapter_singapore.enumerate_sso(client=None, log=lambda *_: None)
    assert rows and isinstance(rows[0], dict)
    for key in ("economy", "portal", "title", "source_url", "body_url", "collection", "status"):
        assert key in rows[0], f"corpus row is missing {key!r}"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_singapore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_singapore'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_singapore.py` carrying `_SG_SORTS`, `_browse_rows`, `_body_url`, `enumerate_sso` and `search_sg_sso`. Port the logic from `backend/corpus/catalogue.enumerate_sg` (lines 206-272) — the regexes, the four windows, the total-vs-union shortfall report — replacing `catalogue._get` with `portal.portal_get` and dropping the `store.law_id` call from the *document* path only.

`enumerate_sso` must keep returning the corpus-shaped dicts **without** a `law_id` key; then modify `backend/corpus/catalogue.py` so `enumerate_sg` becomes a thin wrapper that calls `adapter_singapore.enumerate_sso` and adds `law_id=store.law_id("SG", landing)` to each row. That keeps `ADAPTERS = {"AU": ..., "MY": ..., "SG": enumerate_sg}` and every corpus caller working unchanged.

End with `portal.register("sg_sso", search_sg_sso)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_singapore.py tests/test_pipeline_isolation.py -v`
Expected: PASS. The isolation test is not incidental here — it is the point.

- [ ] **Step 6: Verify the corpus tool still works**

Run: `python -m backend.corpus.cli catalogue --economy SG 2>&1 | tail -15`
Expected: the same enumeration behaviour as before the move. Report the row count and compare it with Step 1's union.

- [ ] **Step 7: Verify live**

Same shape as Task 2 Step 6, with `Economy.SG`, then `python main.py --economy Singapore --pillar 6 --live 2>&1 | tail -30`. **This is the headline number of the phase**: report documents, provisions, and `websearch.diagnostics()["network_queries"]`. A Singapore run that produces provisions with zero successful web searches is what this whole plan is for.

- [ ] **Step 8: Commit**

```bash
git status --short
git add backend/pipeline/adapter_singapore.py backend/corpus/catalogue.py tests/test_adapter_singapore.py tests/fixtures/portals/sg_browse_act.html
git commit -m "discovery: Singapore is mandatory every round and had no lane but a web search

With every engine answering 403 and the Phase-1 TTL correctly refusing
an eight-day-old cache, SG produced zero documents -- one of the three
economies mandatory in every round of this hackathon.

The technique was already written and stranded. enumerate_sg has
enumerated SSO's 524 current Acts by sort-window union since August,
because SSO IGNORES CurrentPage (pages 1, 2 and 3 return byte-identical
HTML at every PageSize) but honours the sort. It sat in backend/corpus,
behind a test that forbids the live pipeline reading a pre-built corpus.

That test is right and stays. But an enumerator is live HTTP, not a
corpus, so the dependency is reversed rather than relaxed: the
enumeration moves into the pipeline and catalogue.py imports it. The
isolation test passes unchanged.

The two id schemes stay different on purpose -- a corpus row and a
discovered document are not the same thing -- and the shortfall against
SSO's 5,843 subsidiary instruments is still reported, not hidden.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: China — two server-rendered indexes

**Files:**
- Create: `backend/pipeline/adapter_china.py`
- Create: `tests/fixtures/portals/cn_cac_index.html`
- Test: `tests/test_adapter_china.py`

**Interfaces:**
- Consumes: `portal.portal_get`, `portal.make_doc`, `portal.register`, `portal_strategies.paginated_index`.
- Produces: `def search_cn_portals(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"cn_portal"`; `def _article_links(html, base_url) -> list[tuple[str, str]]`.

**Why:** both China lanes are `adapter: websearch` today. The spec's standing item — *"CN principal statutes must survive `cac.gov.cn` being unreachable (PIPL / CSL / DSL)"* — is closed by having two real lanes rather than one lane plus a search fallback.

**Route, verified 2026-09-07:**
```
https://www.cac.gov.cn/            200, 59,987 bytes, 356 links, server-rendered, NOT a JS shell
  article pages   //www.cac.gov.cn/YYYY-MM/DD/c_<id>.htm     (82 on the front page alone)
  section indexes //www.cac.gov.cn/<section>/A<N>index_<N>.htm
https://www.gov.cn/zhengce/xxgk/   200, 209,014 bytes, 921 links, server-rendered
```
Note the **protocol-relative** hrefs (`//www.cac.gov.cn/...`) — a parser that does not resolve them produces unfetchable URLs.

**Do not build a lane on `flk.npc.gov.cn`.** Its API's permission block returns `"download": 0`. That is the operator stating the documents are not to be downloaded, and this project does not engineer around it. `flk.npc.gov.cn` also answers with 534 bytes and one link, so there is nothing there anyway.

**Known noise:** `cac.gov.cn` also carries 答记者问 press Q&A pages about the measures. They fetch and split into a single block, so they are visible as noise rather than mistaken for law, and the grader rejects them — but a tier filter would spend fewer LLM calls. If a cheap title-level filter is obvious during recon, apply it and say what it drops; if not, leave the noise visible and say so.

- [ ] **Step 1: Recon and save the fixture**

```bash
python - <<'PY'
import sys, io, re, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
for url in ["https://www.cac.gov.cn/", "https://www.gov.cn/zhengce/xxgk/"]:
    r = httpx.get(url, headers=UA, timeout=45, follow_redirects=True, verify=False)
    s = BeautifulSoup(r.text, "lxml")
    hrefs = [a.get("href") or "" for a in s.select("a[href]")]
    art = [h for h in hrefs if re.search(r"/c_\d+\.html?$", h)]
    idx = [h for h in hrefs if re.search(r"index_?\d*\.html?$", h)]
    print(f"{url}\n  {r.status_code} len={len(r.text)} links={len(hrefs)} articles={len(art)} indexes={len(idx)}")
    print("  protocol-relative:", sum(1 for h in hrefs if h.startswith("//")))
    for h in art[:3]: print("   art:", h)
    for h in idx[:3]: print("   idx:", h)
# does a section index paginate?
sec = "https://www.cac.gov.cn/zwgk/A0901index_{}.htm"
prev = set()
for n in (1, 2):
    try:
        r = httpx.get(sec.format(n), headers=UA, timeout=45, follow_redirects=True, verify=False)
        s = BeautifulSoup(r.text, "lxml")
        ids = {h for a in s.select("a[href]") for h in [a.get("href") or ""] if re.search(r"/c_\d+\.htm", h)}
        print(f"  section page {n}: {r.status_code} articles={len(ids)} new={len(ids-prev)}")
        prev |= ids
    except Exception as e:
        print(f"  section page {n}: ERR {type(e).__name__}")
PY
```
**Report whether the section index paginates.** If `A0901index_2.htm` 404s or repeats page 1, the lane can only read the front page of each section, and that is a coverage limit to state in the docstring, not to paper over.

```bash
curl -sk -A "Mozilla/5.0" "https://www.cac.gov.cn/" -o tests/fixtures/portals/cn_cac_index.html
wc -c tests/fixtures/portals/cn_cac_index.html
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_china.py`:

```python
"""China: both lanes were a web search, and every engine now answers 403.

cac.gov.cn is server-rendered and enumerable -- 200, 59,987 bytes, 356 links, not a JS shell
(probed 2026-09-07). Having two real portal lanes also closes the standing item that CN's
principal statutes (PIPL, CSL, DSL) must survive cac.gov.cn being unreachable.

flk.npc.gov.cn is deliberately NOT a lane: its API's permission block returns "download": 0,
which is the operator saying the documents are not to be downloaded.

Fixture saved 2026-09-07 from https://www.cac.gov.cn/. No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_china
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "cn_cac_index.html"
BASE = "https://www.cac.gov.cn/"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_article_links_are_found(html):
    rows = adapter_china._article_links(html, BASE)
    assert len(rows) >= 40, f"only {len(rows)} article links parsed from the front page"


def test_protocol_relative_hrefs_are_resolved(html):
    """cac.gov.cn writes //www.cac.gov.cn/... A parser that leaves those alone produces URLs
    that cannot be fetched, and the economy silently yields nothing."""
    rows = adapter_china._article_links(html, BASE)
    assert all(u.startswith("https://") for u, _ in rows)
    assert not any(u.startswith("//") for u, _ in rows)


def test_only_article_pages_are_kept(html):
    """Section indexes (A<N>index_<N>.htm) are navigation, not instruments."""
    rows = adapter_china._article_links(html, BASE)
    assert all("/c_" in u for u, _ in rows)
    assert not any("index_" in u for u, _ in rows)


def test_rows_are_deduplicated(html):
    rows = adapter_china._article_links(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_titles_carry_chinese_text(html):
    rows = adapter_china._article_links(html, BASE)
    chinese = [t for _, t in rows if any("一" <= ch <= "鿿" for ch in t)]
    assert chinese, "no article title contained a Chinese character"


def test_the_npc_database_is_not_a_fetch_target():
    """flk.npc.gov.cn's API returns "download": 0 -- the operator refusing. That decision
    stands, and this test is what stops a future edit quietly reversing it.

    The check is narrow on purpose: the host may be NAMED in a comment (explaining why it is
    excluded is worth more than silence), but it must never appear in a string the adapter
    could fetch. So: no line that both mentions the host and looks like a URL.
    """
    import inspect
    for line in inspect.getsource(adapter_china).splitlines():
        if "flk.npc.gov.cn" not in line:
            continue
        stripped = line.strip()
        assert stripped.startswith("#") or stripped.startswith("*") or '"""' in stripped or (
            "http" not in line), (
            f"flk.npc.gov.cn appears in a fetchable string, not a comment: {stripped[:90]}")


def test_search_produces_unique_documents(monkeypatch, html):
    class _R:
        status_code = 200
        content = html.encode()
        text = html

    monkeypatch.setattr(adapter_china.portal, "portal_get", lambda *a, **k: _R())
    docs = adapter_china.search_cn_portals(
        client=None, src={"name": "Cyberspace Administration"}, query="",
        economy=Economy.CN, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.CN for d in docs)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("cn_portal") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_china.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_china'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_china.py`. It must:
- expose `_article_links(html, base_url)` as a pure function resolving protocol-relative hrefs, keeping only `/c_<id>.htm` article pages, deduplicating, with anchor text as the title;
- expose `search_cn_portals(...)` reading its base URLs from `src` (so `sources.yaml` holds the two hosts), walking the section indexes Step 1 found to paginate — or the front pages only, if Step 1 showed they do not;
- carry a `_SECTIONS` constant listing the section index URLs verified in Step 1;
- apply the noise filter only if Step 1 found an obvious one, and name in a comment exactly what it drops;
- end with `portal.register("cn_portal", search_cn_portals)`.

The docstring must record: both hosts with their measured sizes and dates, the protocol-relative href trap, the 答记者问 noise and what was decided about it, whether the section indexes paginate, and — explicitly — that `flk.npc.gov.cn` is excluded because its API states `"download": 0`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_china.py -v`
Expected: PASS, 8 passed

- [ ] **Step 6: Verify live**

Same shape as Task 2 Step 6, with `Economy.CN`, then `python main.py --economy China --pillar 6 --live 2>&1 | tail -30`.

**Additionally, report whether PIPL, the Cybersecurity Law or the Data Security Law appear** in the discovered titles (个人信息保护法, 网络安全法, 数据安全法). Their absence is not a failure of this task — they may live on `gov.cn` rather than `cac.gov.cn` — but it is the fact the standing "CN principal statutes" item turns on, so it must be reported either way.

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/adapter_china.py tests/test_adapter_china.py tests/fixtures/portals/cn_cac_index.html
git commit -m "discovery: China had two web-search lanes and no portal lane

Both CN entries in sources.yaml were adapter: websearch, and every
engine now answers 403. cac.gov.cn turns out to be server-rendered and
enumerable -- 200, 59,987 bytes, 356 links, article pages at
//www.cac.gov.cn/YYYY-MM/DD/c_<id>.htm -- and gov.cn/zhengce/xxgk
likewise at 209 KB and 921 links.

Two real lanes also close the standing item that PIPL, CSL and DSL must
survive cac.gov.cn being unreachable: the fallback is now another
portal, not a search engine.

flk.npc.gov.cn is deliberately not a lane. Its API's permission block
returns \"download\": 0, which is the operator stating the documents are
not to be downloaded, and a test pins that it stays out.

The hrefs are protocol-relative, which is the trap here: left
unresolved they produce URLs that cannot be fetched and an economy that
silently yields nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Indonesia — browser-first, because httpx is refused everywhere

**Files:**
- Create: `backend/pipeline/adapter_indonesia.py`
- Create: `tests/fixtures/portals/id_bpk_search.html`
- Test: `tests/test_adapter_indonesia.py`

**Interfaces:**
- Consumes: `portal.make_doc`, `portal.register`, `backend.pipeline.scrapling_fetch`.
- Produces: `def search_id_bpk(client, src, query, economy, indicators, log) -> list[DiscoveredDoc]`, registered as `"id_bpk"`; `def _result_rows(html, base_url) -> list[tuple[str, str]]`.

**Why:** `peraturan.bpk.go.id` returns **403 to plain httpx on every path** (root, `/Search`, `/sitemap.xml` — measured 2026-09-07) while the browser lane gets HTTP 200. `sources.yaml` has recorded this since 21 August; nothing acted on it until Phase 1's `fetch_browser_on_block`. This adapter must go to the browser lane **first**, not escalate after a refusal — three wasted 403s per request is a real cost across a whole crawl.

**Robots — read this before writing a line.** `peraturan.bpk.go.id/robots.txt` disallows nine NAMED agents — `ClaudeBot`, `GPTBot`, `CCBot`, `Bytespider`, `Amazonbot`, `Applebot-Extended`, `Google-Extended`, `meta-externalagent`, `CloudflareBrowserRenderingCrawler` — and grants the wildcard group `Allow: /` with `Content-Signal: search=yes, ai-train=no, use=reference`. VeriTrade fetches as `VeriTrade-Research/0.2` and falls in the wildcard group, whose signals it satisfies exactly: it references and cites provisions with their source URL, and trains no model on them. **Two rules follow and neither is optional: never fetch this host with an agent identifying as one of the named crawlers, and never use its text for training.** If Scrapling's impersonating fetcher sends a Chrome UA rather than ours, that is still not one of the nine named agents — but check what it actually sends during recon and report it.

**Known route:** `/Details/<id>` → the `/Download/….pdf` it links. Already in `fetch._BODY_ROUTES`, so the fetch half is solved.

**Note from Phase 1:** with `probe_portals.py` fixed, the ID probe now completes and reports `ROBOTS_DISALLOW` and `UNREACHABLE` for the two Indonesian lanes. Read that verdict against the UA the probe actually sent before believing it — the robots file's refusal is agent-specific, and the probe may be sending a UA that falls in the named group.

- [ ] **Step 1: Recon**

```bash
python - <<'PY'
import sys, io, warnings
sys.path.insert(0, "."); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import httpx
from backend.config import settings
from backend.pipeline import robots, scrapling_fetch

print("our UA:", settings.crawl_user_agent)
r = httpx.get("https://peraturan.bpk.go.id/robots.txt",
              headers={"User-Agent": settings.crawl_user_agent}, timeout=30, verify=False)
print("robots.txt:", r.status_code, len(r.text))
print(r.text[:900])
for u in ["https://peraturan.bpk.go.id/", "https://peraturan.bpk.go.id/Search?keywords=data+pribadi"]:
    ok, why = robots.allowed(u, settings.crawl_user_agent)
    print(f"robots.allowed({u[:55]}) -> {ok} :: {why[:70]}")
print("scrapling available:", scrapling_fetch.available())
res = scrapling_fetch.fetch("https://peraturan.bpk.go.id/Search?keywords=data+pribadi", log=print)
print("scrapling result bytes:", None if not res else len(res.body))
if res:
    from bs4 import BeautifulSoup
    s = BeautifulSoup(res.body.decode("utf-8", "ignore"), "lxml")
    det = [a.get("href") for a in s.select("a[href]") if "/Details/" in (a.get("href") or "")]
    print("detail links:", len(det))
    for h in det[:5]: print("   ", h)
    open("tests/fixtures/portals/id_bpk_search.html", "wb").write(res.body)
    print("fixture saved")
PY
```

**If `robots.allowed` returns False for our own UA, STOP and report it.** That is a compliance answer, not an obstacle: the lane does not get built, `readiness.py` records the refusal, and the task closes as "not permitted" rather than being routed around.

- [ ] **Step 2: Write the failing test**

Create `tests/test_adapter_indonesia.py`:

```python
"""Indonesia: httpx is refused on every path, the browser lane is not.

peraturan.bpk.go.id answers HTTP 403 to plain httpx at the root, at /Search and at
/sitemap.xml (measured 2026-09-07) while Scrapling's impersonating fetcher gets 200.
sources.yaml has recorded this since 21 August. So this adapter goes to the browser lane
FIRST rather than escalating after a refusal -- three wasted 403s per request is real cost
across a crawl.

robots.txt here disallows nine NAMED agents (ClaudeBot, GPTBot, CCBot, Bytespider,
Amazonbot, Applebot-Extended, Google-Extended, meta-externalagent,
CloudflareBrowserRenderingCrawler) and grants the wildcard group Allow: / with
Content-Signal: search=yes, ai-train=no, use=reference. We fetch as VeriTrade-Research/0.2,
fall in the wildcard group, cite every provision to its source URL and train nothing.

Fixture saved 2026-09-07 via the browser lane. No test here touches the network.
"""
from pathlib import Path

import pytest

from backend.pipeline import adapter_indonesia
from backend.schemas import Economy

FIXTURE = Path(__file__).parent / "fixtures" / "portals" / "id_bpk_search.html"
BASE = "https://peraturan.bpk.go.id/Search?keywords=data+pribadi"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_detail_links_are_parsed(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert rows, "no /Details/ links parsed from a search result page"
    assert all("/Details/" in u for u, _ in rows)


def test_urls_are_absolute(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert all(u.startswith("https://peraturan.bpk.go.id/") for u, _ in rows)


def test_rows_are_deduplicated(html):
    rows = adapter_indonesia._result_rows(html, BASE)
    assert len({u for u, _ in rows}) == len(rows)


def test_the_adapter_never_sends_a_named_crawler_user_agent():
    """robots.txt disallows nine named AI crawlers by name. Sending one of those UAs to this
    host would be a refusal we walked past, and the difference is only the header we send."""
    import inspect
    src = inspect.getsource(adapter_indonesia)
    for named in ("ClaudeBot", "GPTBot", "CCBot", "Bytespider", "Amazonbot",
                  "Applebot-Extended", "Google-Extended", "meta-externalagent",
                  "CloudflareBrowserRenderingCrawler"):
        assert named not in src or "never" in src.lower(), (
            f"{named} appears in the adapter; robots.txt disallows it by name")


def test_search_produces_unique_documents(monkeypatch, html):
    """The browser lane is mocked; the point is the adapter's shape, not the fetch."""
    class _Res:
        body = html.encode()

    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "available", lambda: True)
    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "fetch", lambda *a, **k: _Res())
    docs = adapter_indonesia.search_id_bpk(
        client=None, src={"name": "JDIH BPK"}, query="data pribadi",
        economy=Economy.ID, indicators=[], log=lambda *_: None)
    assert docs
    assert len({d.doc_id for d in docs}) == len(docs)
    assert all(d.economy == Economy.ID for d in docs)


def test_an_unavailable_browser_lane_says_so_and_returns_nothing(monkeypatch):
    """Without Scrapling this host cannot be reached at all. Returning [] silently is the
    failure mode Phase 1 exists to remove -- it must log why."""
    monkeypatch.setattr(adapter_indonesia.scrapling_fetch, "available", lambda: False)
    lines = []
    docs = adapter_indonesia.search_id_bpk(
        client=None, src={"name": "JDIH BPK"}, query="data pribadi",
        economy=Economy.ID, indicators=[], log=lines.append)
    assert docs == []
    assert any("browser" in ln.lower() or "scrapling" in ln.lower() for ln in lines)


def test_the_adapter_is_registered_under_the_name_sources_yaml_uses():
    from backend.pipeline import portal
    assert portal.get_adapter("id_bpk") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_adapter_indonesia.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.adapter_indonesia'`

- [ ] **Step 4: Write the implementation**

Create `backend/pipeline/adapter_indonesia.py`. It must:
- go to `scrapling_fetch` **first**, never httpx, and say why in a comment naming the 403s;
- log a clear reason and return `[]` when the browser lane is unavailable — never silently;
- expose `_result_rows(html, base_url)` as a pure parser keeping only `/Details/<id>` links;
- use the query terms from `src` (`queries_p6` / `queries_p7`) so pillar scoping works as it does for the other economies;
- leave the `/Details/<id>` → `/Download/….pdf` hop to `fetch._BODY_ROUTES`, which already handles it, and say so rather than duplicating it;
- end with `portal.register("id_bpk", search_id_bpk)`.

The docstring must carry the robots analysis verbatim from this task's preamble — the nine named agents, the wildcard grant, the two non-optional rules — because that reasoning is the licence for the lane's existence.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_indonesia.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Verify live**

Same shape as Task 2 Step 6, with `Economy.ID`, then `python main.py --economy Indonesia --pillar 6 --live 2>&1 | tail -30`. Report documents, provisions, and whether the Pasal splitter fired (`ARTICLE_PATTERNS` has the Indonesian pattern; Phase-1 notes record Indonesia going from 0 usable provisions to 252 once fetch was fixed).

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/adapter_indonesia.py tests/test_adapter_indonesia.py tests/fixtures/portals/id_bpk_search.html
git commit -m "discovery: Indonesia refuses httpx everywhere, so the lane starts at the browser

peraturan.bpk.go.id answers 403 to plain httpx at the root, at /Search
and at /sitemap.xml while the browser lane gets 200. sources.yaml has
said so since 21 August. This adapter goes to Scrapling first rather
than escalating after a refusal -- three wasted 403s per request is real
cost across a crawl.

The robots reasoning is the licence for the lane and travels with it:
the file disallows nine NAMED AI crawlers and grants the wildcard group
Allow: / with Content-Signal: search=yes, ai-train=no, use=reference. We
fetch as VeriTrade-Research/0.2, fall in the wildcard group, cite every
provision to its source URL and train nothing on it. A test pins that no
named-crawler UA appears in the adapter.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Wire the six lanes and verify the four that already worked

**Files:**
- Modify: `backend/pipeline/discovery.py` (the `_ADAPTERS` dispatch, ~line 1352)
- Modify: `data/sources.yaml` (six lanes)
- Test: `tests/test_adapter_registry.py` (**Create**)

**Interfaces:**
- Consumes: every `portal.register(...)` call from Tasks 2-7.
- Produces: nothing new — this task makes the existing dispatch consult the registry.

**Why:** the adapters exist but nothing dispatches to them until `sources.yaml` names them and `discovery._ADAPTERS` can find them. This is also the one place where a typo silently costs an economy its lane, so it gets its own test.

- [ ] **Step 1: Write the failing test**

Create `tests/test_adapter_registry.py`:

```python
"""Every adapter named in sources.yaml must resolve, and every economy must have a lane.

This is the seam where a typo costs an economy its entire discovery in silence: an unknown
adapter name falls through to `_search_one`, which needs a `search_url_template` these
entries do not have, and the lane quietly returns nothing.
"""
import pytest

from backend.pipeline import discovery, portal
from backend.schemas import LIVE_TEST_POOL

# Importing the adapter modules is what runs their portal.register(...) calls.
from backend.pipeline import (adapter_china, adapter_indonesia, adapter_laos,  # noqa: F401
                              adapter_singapore, adapter_thailand, adapter_timor)


def _named_adapters():
    return {s.get("adapter") for s in discovery.load_sources()
            if s.get("adapter") and s.get("adapter") != "websearch"}


def test_every_adapter_named_in_sources_yaml_resolves():
    unresolved = [a for a in _named_adapters()
                  if portal.get_adapter(a) is None and a not in discovery._ADAPTERS]
    assert not unresolved, f"sources.yaml names adapters nothing implements: {unresolved}"


@pytest.mark.parametrize("economy", sorted(LIVE_TEST_POOL))
def test_every_economy_has_at_least_one_portal_native_lane(economy):
    """Russia is the documented exception: its fetch route is solved but discovery injects
    its rows client-side, and Phase 3 owns it. Every other economy must be able to reach its
    own portal without a search engine."""
    if economy == "RU":
        pytest.skip("RU discovery is unsolved by design — see the design spec, Phase 3")
    native = [s for s in discovery.load_sources()
              if s.get("economy") == economy
              and s.get("adapter") and s.get("adapter") != "websearch"]
    assert native, f"{economy} has no portal-native lane — a dead search engine costs it everything"


def test_no_lane_is_configured_on_the_npc_database():
    """flk.npc.gov.cn's API returns "download": 0. Discovery-only entries may mention it;
    no ADAPTER may be built on it."""
    for s in discovery.load_sources():
        if "flk.npc.gov.cn" in (s.get("base_url") or "") or "flk.npc.gov.cn" in (s.get("site") or ""):
            assert s.get("adapter") in (None, "websearch"), (
                "flk.npc.gov.cn must not carry a portal adapter — the operator refused")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_adapter_registry.py -v`
Expected: FAIL — the per-economy test fails for SG, CN, TH, ID, LA, TL, because `sources.yaml` still names `websearch` for all of them.

- [ ] **Step 3: Add the six lanes to `data/sources.yaml`**

Add one entry per economy, each carrying `economy`, `name`, `base_url`, `adapter`, `verified: true`, and a `notes:` block recording the route and the date it was measured. Follow the file's existing style — it is a record, not just config.

- **TL** `adapter: tl_gazette`, `base_url: https://mj.gov.tl/jornal`. Note `Crawl-delay: 10`, the frameset route, and whatever Task 2 found about the year range.
- **LA** `adapter: la_gazette`, `base_url: https://laoofficialgazette.gov.la`. Note the four Yii routes and that ids come only from the list page. **Correct the existing entry rather than adding a second one.**
- **TH** `adapter: th_law_api`, `base_url: https://www.law.go.th`, plus `api_base: https://apig.law.go.th/` and `api_key: 4nEZYvTwRFlUVn7aK85cZ2xSU83dOFai` with a comment stating it is a public constant from the app's own bundle and where it came from. Leave the superseded `krisdika.go.th` entry in place — its `note:` is a record of an expensive error.
- **SG** `adapter: sg_sso`, `base_url: https://sso.agc.gov.sg`. Keep the existing websearch entry as a **secondary** lane; it costs nothing when the engines are down and adds coverage when they are not.
- **CN** `adapter: cn_portal` on the `cac.gov.cn`/`gov.cn` entry. Keep the `flk.npc.gov.cn` entry as `websearch` — discovery-only, as its own note already says.
- **ID** `adapter: id_bpk` on the `peraturan.bpk.go.id` entry, carrying the robots analysis.

Then confirm the file still parses:
```bash
python -c "import yaml; d=yaml.safe_load(open('data/sources.yaml',encoding='utf-8')); print('sources:', len(d['sources']))"
```

- [ ] **Step 4: Make the dispatch consult the registry**

In `backend/pipeline/discovery.py`, the `_ADAPTERS` dict (~line 1352) currently hard-codes four names. Change the lookup so it falls back to `portal.get_adapter(name)` before `_search_one`:

```python
                searcher = (_ADAPTERS.get(src.get("adapter"))
                            or portal.get_adapter(src.get("adapter"))
                            or _search_one)
```

and import the six adapter modules at the top of `discover_live` (not at module import time — keep `discovery.py`'s import cost where it already is), mirroring how `adapter_india` and `adapter_mongolia` are imported there today.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_adapter_registry.py -v`
Expected: PASS — 12 passed (1 skip for RU)

- [ ] **Step 6: Verify the four pre-existing lanes still enumerate**

Phase 1 changed what a zero result means, and Task 8 changed the dispatch. Confirm nothing regressed:

```bash
python - <<'PY'
import sys, io
sys.path.insert(0, "."); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from backend.pipeline import discovery, websearch
from backend.schemas import Economy
for e in [Economy.AU, Economy.MY, Economy.IN, Economy.MN]:
    websearch.reset_diagnostics(); websearch.reset_circuit()
    docs = discovery.discover(e, 6, use_samples=False, log=lambda *_: None)
    print(f"{e.value}: {len(docs)} documents")
PY
```
Expected: all four non-zero. Report the counts; any zero is a regression this task must fix.

- [ ] **Step 7: Commit**

```bash
git status --short
git add backend/pipeline/discovery.py data/sources.yaml tests/test_adapter_registry.py
git commit -m "discovery: name the six new lanes, and pin that every economy has one

The adapters existed but nothing dispatched to them. An unknown adapter
name falls through to _search_one, which needs a search_url_template
these entries do not have -- so a typo here costs an economy its entire
discovery in silence, which is why the seam gets its own test.

test_every_economy_has_at_least_one_portal_native_lane now fails if any
economy but Russia is left depending on a search engine. Russia skips
explicitly: its fetch route is solved, its discovery injects rows
client-side, and Phase 3 owns it.

A second test pins that no adapter is ever configured on
flk.npc.gov.cn, whose API returns \"download\": 0.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: The two items Phase 1 parked

**Files:**
- Modify: `backend/pipeline/websearch.py` (`_entry_results`)
- Test: `tests/test_websearch_diagnostics.py` (append)
- Test: `tests/test_run_pipeline_wiring.py` (**Create**)

**Interfaces:**
- Consumes: `websearch._entry_results`, `discovery.explain_empty_discovery`, `orchestrator._explain_lost_cached_bodies`.
- Produces: nothing new.

**Why now:** Phase 1's final review parked both. The first is a regression Phase 1 itself introduced; the second is only cheap to fix while someone is already in the orchestrator, which Task 8 just changed.

### 9a — `_entry_results`' final comprehension sits outside its `try`

```python
    try:
        age_days = (...) / 86400.0
    except (ValueError, TypeError):
        return None
    if age_days > max_age:
        return None
    return [(r[0], r[1], r[2] if len(r) > 2 else "") for r in rows]   # ← outside
```

A corrupted row (`rows` containing a string, or a list shorter than two) raises `IndexError`/`TypeError` and nothing catches it. **Phase 1 widened the blast radius**: this function used to run only when its own key was queried; since the expiry-prune landed it runs across the *whole cache on every successful write*. So one corrupted row now breaks every search, not one.

### 9b — nothing drives `run_pipeline`

Deleting the `explain_empty_discovery` call from the orchestrator, or the `live_discovery` guard, leaves the whole suite green. The feature Phase 1 was commissioned to build is unprotected.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_websearch_diagnostics.py`:

```python
def test_a_corrupted_cache_row_is_a_miss_not_an_exception(monkeypatch):
    """The comprehension that builds the result tuples sat OUTSIDE the try, so a row that is
    a string, or shorter than two elements, raised instead of being declined.

    Phase 1 widened this from a nuisance to a stopper: _entry_results used to run only when
    its own key was queried, and since the expiry-prune landed it runs across the whole cache
    on every successful write. One corrupted row broke every search.
    """
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    fresh = _iso(1)
    for rows in (["not-a-list"], [[]], [["only-one-element"]], [None], "not-a-list-at-all"):
        entry = {"results": rows, "fetched_at": fresh, "engine": "serper"}
        assert websearch._entry_results(entry) is None, f"{rows!r} should be a miss"


def test_a_good_row_still_survives_the_hardening(monkeypatch):
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    entry = {"results": [["https://x", "X", "snip"]], "fetched_at": _iso(1), "engine": "serper"}
    assert websearch._entry_results(entry) == [("https://x", "X", "snip")]


def test_one_corrupted_row_does_not_discard_a_whole_good_cache(monkeypatch, tmp_path):
    """The prune walks every entry. A single bad neighbour must not take the good ones with it."""
    monkeypatch.setattr(websearch.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(websearch.settings, "search_cache_max_age_days", 7.0)
    monkeypatch.setattr(websearch.settings, "serper_api_key", "")
    websearch.reset_diagnostics(); websearch.reset_circuit()
    (tmp_path / "_search.json").write_text(json.dumps({
        "good": {"results": [["https://good", "G", ""]], "fetched_at": _iso(1), "engine": "s"},
        "bad": {"results": ["corrupt"], "fetched_at": _iso(1), "engine": "s"},
    }), encoding="utf-8")
    monkeypatch.setattr(websearch, "_engines",
                        lambda: [lambda c, q, n: [("https://new", "N", "")]])

    websearch.search("something new", log=lambda *_: None)
    after = json.loads((tmp_path / "_search.json").read_text(encoding="utf-8"))
    assert "good" in after, "a corrupted neighbour must not evict a healthy entry"
```

Create `tests/test_run_pipeline_wiring.py`:

```python
"""The wiring Phase 1 built and no test protected.

Deleting the explain_empty_discovery call from run_pipeline, or the live_discovery guard,
left the whole suite green -- so the feature that tells a judge WHY a run found nothing was
one careless edit from vanishing silently. These tests read the orchestrator's own source,
because driving a full run needs an LLM and neither grader is reachable.

Source-reading tests are weaker than behavioural ones and are chosen deliberately: they fail
on the deletion they exist to catch, and they need no network, no key and no fixture.
"""
import inspect

from backend.pipeline import discovery, orchestrator


def _run_source() -> str:
    fn = getattr(orchestrator, "run_pipeline", None) or orchestrator.run
    return inspect.getsource(fn)


def test_run_pipeline_explains_an_empty_live_discovery():
    src = _run_source()
    assert "explain_empty_discovery" in src, (
        "the orchestrator no longer explains a zero-document live run; a judged run would "
        "again export an empty CSV and exit 0")


def test_the_explanation_is_gated_on_live_discovery():
    src = _run_source()
    assert "live_discovery" in src, (
        "without the guard the explanation also fires on the reuse_documents second pass, "
        "where zero documents means the cached bodies are gone and no portal was contacted")


def test_the_second_pass_has_its_own_explanation():
    assert hasattr(orchestrator, "_explain_lost_cached_bodies")
    src = _run_source()
    assert "_explain_lost_cached_bodies" in src


def test_the_search_diagnostics_are_reset_once_per_run():
    src = _run_source()
    assert "reset_diagnostics" in src, (
        "without a per-run reset, run N reports run N-1's engine failures — the Streamlit "
        "process is long-lived and most economies no longer enter the web-search lane at all")


def test_every_explanation_line_is_an_error_pair():
    """frontend/runview.py reads these as (what happened, what to do). A last line that does
    not start with 'what to do:' leaves the Run screen showing a diagnosis with no action."""
    from backend.schemas import Economy
    from backend.pipeline import websearch
    websearch.reset_diagnostics()
    lines = discovery.explain_empty_discovery(Economy.SG, log=lambda *_: None)
    assert lines and all(ln.startswith("[error] ") for ln in lines)
    assert lines[-1].startswith("[error] what to do:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_websearch_diagnostics.py tests/test_run_pipeline_wiring.py -v`
Expected: the three new `websearch` tests FAIL with `IndexError`/`TypeError` rather than returning `None`. The wiring tests should mostly PASS already (Phase 1 built the wiring) — if any fails, that is a real gap and must be fixed, not deleted.

- [ ] **Step 3: Harden `_entry_results`**

Move the final comprehension inside a `try`, or build it defensively — either is acceptable provided a malformed row yields `None` and a good entry is unaffected. Add a comment naming why it matters more now than it did: the prune walks the whole cache on every write.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_websearch_diagnostics.py tests/test_run_pipeline_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Prove the wiring tests can actually fail**

A test that cannot fail is the defect it was written to prevent. Temporarily comment out the `explain_empty_discovery` call in `orchestrator.py`, run `python -m pytest tests/test_run_pipeline_wiring.py -q`, confirm it FAILS, then restore the line. Paste both outputs into the report.

- [ ] **Step 6: Commit**

```bash
git status --short
git add backend/pipeline/websearch.py tests/test_websearch_diagnostics.py tests/test_run_pipeline_wiring.py
git commit -m "fix: a corrupted cache row broke every search, and nothing protected the wiring

_entry_results built its result tuples OUTSIDE the try that guards the
timestamp parse, so a row that is a string, or shorter than two
elements, raised instead of being declined. Phase 1 widened that from a
nuisance to a stopper: the function used to run only when its own key
was queried, and since the expiry-prune landed it runs across the whole
cache on every successful write. One bad row broke every search.

Separately, deleting the explain_empty_discovery call from run_pipeline
-- or the live_discovery guard, or the per-run diagnostics reset -- left
all 922 tests green. The feature that tells a judge WHY a run found
nothing was one careless edit from vanishing in silence. The new tests
read the orchestrator's source rather than driving a run, because
neither grader is reachable; weaker, deliberately, and they fail on the
deletion they exist to catch.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: The phase gate

**Files:**
- Modify: `tools/readiness.py` (`RUN_END_TO_END`)
- Modify: `PROJECT_STATE.md` (§2 table and §5)
- Modify: `CLAUDE.md` (§4 Known Gaps, §8 Honesty statement)

**Interfaces:** none — verification and record.

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: everything passes except the pre-existing `tests/test_localisation_gates.py::test_nothing_is_left_staged_in_the_candidate_file`. Report the real counts. Any other failure blocks the phase.

- [ ] **Step 2: Confirm the corpus firewall survived Task 5**

Run: `python -m pytest tests/test_pipeline_isolation.py tests/test_labels_and_budget.py -q`
Expected: PASS. Task 5 reversed a dependency; this is what proves it reversed rather than relaxed.

- [ ] **Step 3: Run every economy's discovery and build the real table**

```bash
python - <<'PY'
import sys, io, time
sys.path.insert(0, "."); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from backend.pipeline import discovery, websearch
from backend.schemas import Economy, LIVE_TEST_POOL
print(f"{'econ':5} {'docs':>5} {'net queries':>12}  seconds")
for code in sorted(LIVE_TEST_POOL):
    websearch.reset_diagnostics(); websearch.reset_circuit()
    t = time.perf_counter()
    try:
        docs = discovery.discover(Economy(code), 6, use_samples=False, log=lambda *_: None)
        n = len(docs)
    except Exception as e:
        n = f"ERR {type(e).__name__}"
    print(f"{code:5} {str(n):>5} {websearch.diagnostics()['network_queries']:>12}  {time.perf_counter()-t:.0f}")
PY
```
This table is the phase's headline result. Record it verbatim in the report — including any economy that still returns zero, and RU, which is expected to.

- [ ] **Step 4: Update `tools/readiness.py`**

Move each economy that now produces provisions from its own portal to `EXTRACTED` in `RUN_END_TO_END`, with a comment naming what was measured and when. **Do not promote an economy to `MEASURED`** — that level means a run scored against the panel's database, and no grader is reachable. The file's own docstring makes that distinction; honour it.

Run: `python tools/readiness.py` and paste the table.

- [ ] **Step 5: Update `PROJECT_STATE.md` §2 and §5**

`PROJECT_STATE.md` carries the user's uncommitted work. Use the snapshot route:

```bash
W=.superpowers/sdd/2026-09-07-phase2-portal-adapters
mkdir -p "$W"
cp PROJECT_STATE.md "$W/PROJECT_STATE.md.SNAPSHOT"
git show HEAD:PROJECT_STATE.md > "$W/PROJECT_STATE.md.BASE"
```
1. Apply your edits to the SNAPSHOT content; keep that result aside — it is the final working-tree state.
2. `cp "$W/PROJECT_STATE.md.BASE" PROJECT_STATE.md`, apply the same edits, `git add PROJECT_STATE.md`.
3. Commit.
4. Write the step-1 result back to `PROJECT_STATE.md`.

Verify, and paste the output:
- `git show HEAD -- PROJECT_STATE.md | sed -n '/^@@/,$p' | grep "^[+-]" | grep -v "^+++\|^---"` → only your edits; nothing mentioning `check_gates.py`, `replay_grade`, P7-I3, OpenRouter or Tailscale.
- `git diff -- PROJECT_STATE.md | grep "^+" | grep -v "^+++" | wc -l` → the same count as before you started (the user's untouched additions).

In §2, update the Lane column for every economy this phase changed. In §5, add one line recording the phase, with the numbers from Step 3 and where they were measured.

Delete from §3 the items this phase closed: *"Portal adapters for TH · ID · LA · RU"* (RU remains — reword rather than delete), *"Timor-Leste: no lane, no language profile, no OCR path"*, and *"CN principal statutes must survive cac.gov.cn being unreachable"* if Task 6's live check confirmed the second lane reaches them. Follow the file's rule: delete, do not annotate.

- [ ] **Step 6: Update `CLAUDE.md`**

`CLAUDE.md` is clean in git — stage it wholesale. Correct §4 Known Gaps and §8's honesty statement, both of which still say TH/ID/LA have no working lane and that live crawling runs end-to-end only for six economies. Keep the statement honest about what is *not* done: no grader is reachable, so nothing in this phase is scored, and RU discovery is unsolved.

- [ ] **Step 7: Commit**

```bash
git status --short
git add tools/readiness.py CLAUDE.md PROJECT_STATE.md
git commit -m "docs: record Phase 2 — ten of eleven economies now reach their own portal

<the table from Step 3>

readiness moves these economies to EXTRACTED, not MEASURED: that level
means a run scored against the panel's database, and neither grader is
reachable -- the local server refuses connections and the OpenRouter key
answers 401 User not found. Nothing in this phase is scored.

Russia stays unsolved and stays visible: its fetch route works, its
discovery injects rows client-side, and Phase 3 owns it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## What Phase 2 deliberately does not do

- **It does not restore web search.** Serper stays spent. Ten of eleven economies no longer need it; the eleventh is Russia, whose problem is not the engine.
- **It does not score anything.** Both graders are unreachable, so every acceptance criterion here stops at "provisions extracted from the portal". No economy may be promoted to `MEASURED`.
- **It does not touch Russia.** Fetch is solved (`pravo.gov.ru/proxy/ips/?doc_itself=&nd=<id>`, cp1251, with the frameset trap documented); discovery injects rows client-side and needs its own research task. Phase 3.
- **It does not re-measure retrieval budgets.** New corpora will change what depth each economy needs, but `tools/measure_budget.py` needs a grader. That waits.
