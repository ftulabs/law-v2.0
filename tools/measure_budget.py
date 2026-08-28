"""Measure, per economy, how deep the retrieval shortlist has to go — and write the table.

    python tools/measure_budget.py                     # every economy with a built corpus
    python tools/measure_budget.py --economy SG MY     # just these
    python tools/measure_budget.py --ladder 40 80 150 300 450
    python tools/measure_budget.py --dry-run           # measure, print, write nothing

Why this exists: `retrieve_max_top_k=450` and `retrieve_fraction=0.05` were fitted to SG+AU+MY
TOGETHER, and the per-economy split shows the compromise. Singapore's cited provisions all
arrive by rank 40; Australia's need 300. A single constant therefore over-spends on one
economy to serve another, and on a 4,840-provision Singapore pillar-6 crawl that came to 968
LLM calls to fetch what sat in the top forty.

The rule this writes into data/retrieval_budget.json:

    cap = the SMALLEST k on the ladder at which BOTH provision-recall and law-recall reach
          the best value that economy ever reaches, times a safety margin, rounded up to the
          next ladder rung.  (See _derive: law recall has to be in the rule, or Malaysia gets
          capped at 40 and loses a cited Act from the shortlist altogether.)

The margin is not cosmetic. Recall here is measured against a handful of cited provisions per
economy (5-8), so the smallest passing k is an estimate from a small sample, and the failure
it protects against is asymmetric: spending too much costs money, spending too little costs a
row in the submission that nothing downstream can tell is missing.

An economy with no built corpus is SKIPPED, not defaulted to something optimistic — it keeps
the conservative shipped formula until someone measures it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ROOT, settings                  # noqa: E402
from backend.eval import harness                           # noqa: E402
from backend.eval.ground_truth import labelled_economies   # noqa: E402
from backend.pipeline.mapping import _diverse_shortlist    # noqa: E402

OUT = ROOT / "data" / "retrieval_budget.json"
LADDER = (40, 80, 150, 300, 450)
MARGIN = 1.5        # cap = smallest passing k x this, rounded up to the next ladder rung


def measure(econ: str, ladder: tuple[int, ...]) -> dict | None:
    provisions = harness.load_provisions(econ)
    if not provisions:
        print(f"  {econ}: no built corpus - skipped (keeps the conservative default)")
        return None
    curve = []
    for k in ladder:
        t0 = time.perf_counter()

        def sel(indicator_id, provs, k=k):
            return _diverse_shortlist(indicator_id, provs, k,
                                      settings.retrieve_per_law_k, log=lambda _m: None)

        rep = harness.evaluate(econ, sel, provisions)
        s = rep.summary()
        curve.append({"k": k, "prov_recall": s["prov_recall"], "law_recall": s["law_recall"],
                      "prov_hits": s["prov_hits"], "n_calls": s["n_calls"]})
        print(f"  {econ} k={k:<4} prov={s['prov_recall']:.3f} ({s['prov_hits']:>7}) "
              f"law={s['law_recall']:.3f}  calls={s['n_calls']:<5} {time.perf_counter()-t0:.0f}s")
    return {**_derive(curve, ladder),
            "provisions": len(provisions),
            "measured_on": time.strftime("%Y-%m-%d"),
            "curve": curve}


def _derive(curve: list[dict], ladder: tuple[int, ...]) -> dict:
    """Curve → cap, floor and the sentence that justifies them.

    BOTH recalls decide, not just provision recall. Malaysia is why: its provision recall is
    flat 0.875 at every k (one cited provision is never retrieved at any budget, so depth
    cannot buy it), while its LAW recall climbs 0.875 → 1.000 between k=40 and k=80. Choosing
    on provision recall alone would have capped Malaysia at 40 and dropped a cited Act out of
    the shortlist entirely — a law that never reaches the grader can never be answered.
    """
    best_p = max(c["prov_recall"] for c in curve)
    best_l = max(c["law_recall"] for c in curve)
    smallest = min(c["k"] for c in curve
                   if c["prov_recall"] >= best_p and c["law_recall"] >= best_l)
    cap = next((k for k in ladder if k >= smallest * MARGIN), max(ladder))
    return {
        "cap": cap,
        "floor": min(settings.retrieve_top_k, cap),
        "measured_k": smallest,
        "prov_recall": best_p,
        "law_recall": best_l,
        "note": (f"recall plateaus at prov={best_p:.3f} law={best_l:.3f} from k={smallest}; "
                 f"cap={cap} is that with a {MARGIN}x margin"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", nargs="*", default=None)
    ap.add_argument("--ladder", nargs="*", type=int, default=list(LADDER))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rederive", action="store_true",
                    help="recompute cap/floor from the curves already in the file — no "
                         "measurement, so the numbers stay the ones that were observed")
    a = ap.parse_args()

    econs = [e.upper() for e in (a.economy or sorted(labelled_economies()))]
    ladder = tuple(sorted(set(a.ladder)))
    print(f"[budget] ladder={ladder} margin={MARGIN}x  economies={econs}")

    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8")).get("economies", {})
        except Exception:  # noqa: BLE001
            existing = {}

    for econ in econs:
        if a.rederive:
            prev = existing.get(econ)
            if not prev or not prev.get("curve"):
                print(f"  {econ}: no stored curve to re-derive from - skipped")
                continue
            res = {**prev, **_derive(prev["curve"], tuple(prev.get("curve_ladder")
                                                          or [c["k"] for c in prev["curve"]]))}
        else:
            res = measure(econ, ladder)
        if res:
            existing[econ] = res
            print(f"  {econ}: cap={res['cap']} floor={res['floor']} - {res['note']}")

    doc = {
        "_README": ("Per-economy retrieval shortlist budget, GENERATED by "
                    "tools/measure_budget.py against the panel's own Database labels. Do not "
                    "hand-edit: re-run the tool. An economy absent from this file keeps the "
                    "conservative default in backend/config.py, which is the safe direction."),
        "generated_by": "tools/measure_budget.py",
        "ladder": list(ladder),
        "margin": MARGIN,
        "economies": dict(sorted(existing.items())),
    }
    if a.dry_run:
        print(json.dumps(doc, indent=1))
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print("written:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
