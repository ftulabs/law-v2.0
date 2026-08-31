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
#: Curves that never flattened. Kept as evidence, deliberately NOT as a budget — see _derive.
UNPLATEAUED = ROOT / "data" / "retrieval_budget_unplateaued.json"
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
        curve.append({"k": k, "prov_recall": s["prov_recall_available"],
                      "law_recall": s["law_recall"], "prov_hits": s["prov_hits_available"],
                      # every cited provision, including those the corpus does not hold —
                      # the honest overall figure, but not one a shortlist depth can move
                      "prov_recall_all_cited": s["prov_recall_each"],
                      "prov_hits_all_cited": s["prov_hits_each"],
                      # how many cited provisions the recall above is a fraction OF
                      "prov_sample": int(s["prov_hits_available"].split("/")[1]),
                      # the old per-indicator bit, kept so a re-measurement can be compared
                      # with the 2026-08-27 table rather than silently replacing it
                      "prov_recall_by_indicator": s["prov_recall"],
                      "n_calls": s["n_calls"]})
        print(f"  {econ} k={k:<4} in-corpus={s['prov_recall_available']:.3f} "
              f"({s['prov_hits_available']:>7})  all-cited={s['prov_recall_each']:.3f} "
              f"({s['prov_hits_each']:>7})  law={s['law_recall']:.3f}  "
              f"calls={s['n_calls']:<5} {time.perf_counter()-t0:.0f}s")
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

    CHANGED 2026-08-31: `prov_recall` here is `summary()["prov_recall_available"]` — every
    cited provision THE CORPUS ACTUALLY HOLDS — where it used to be `["prov_recall"]`, one bit
    per indicator. Two corrections in one:

      The bit saturated as soon as ONE citation per indicator arrived, so it plateaued long
      before recall did and the caps derived from it were too small. Malaysia's read "7/8" and
      capped at 150 while the panel cites 72 linkable provisions there.

      Counting ALL cited provisions instead would swing too far the other way: India reaches
      1 of 16, but six of its laws never fetched, so no shortlist depth on earth can reach
      them and a cap chosen from that number would just buy calls. `prov_recall_all_cited`
      is still recorded in the curve as the honest overall figure; the cap is derived from
      what retrieval can actually influence.

    The rule is otherwise unchanged.
    """
    best_p = max(c["prov_recall"] for c in curve)
    best_l = max(c["law_recall"] for c in curve)
    smallest = min(c["k"] for c in curve
                   if c["prov_recall"] >= best_p and c["law_recall"] >= best_l)
    cap = next((k for k in ladder if k >= smallest * MARGIN), max(ladder))
    # "Plateaus" was written unconditionally, and on the 2026-08-31 re-measurement it was FALSE
    # for five of six economies: provision recall was still CLIMBING at the ladder's last rung,
    # so `smallest` is where we stopped looking, not where the curve flattened. A cap justified
    # by a plateau that does not exist is an opinion wearing a measurement's clothes.
    plateaued = smallest < max(ladder)
    # How many provisions the recall is a fraction of. India's cap is derived from ONE — the
    # only cited provision its corpus holds, six of its laws having failed to fetch — and a cap
    # justified by a single data point should not read the same as one justified by fifty-five.
    # 0 means "this curve predates the field", not "zero provisions" — an older stored curve
    # re-derived with --rederive has no prov_sample, and warning that it was measured on
    # nothing would be a fabricated finding.
    samples = [c.get("prov_sample") for c in curve if c.get("prov_sample") is not None]
    sample = max(samples) if samples else None
    note = (f"recall plateaus at prov={best_p:.3f} law={best_l:.3f} from k={smallest}; "
            f"cap={cap} is that with a {MARGIN}x margin") if plateaued else (
        f"recall had NOT plateaued at the ladder's last rung k={max(ladder)} "
        f"(prov={best_p:.3f} law={best_l:.3f}, still rising); cap={cap} is the deepest "
        f"measured, NOT a measured sufficiency — extend the ladder to find the real one")
    if sample is not None and sample < 5:
        note += (f"  ⚠ derived from only {sample} cited provision(s) in the corpus — too few to "
                 f"choose a cap from; fix the fetch failures and re-measure before trusting it")
    # A curve that never flattened has not told us a sufficient depth; it has told us the ladder
    # was too short. Writing the last rung down as the answer is how the whole table became 450
    # on 2026-08-31, which cost $2.07 -> $7.39 a submission and added ~418 wrong rows for 17
    # right ones. `write_ok=False` keeps the economy OUT of the table, so it falls back to the
    # conservative default in backend/config.py — the honest reading of "we did not find it".
    write_ok = bool(plateaued)
    return {
        "write_ok": write_ok,
        "cap": cap,
        "floor": min(settings.retrieve_top_k, cap),
        "measured_k": smallest,
        "plateaued": plateaued,
        "prov_sample": sample,
        "prov_recall": best_p,
        "law_recall": best_l,
        "note": note,
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

    existing, unplateaued = {}, {}
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
        if not res:
            continue
        if not res.get("write_ok"):
            # Not written: an unflattened curve says the ladder was too short, not that the
            # last rung is enough. The economy keeps the conservative default, and the curve
            # is kept beside it so the next run can extend the ladder instead of re-measuring
            # from nothing.
            existing.pop(econ, None)
            print(f"  {econ}: NOT WRITTEN — {res['note']}")
            print(f"         (curve kept in {UNPLATEAUED.name}; the economy keeps the "
                  f"conservative default)")
            unplateaued[econ] = res
            continue
        existing[econ] = res
        print(f"  {econ}: cap={res['cap']} floor={res['floor']} - {res['note']}")

    doc = {
        "_README": ("Per-economy retrieval shortlist budget, GENERATED by "
                    "tools/measure_budget.py against the panel's own Database labels. Do not "
                    "hand-edit: re-run the tool. An economy absent from this file keeps the "
                    "conservative default in backend/config.py, which is the safe direction. "
                    "`prov_recall` counts the cited provisions THE CORPUS HOLDS that reach the "
                    "shortlist — not one bit per indicator (which saturates on the first hit "
                    "and produced caps that were far too small), and not every cited provision "
                    "(which counts documents that never fetched, and no shortlist depth can "
                    "reach those). `prov_recall_all_cited` in each curve point is that wider, "
                    "honest figure. `plateaued: false` means recall was STILL RISING at the "
                    "ladder's last rung, so the cap is the deepest measured rather than a "
                    "measured sufficiency. `prov_sample` is how many provisions the recall is "
                    "a fraction of; below five it is too few to choose a cap from."),
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
    if unplateaued:
        prior = {}
        if UNPLATEAUED.exists():
            try:
                prior = json.loads(UNPLATEAUED.read_text(encoding="utf-8")).get("economies", {})
            except Exception:  # noqa: BLE001
                prior = {}
        prior.update(unplateaued)
        UNPLATEAUED.write_text(json.dumps(
            {"_README": ("Recall curves that were STILL RISING at the ladder's last rung. They "
                         "are evidence, not budgets: nothing reads this file at run time. An "
                         "economy here keeps the conservative default until a longer ladder "
                         "finds where its curve actually flattens."),
             "economies": dict(sorted(prior.items()))}, indent=1), encoding="utf-8")
        print("unplateaued curves written:", UNPLATEAUED)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
