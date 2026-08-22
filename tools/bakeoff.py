"""Measure candidate grading models against the frozen benchmark, and price them.

Two engines get declared on the Word submission and cannot be changed afterwards, so the
choice has to be a measurement. This runs each candidate over
`data/benchmarks/grader_bakeoff.json` — the panel's own answer key joined to our extracted
provision text — using the PRODUCTION prompt from `pipeline/mapping.py`. Measuring a different
prompt would measure a system we do not ship.

What is reported, and why each column earns its place:

    F1          the headline. Accuracy alone is misleading here: the set is 3:1 negative, so a
                model that refuses everything scores 75% and finds nothing.
    recall      of the panel's own answers, how many did this model accept? A miss is a row
                absent from the submission, which is the expensive direction.
    precision   of what it accepted, how much was right? Low precision means a reviewer has to
                read every row, which is the cost the tool exists to remove.
    $/1k calls  from ACTUAL token usage returned by the API, not from an assumed prompt size.
    s/call      wall-clock. The live test allows sixty minutes in total.

Cost-efficiency is explicitly a scored plus, so the summary ranks by F1 per dollar as well as
by F1 — a model 1% better for 15x the money is not the better choice here.

    python tools/bakeoff.py --list                       # candidates and their catalogue prices
    python tools/bakeoff.py --models a,b,c               # run those
    python tools/bakeoff.py --models a,b --limit 40      # a cheap smoke pass first
    python tools/bakeoff.py --report                     # re-print saved results
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ROOT, settings                          # noqa: E402
from backend.pipeline.mapping import SYSTEM, _user_prompt          # noqa: E402
from backend.rdtii import get_indicator                            # noqa: E402
from backend.schemas import DiscoveryTag, Economy, OCRMetrics, Provision   # noqa: E402

BENCH = ROOT / "data" / "benchmarks" / "grader_bakeoff.json"
RESULTS = ROOT / "data" / "benchmarks" / "bakeoff_results.json"
API = "https://openrouter.ai/api/v1/chat/completions"

#: Candidates, and why each is on the list. Engine A must be a commercial hosted model and
#: Engine B open weights — but note the template asks "Local or hosted API" as a separate
#: field, so an OPEN-WEIGHTS model served through OpenRouter still qualifies as Engine B. That
#: matters: it means Engine B needs no GPU of ours, and can be measured on the same footing.
CANDIDATES = {
    # id: (kind, one-line reason for being tested)
    "deepseek/deepseek-v4-flash":      ("open",   "current default; reasoning model, ~4-5k thinking tokens"),
    "openai/gpt-oss-120b":             ("open",   "open weights, cheapest strong candidate at $0.19/1k calls"),
    "openai/gpt-oss-20b":              ("open",   "open weights, small enough to self-host on one GPU"),
    "qwen/qwen3.7-flash":              ("open",   "open weights, strongest multilingual prior of the cheap tier"),
    "meta-llama/llama-3.3-70b-instruct": ("open", "open weights, the conservative well-understood baseline"),
    "mistralai/mistral-small-3.2-24b-instruct": ("open", "open weights, European, small"),
    "google/gemini-2.5-flash":         ("hosted", "hosted incumbent for the crosscheck lane"),
    "openai/gpt-4o-mini":              ("hosted", "hosted baseline everyone recognises"),
}


def _load_bench(limit: int | None) -> list[dict]:
    cases = json.loads(BENCH.read_text(encoding="utf-8"))["cases"]
    if limit:
        # Keep the positive/negative ratio and the language mix rather than taking a prefix,
        # or a smoke pass measures something different from the full run.
        pos = [c for c in cases if c["label"]][: max(1, limit // 4)]
        neg = [c for c in cases if not c["label"]][: limit - len(pos)]
        cases = pos + neg
    return cases


def _prompt_for(case: dict) -> tuple[str, str]:
    ind = get_indicator(case["indicator_id"])
    prov = Provision(
        provision_id=case["id"], doc_id="bench", economy=Economy(case["economy"]),
        law_name=case["law_name"], article_section=case["article_section"],
        verbatim_snippet=case["text"], source_url=case["source_url"] or "https://bench.test/x",
        discovery_tag=DiscoveryTag.KNOWN, ocr=OCRMetrics())
    return SYSTEM, _user_prompt(ind, prov)


def _call(model: str, system: str, user: str, timeout: int = 180) -> tuple[dict | None, dict, float]:
    """(parsed json, usage, seconds). Never raises — a failed call is a data point."""
    body = {
        "model": model, "temperature": 0,
        "max_tokens": settings.openrouter_max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {settings.openrouter_api_key}",
                 "HTTP-Referer": "https://veritrade.ftu.fyi", "X-Title": "VeriTrade bake-off"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, {"error": f"HTTP {exc.code}: {exc.read()[:200].decode('utf-8', 'replace')}"}, \
            time.time() - t0
    except Exception as exc:
        return None, {"error": f"{type(exc).__name__}: {exc}"}, time.time() - t0
    dt = time.time() - t0
    usage = payload.get("usage") or {}
    try:
        content = payload["choices"][0]["message"]["content"] or ""
    except Exception:
        return None, {**usage, "error": "no content"}, dt
    # Models wrap JSON in prose or fences often enough that this is not defensive coding, it is
    # the normal path; a parse failure counts as a wrong answer, never as a skipped case.
    text = content.strip()
    if "```" in text:
        text = text.split("```")[1].removeprefix("json").strip()
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1:
        return None, {**usage, "error": "unparseable"}, dt
    try:
        return json.loads(text[a:b + 1]), usage, dt
    except Exception:
        return None, {**usage, "error": "bad json"}, dt


def run_model(model: str, cases: list[dict], workers: int = 6) -> dict:
    def one(case: dict) -> dict:
        system, user = _prompt_for(case)
        parsed, usage, dt = _call(model, system, user)
        if parsed is None:
            # A model that cannot return parseable JSON is not usable, so this must count
            # against it rather than being filtered out of the denominator.
            predicted = False
        else:
            predicted = bool(parsed.get("satisfies_target")) and not parsed.get("better_sibling")
        return {"id": case["id"], "truth": case["label"], "pred": predicted,
                "seconds": dt, "error": usage.get("error"),
                "in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, cases))
    wall = time.time() - t0

    tp = sum(1 for r in rows if r["truth"] and r["pred"])
    fp = sum(1 for r in rows if not r["truth"] and r["pred"])
    fn = sum(1 for r in rows if r["truth"] and not r["pred"])
    tn = sum(1 for r in rows if not r["truth"] and not r["pred"])
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    errs = [r["error"] for r in rows if r["error"]]
    return {
        "model": model, "n": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
        "accuracy": round((tp + tn) / len(rows), 3) if rows else 0.0,
        "in_tokens": sum(r["in"] for r in rows), "out_tokens": sum(r["out"] for r in rows),
        "seconds_per_call": round(sum(x["seconds"] for x in rows) / max(len(rows), 1), 2),
        "wall_seconds": round(wall, 1),
        "errors": len(errs), "error_examples": errs[:3],
        "rows": rows,
    }


def catalogue() -> dict[str, dict]:
    req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                 headers={"User-Agent": "VeriTrade-Research/0.2"})
    return {m["id"]: m for m in json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]}


def price(result: dict, cat: dict) -> tuple[float, float]:
    """(total $ spent, $ per 1000 calls) from ACTUAL usage."""
    m = cat.get(result["model"])
    if not m:
        return 0.0, 0.0
    pin, pout = float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])
    total = result["in_tokens"] * pin + result["out_tokens"] * pout
    return total, (total / max(result["n"], 1)) * 1000


def report(results: list[dict]) -> str:
    cat = catalogue()
    rows = []
    for r in results:
        spent, per_k = price(r, cat)
        kind = CANDIDATES.get(r["model"], ("?", ""))[0]
        rows.append((r["f1"], r, spent, per_k, kind))
    rows.sort(key=lambda x: -x[0])
    out = [f"{'model':44} {'kind':6} {'F1':>5} {'prec':>5} {'rec':>5} "
           f"{'$/1k':>7} {'s/call':>6} {'err':>4}  F1/$",
           "-" * 104]
    for f1, r, spent, per_k, kind in rows:
        eff = (f1 / per_k) if per_k else 0.0
        out.append(f"{r['model']:44} {kind:6} {f1:5.3f} {r['precision']:5.3f} {r['recall']:5.3f} "
                   f"{per_k:7.3f} {r['seconds_per_call']:6.2f} {r['errors']:4}  {eff:6.1f}")
    total = sum(s for _, _, s, _, _ in rows)
    out.append("-" * 104)
    out.append(f"total spent this bake-off: ${total:.4f}")
    best_a = next((r for _, r, _, _, k in rows if k == "hosted"), None)
    best_b = next((r for _, r, _, _, k in rows if k == "open"), None)
    if best_a:
        out.append(f"best hosted     (Engine A candidate): {best_a['model']}  F1 {best_a['f1']}")
    if best_b:
        out.append(f"best open-weights (Engine B candidate): {best_b['model']}  F1 {best_b['f1']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", help="comma-separated ids; default = every candidate")
    ap.add_argument("--limit", type=int, help="use only N cases (smoke pass)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--list", action="store_true", help="show candidates and catalogue prices")
    ap.add_argument("--report", action="store_true", help="re-print saved results")
    args = ap.parse_args()

    if args.report:
        saved = json.loads(RESULTS.read_text(encoding="utf-8"))
        print(report(saved["results"]))
        return 0

    if args.list:
        cat = catalogue()
        print(f"{'model':44} {'kind':7} {'in $/M':>7} {'out $/M':>8}  why")
        for mid, (kind, why) in CANDIDATES.items():
            m = cat.get(mid)
            if not m:
                print(f"{mid:44} {kind:7} {'MISSING FROM CATALOGUE':>18}")
                continue
            pin, pout = float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])
            print(f"{mid:44} {kind:7} {pin*1e6:7.3f} {pout*1e6:8.3f}  {why}")
        return 0

    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    models = args.models.split(",") if args.models else list(CANDIDATES)
    cases = _load_bench(args.limit)
    print(f"benchmark: {len(cases)} cases "
          f"({sum(1 for c in cases if c['label'])} positive) · {len(models)} models\n")

    results = []
    for mid in models:
        print(f"  running {mid} …", flush=True)
        r = run_model(mid.strip(), cases, workers=args.workers)
        print(f"    F1 {r['f1']}  prec {r['precision']}  rec {r['recall']}  "
              f"{r['seconds_per_call']}s/call  {r['errors']} errors", flush=True)
        if r["error_examples"]:
            print(f"    e.g. {r['error_examples'][0][:120]}", flush=True)
        results.append(r)

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"cases": len(cases), "results": results},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + report(results))
    print(f"\nwritten -> {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
