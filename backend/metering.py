"""What a run actually cost, counted as it happens.

The final-round README requires a cost table per component — OCR, embedding, mapping per
engine, crawling — and states the condition plainly: *"Cost is also recorded per run and per
engine during the live hour, so make sure your logging produces it without manual arithmetic."*
Our previous figures were real but arrived at with a calculator, which is exactly what that
sentence rules out.

Every unit is already available at the moment it is spent; nothing here estimates anything:

    LLM         prompt_tokens / completion_tokens come back in every API response
    OCR         pages processed, and which engine processed them
    search      one billable query per call to a paid search API
    fetch       requests and bytes, so a bandwidth-priced deployment can be costed later
    embedding   sentences encoded — local, so $0, but the wall-clock is the real cost

Design notes worth knowing before extending it:

* **The meter is ambient, not threaded through every signature.** A module-level global holds
  the current run's meter, so a provider records against whichever run is active without the
  pipeline passing an extra argument down six layers. Outside a run the calls are no-ops, which
  keeps `tools/` scripts and the test suite free of setup. It is a global and not a `ContextVar`
  for a measured reason — see the comment on `_current`.
* **Recording is thread-safe.** Mapping runs sixteen calls concurrently.
* **Cost is derived, never stored.** Counters hold units; money is computed at report time from
  `data/pricing.json`. A price change then re-prices history instead of corrupting it, and a
  missing price yields `None` — reported as "unpriced", never as $0.00, because zero is a claim
  and silence is not.
* **Per engine, not just per run.** C5b compares two engines over the same work in the live
  hour, so the totals are keyed by the model that actually answered — which, after the 429 fix
  in `llm_openrouter`, is reliably the model we asked for.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from .config import ROOT

PRICES = ROOT / "data" / "pricing.json"

# A module GLOBAL, deliberately, not a ContextVar.
#
# The first version used a ContextVar and recorded nothing at all. Mapping runs sixteen calls
# through a ThreadPoolExecutor, and a worker thread starts with a FRESH context — so every
# provider recorded into a meter that the reporting thread could not see. The run then reported
# `total_usd: 0.0` with `total_is_complete: true`, which is the worst possible failure for a
# cost table: not an error, not a gap, a confident zero.
#
# A global is visible from every thread, and one process runs one pipeline at a time, so there
# is nothing for it to collide with. If concurrent runs in one process ever become real, this
# is the line to revisit — and `Meter._lock` already makes the counters themselves safe.
_current: "Meter | None" = None
_swap = threading.Lock()


@dataclass
class LLMUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    failures: int = 0


@dataclass
class OCRUsage:
    documents: int = 0
    pages: int = 0
    seconds: float = 0.0


@dataclass
class Meter:
    """Counters for one run. Units only — money is computed in `report()`."""

    run_id: str = ""
    started: float = field(default_factory=time.monotonic)
    llm: dict[str, LLMUsage] = field(default_factory=dict)      # model id -> usage
    ocr: dict[str, OCRUsage] = field(default_factory=dict)      # provider name -> usage
    search_queries: dict[str, int] = field(default_factory=dict)  # engine -> billable queries
    fetch_requests: int = 0
    fetch_bytes: int = 0
    embed_sentences: int = 0
    embed_seconds: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ── recording ────────────────────────────────────────────────────────────────────
    def record_llm(self, model: str, prompt_tokens: int, completion_tokens: int,
                   seconds: float = 0.0, failed: bool = False) -> None:
        with self._lock:
            u = self.llm.setdefault(model, LLMUsage())
            u.calls += 1
            u.prompt_tokens += int(prompt_tokens or 0)
            u.completion_tokens += int(completion_tokens or 0)
            u.seconds += seconds
            u.failures += int(failed)

    def record_ocr(self, provider: str, pages: int, seconds: float = 0.0) -> None:
        with self._lock:
            u = self.ocr.setdefault(provider, OCRUsage())
            u.documents += 1
            u.pages += int(pages or 0)
            u.seconds += seconds

    def record_search(self, engine: str, queries: int = 1) -> None:
        with self._lock:
            self.search_queries[engine] = self.search_queries.get(engine, 0) + queries

    def record_fetch(self, nbytes: int) -> None:
        with self._lock:
            self.fetch_requests += 1
            self.fetch_bytes += int(nbytes or 0)

    def record_embedding(self, sentences: int, seconds: float = 0.0) -> None:
        with self._lock:
            self.embed_sentences += int(sentences or 0)
            self.embed_seconds += seconds

    # ── reporting ────────────────────────────────────────────────────────────────────
    def report(self, prices: dict | None = None) -> dict:
        """Units and money, per component and per engine. `None` cost means UNPRICED."""
        p = prices if prices is not None else load_prices()
        llm_rows, llm_total, llm_unpriced = [], 0.0, False
        for model, u in sorted(self.llm.items()):
            rate = (p.get("llm") or {}).get(model)
            cost = None
            if rate:
                cost = (u.prompt_tokens * rate["input_per_1m"]
                        + u.completion_tokens * rate["output_per_1m"]) / 1_000_000
                llm_total += cost
            else:
                llm_unpriced = True
            llm_rows.append({"model": model, "calls": u.calls, "failures": u.failures,
                             "prompt_tokens": u.prompt_tokens,
                             "completion_tokens": u.completion_tokens,
                             "seconds": round(u.seconds, 1), "cost_usd": cost})

        ocr_rows, ocr_total, ocr_unpriced = [], 0.0, False
        for prov, u in sorted(self.ocr.items()):
            per_page = (p.get("ocr") or {}).get(prov)
            cost = None
            if per_page is not None:
                cost = u.pages * per_page
                ocr_total += cost
            else:
                ocr_unpriced = True
            ocr_rows.append({"provider": prov, "documents": u.documents, "pages": u.pages,
                             "seconds": round(u.seconds, 1), "cost_usd": cost})

        search_rows, search_total, search_unpriced = [], 0.0, False
        for engine, n in sorted(self.search_queries.items()):
            per_query = (p.get("search") or {}).get(engine)
            cost = None
            if per_query is not None:
                cost = n * per_query
                search_total += cost
            else:
                search_unpriced = True
            search_rows.append({"engine": engine, "queries": n, "cost_usd": cost})

        known = llm_total + ocr_total + search_total
        return {
            "run_id": self.run_id,
            "wall_seconds": round(time.monotonic() - self.started, 1),
            "llm": llm_rows,
            "ocr": ocr_rows,
            "search": search_rows,
            "fetch": {"requests": self.fetch_requests, "bytes": self.fetch_bytes,
                      "cost_usd": 0.0},          # bandwidth is not billed on our deployments
            "embedding": {"sentences": self.embed_sentences,
                          "seconds": round(self.embed_seconds, 1), "cost_usd": 0.0},
            "total_usd": round(known, 6),
            # An unpriced component means the total is a FLOOR, not the answer. Saying so is the
            # difference between a measured figure and one that merely looks measured.
            "total_is_complete": not (llm_unpriced or ocr_unpriced or search_unpriced),
            "unpriced": [c for c, flag in (("llm", llm_unpriced), ("ocr", ocr_unpriced),
                                           ("search", search_unpriced)) if flag],
        }

    def table(self) -> str:
        """The README's Measured Cost table, generated. Never hand-typed again."""
        r = self.report()
        lines = ["| Component | Engine used | Units | Measured cost |",
                 "| :--- | :--- | :--- | ---: |"]
        for row in r["ocr"]:
            lines.append(f"| OCR | {row['provider']} | {row['pages']} pages | "
                         f"{_money(row['cost_usd'])} |")
        lines.append(f"| Embedding | local | {r['embedding']['sentences']} sentences | $0.000 |")
        for row in r["llm"]:
            lines.append(f"| Mapping | {row['model']} | {row['calls']} calls, "
                         f"{row['prompt_tokens'] + row['completion_tokens']} tokens | "
                         f"{_money(row['cost_usd'])} |")
        for row in r["search"]:
            lines.append(f"| Crawling | {row['engine']} | {row['queries']} queries | "
                         f"{_money(row['cost_usd'])} |")
        lines.append(f"| Crawling | fetch | {r['fetch']['requests']} requests, "
                     f"{r['fetch']['bytes'] // 1000} KB | $0.000 |")
        total = _money(r["total_usd"])
        lines.append(f"| **Total** | | **{r['wall_seconds']:.0f}s wall-clock** | **{total}** |")
        if not r["total_is_complete"]:
            lines.append("")
            lines.append(f"> Incomplete: no price on file for {', '.join(r['unpriced'])}. "
                         f"The total above is a floor, not the full cost.")
        return "\n".join(lines)


def _money(v: float | None) -> str:
    return "unpriced" if v is None else f"${v:.4f}"


def load_prices() -> dict:
    try:
        return json.loads(PRICES.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── ambient access ───────────────────────────────────────────────────────────────────
def start(run_id: str = "") -> Meter:
    """Begin metering. Returns the meter so a caller can report on it afterwards."""
    global _current
    with _swap:
        _current = Meter(run_id=run_id)
        return _current


def stop() -> Meter | None:
    """End metering. Recording after this is a no-op again."""
    global _current
    with _swap:
        m, _current = _current, None
        return m


def current() -> Meter | None:
    return _current


def record_llm(model: str, prompt_tokens: int, completion_tokens: int,
               seconds: float = 0.0, failed: bool = False) -> None:
    m = _current
    if m is not None:
        m.record_llm(model, prompt_tokens, completion_tokens, seconds, failed)


def record_ocr(provider: str, pages: int, seconds: float = 0.0) -> None:
    m = _current
    if m is not None:
        m.record_ocr(provider, pages, seconds)


def record_search(engine: str, queries: int = 1) -> None:
    m = _current
    if m is not None:
        m.record_search(engine, queries)


def record_fetch(nbytes: int) -> None:
    m = _current
    if m is not None:
        m.record_fetch(nbytes)


def record_embedding(sentences: int, seconds: float = 0.0) -> None:
    m = _current
    if m is not None:
        m.record_embedding(sentences, seconds)
