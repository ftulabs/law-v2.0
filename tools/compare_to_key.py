"""Did the cheaper run still reach the panel's own answers? Measured on the CSV, not the shortlist.

    python tools/compare_to_key.py SG MY AU

The per-economy retrieval budget was chosen on RETRIEVAL recall — whether the provision the
panel cited reaches the shortlist at all. That is the ceiling on everything the grader can get
right, and it needs no LLM call, which is why it was measured first. It is not the same claim
as "the submission still contains the answer", because a provision can reach the shortlist and
still be rejected by the grader. This closes that gap: it reads the exported CSV of two runs
and asks, per indicator, whether a law the panel accepted appears in ours.

Law names are matched on the linkage module's normalised form (case, punctuation, year and
instrument-type noise removed), in both containment directions, because the panel writes
"Personal Data Protection Act 2012" where a portal writes "Personal Data Protection Act 2012
(Singapore)".
"""
from __future__ import annotations

import csv
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.eval.ground_truth import load_labels     # noqa: E402
from backend.eval.linkage import _norm                # noqa: E402

IND = {f"{p}.{i}": f"P{p}-I{i}" for p in (6, 7) for i in range(1, 6)}


def key_laws(econ: str) -> dict[str, set[str]]:
    want: dict[str, set[str]] = {}
    for r in load_labels():
        if r.economy != econ or r.kind != "provision":
            continue
        want.setdefault(r.indicator_id, set()).update(_norm(l) for l in r.laws if len(l) > 4)
    return {k: {v for v in vs if v} for k, vs in want.items()}


def rows_of(path: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ind = (row.get("Indicator ID") or row.get("Indicator_ID") or "").strip()
            ind = IND.get(ind, ind)
            law = (row.get("Law Name") or row.get("Law/Regulation Name") or "").strip()
            # "No evidence" rows are a deliberate output, not a citation — see the placeholder
            # stage in the orchestrator. Counting them as coverage would score an absence as a hit.
            if law and "no evidence" not in law.lower():
                out.setdefault(ind, set()).add(_norm(law))
    return out


def score(path: str, want: dict[str, set[str]]) -> tuple[int, int, list, int]:
    got = rows_of(path)
    hit, detail = 0, []
    for ind, laws in sorted(want.items()):
        ours = got.get(ind, set())
        found = any(any(w in o or o in w for o in ours) for w in laws)
        hit += found
        detail.append((ind, found, len(ours)))
    return hit, len(want), detail, sum(len(v) for v in got.values())


def newest(pattern: str) -> str | None:
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def main() -> int:
    econs = [e.upper() for e in (sys.argv[1:] or ["SG", "MY", "AU"])]
    for econ in econs:
        want = key_laws(econ)
        old = newest(f"outputs/rt_check/{econ}_P67_*.csv")
        new = newest(f"outputs/budget_check/{econ}_P67_*.csv")
        print(f"\n=== {econ}")
        for label, path in (("before (untuned budget)", old), ("after  (measured budget)", new)):
            if not path:
                print(f"  {label}: no run found")
                continue
            h, t, detail, n = score(path, want)
            miss = [i for i, ok, _ in detail if not ok]
            print(f"  {label}: {h}/{t} answer-key indicators reached · {n} law-rows exported"
                  + (f" · MISSED {miss}" if miss else ""))
            print(f"      {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
