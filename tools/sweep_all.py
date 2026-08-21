"""Run every economy × pillar end to end and record what happened.

This is not a benchmark in the "compare two versions" sense — the pipeline has never once been
run across all six economies for both pillars, so the first job is simply to find out where it
breaks. The numbers are a by-product; the failure list is the point.

It runs the REAL pipeline, including export, so a break anywhere in the chain shows up here
rather than in week five. Two modes:

    --llm mock    zero API cost. Exercises discovery, fetch, OCR, extraction, retrieval, the
                  mapping plumbing and the exporter. The mappings themselves are lexical and
                  not worth reading — this mode answers "does it hold together", not "is it right".

    --llm openrouter   real grading, real cost. Use on ONE economy to get the per-run US$ and
                  wall-clock figures the README has to report, not on all twelve combinations.

Every run is isolated: one economy-pillar failing is recorded and the sweep continues, because a
crash in Mongolia should not cost us the knowledge that India works.

    python tools/sweep_all.py --llm mock --live
    python tools/sweep_all.py --llm mock --live --economies Singapore Australia
    python tools/sweep_all.py --llm openrouter --live --economies India --pillars 6
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                       # noqa: E402
from backend.schemas import ECONOMY_UN_NAME                # noqa: E402

ALL_ECONOMIES = list(ECONOMY_UN_NAME.values())
OUT_DIR = Path(__file__).resolve().parent.parent / "logs" / "benchmark"


def run_one(economy: str, pillar: int, llm: str, live: bool, ocr: str | None) -> dict:
    """One economy-pillar, fully isolated — an exception becomes a recorded result."""
    from backend.pipeline.orchestrator import run_pipeline
    from backend.schemas import resolve_economy

    lines: list[str] = []
    started = time.perf_counter()
    rec: dict = {"economy": economy, "pillar": pillar, "llm": llm, "live": live}
    try:
        result = run_pipeline(
            resolve_economy(economy), [pillar], use_samples=not live,
            log=lines.append, llm_provider=llm, ocr_provider=ocr)
        mappings = result.mappings
        rec.update({
            "ok": True,
            "provisions_mapped": len(mappings),
            "rows_by_indicator": dict(Counter(m.indicator_id for m in mappings)),
            "laws": len({m.law_name for m in mappings}),
            "placeholder_rows": sum(1 for m in mappings if m.law_name == "No provision found"),
            "docs_discovered": getattr(result.meta, "docs_discovered", None),
            "run_id": getattr(result.meta, "run_id", None),
        })
    except Exception as exc:
        rec.update({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-1200:]})
    rec["elapsed_s"] = round(time.perf_counter() - started, 1)

    # The pipeline already narrates itself; keep the stage timings and anything that looks
    # like a failure, and drop the rest so the JSON stays readable.
    rec["timings"] = [l for l in lines if l.startswith("[timing]")]
    rec["warnings"] = [l for l in lines
                       if any(w in l.lower() for w in ("fail", "error", "skip", "empty",
                                                       "unavailable", "0 provisions"))][:25]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--economies", nargs="*", default=ALL_ECONOMIES)
    ap.add_argument("--pillars", nargs="*", type=int, default=[6, 7])
    ap.add_argument("--llm", default="mock")
    ap.add_argument("--ocr", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--tag", default="sweep")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{stamp}-{args.tag}-{args.llm}.json"

    report: dict = {
        "started_utc": stamp,
        "llm": args.llm, "live": args.live, "ocr": args.ocr or settings.ocr_provider,
        "machine": f"{platform.system()} {platform.machine()} · py{platform.python_version()}",
        "runs": [],
    }
    print(f"sweep: {len(args.economies)} economies x {len(args.pillars)} pillars "
          f"· llm={args.llm} · live={args.live}\n-> {out}\n")

    for economy in args.economies:
        for pillar in args.pillars:
            print(f"[{economy} P{pillar}] running…", flush=True)
            rec = run_one(economy, pillar, args.llm, args.live, args.ocr)
            report["runs"].append(rec)
            if rec["ok"]:
                print(f"[{economy} P{pillar}] OK — {rec['provisions_mapped']} rows, "
                      f"{rec['laws']} laws, {rec['elapsed_s']}s", flush=True)
            else:
                print(f"[{economy} P{pillar}] FAILED — {rec['error']}", flush=True)
            out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    ok = [r for r in report["runs"] if r["ok"]]
    report["summary"] = {
        "combinations": len(report["runs"]),
        "succeeded": len(ok),
        "failed": len(report["runs"]) - len(ok),
        "total_rows": sum(r.get("provisions_mapped", 0) for r in ok),
        "total_minutes": round(sum(r["elapsed_s"] for r in report["runs"]) / 60, 1),
    }
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'=' * 68}\n{report['summary']['succeeded']}/{report['summary']['combinations']} "
          f"combinations succeeded · {report['summary']['total_rows']} rows · "
          f"{report['summary']['total_minutes']} min")
    for r in report["runs"]:
        mark = "OK  " if r["ok"] else "FAIL"
        detail = (f"{r.get('provisions_mapped', 0):>4} rows, {r.get('laws', 0):>3} laws"
                  if r["ok"] else r["error"][:70])
        print(f"  {mark} {r['economy']:<12} P{r['pillar']}  {r['elapsed_s']:>7}s  {detail}")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
