"""Re-grade rows we already exported, under a changed indicator definition. No crawl.

    python tools/replay_grade.py --variant baseline  --indicators P6-I1 P6-I2 P6-I3
    python tools/replay_grade.py --variant candidate --indicators P6-I1 P6-I2 P6-I3

Why this exists. The first attempt to fix a definition (tightening P7-I1, 2026-08-30) was
judged by re-running three economies end to end: ~40 minutes and real money to learn that the
change recovered nothing. Almost all of that cost is discovery, fetch and extraction — stages
the edit cannot possibly affect. The only thing a definition change alters is the grader's
verdict on a provision it was already shown.

So this replays exactly that step. It takes provisions out of the exported CSVs, sends them
through the SAME `mapping.SYSTEM` prompt and `mapping._user_prompt`, and reports what changed.
One call per row instead of a whole pipeline.

It scores against three populations, and a change is only good if all three move the right way:

  CONTROL   rows the panel itself cites under this indicator. These must survive. A definition
            that drops them is not stricter, it is wrong — this is the check the P7-I1 attempt
            did not have, and it is why that attempt's real cost went unnoticed for an hour.
  REJECTED  our rows an independent auditor refused (tools/audit_rows.py). These SHOULD drop.
  UPHELD    our rows the same auditor accepted. These should survive; they are the cost side of
            any tightening, and a fix that drops them buys precision with recall.

The candidate definitions live in tools/candidate_indicators.py, not in the shipped file, so a
variant can be measured before anything ships.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings                                  # noqa: E402
from backend.pipeline import mapping                                 # noqa: E402
from backend.rdtii import indicators as ind_mod                      # noqa: E402
from backend.schemas import Economy, Provision                       # noqa: E402
from tools.provision_scorecard import (_same_law, _same_provision,   # noqa: E402
                                       key_provisions, newest, our_rows)

AUDIT_LOGS = ("logs/audit_sg_au_my.json", "logs/audit_cn_in.json", "logs/audit2.json",
              # last wins: the post-P6-gate audit, and the only one covering pillar 7
              # at depth (47 P7-I3 rows against the older logs' 12-21).
              "logs/audit_after_20260831.json")
IND = {f"{p}.{j}": f"P{p}-I{j}" for p in (6, 7) for j in range(1, 6)}


def audit_verdicts() -> dict[tuple, bool]:
    """{(economy, indicator, law[:90], section): the auditor said it satisfies}."""
    out: dict[tuple, bool] = {}
    for p in AUDIT_LOGS:
        if not Path(p).exists():
            continue
        for r in json.load(open(p, encoding="utf-8"))["rows"]:
            if r["kind"] != "ours-only":
                continue
            out[(r["economy"], r["indicator"], (r["law"] or "")[:90], r["section"])] = \
                bool(r["satisfies"])
    return out


def rows_for(econ: str, wanted: set[str], verdicts: dict[tuple, bool]) -> list[dict]:
    """Exported rows for these indicators, each tagged with the population it belongs to."""
    path = newest(econ)
    if not path:
        return []
    parsed = our_rows(path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    # `our_rows` drops placeholder rows, so it is not index-aligned with the raw file; rebuild
    # the same filter here to keep the two in step.
    raw = [r for r in raw if (r.get("Law Name") or "").strip()
           and "no evidence" not in (r.get("Law Name") or "").lower()]

    confirmed = set()
    for k in key_provisions(econ):
        for i, r in enumerate(parsed):
            if _same_law(k, r) and _same_provision(r["section"], k["section"]) \
                    and r["indicator"] == k["indicator"]:
                confirmed.add(i)

    out = []
    for i, row in enumerate(raw):
        ind = IND.get((row.get("Indicator ID") or "").strip(),
                      (row.get("Indicator ID") or "").strip())
        if ind not in wanted:
            continue
        law = (row.get("Law Name") or "").strip()
        sec = (row.get("Article/Section") or row.get("Article / Section") or "").strip()
        if i in confirmed:
            pop = "CONTROL"
        else:
            v = verdicts.get((econ, ind, law[:90], sec))
            pop = "unaudited" if v is None else ("UPHELD" if v else "REJECTED")
        out.append({"economy": econ, "indicator": ind, "law": law, "section": sec,
                    "snippet": row.get("Verbatim Snippet") or "", "pop": pop,
                    "url": row.get("Source URL") or ""})
    return out


def apply_candidate() -> list[str]:
    """Overwrite the shipped legal_test/query_terms in memory. Returns what changed."""
    from tools.candidate_indicators import CANDIDATE
    changed = []
    for iid, patch in CANDIDATE.items():
        ind = ind_mod.get_indicator(iid)
        if ind is None:
            raise SystemExit(f"unknown indicator {iid}")
        for field, value in patch.items():
            setattr(ind, field, value)
        changed.append(iid)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("baseline", "candidate"), default="baseline")
    ap.add_argument("--indicators", nargs="+", default=["P6-I1", "P6-I2", "P6-I3"])
    ap.add_argument("--economies", nargs="+", default=["SG", "AU", "MY", "CN", "IN", "MN"])
    ap.add_argument("--out", default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--all-rows", action="store_true",
                    help="also grade rows nobody audited — no pass/fail attaches to them, but "
                         "they are most of the output, so this is how much volume a change costs")
    a = ap.parse_args()

    if a.variant == "candidate":
        print("candidate definitions applied to:", ", ".join(apply_candidate()))

    wanted, verdicts = set(a.indicators), audit_verdicts()
    population = [r for e in a.economies for r in rows_for(e.upper(), wanted, verdicts)]
    # An unaudited row carries no expectation, so by default grading it buys nothing measurable.
    if not a.all_rows:
        population = [r for r in population if r["pop"] != "unaudited"]
    print(f"{len(population)} rows: "
          + ", ".join(f"{k}={v}" for k, v in Counter(r["pop"] for r in population).items()))

    from backend.providers import get_llm_provider
    llm = get_llm_provider(settings.llm_provider)
    _graded_by = getattr(llm, "model_version", None) or settings.openrouter_model
    print(f"grader: {getattr(llm, 'name', '?')} / {_graded_by}")

    def one(row):
        ind = ind_mod.get_indicator(row["indicator"])
        prov = Provision(provision_id="replay", doc_id="replay",
                         economy=Economy(row["economy"]), law_name=row["law"],
                         article_section=row["section"] or "(document)",
                         verbatim_snippet=row["snippet"], source_url=row["url"])
        try:
            g = llm.complete_json(mapping.SYSTEM, mapping._user_prompt(ind, prov))
        except Exception as e:                                    # noqa: BLE001
            return row, None, f"{type(e).__name__}: {e}"[:120]
        if not g or g.get("_parse_error"):
            return row, None, "unparseable"
        return row, mapping._relevant(g), (g.get("rationale") or "")[:200]

    results, tally = [], defaultdict(Counter)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for row, ok, why in pool.map(one, population):
            state = "error" if ok is None else ("kept" if ok else "dropped")
            tally[row["pop"]][state] += 1
            tally[f"{row['indicator']}/{row['pop']}"][state] += 1
            results.append({**{k: row[k] for k in
                               ("economy", "indicator", "law", "section", "pop")},
                            "kept": ok, "why": why})

    print(f"\n=== {a.variant} ===")
    print(f"{'population':12} {'kept':>5} {'dropped':>8} {'err':>4}   want")
    want = {"CONTROL": "keep ALL", "UPHELD": "keep", "REJECTED": "DROP",
            "unaudited": "(volume only — no expectation)"}
    for pop in ("CONTROL", "UPHELD", "REJECTED", "unaudited"):
        if not tally[pop]:
            continue
        c = tally[pop]
        print(f"{pop:12} {c['kept']:>5} {c['dropped']:>8} {c['error']:>4}   {want[pop]}")
    print()
    for iid in sorted(a.indicators):
        bits = [f"{pop} {tally[f'{iid}/{pop}']['kept']}kept/"
                f"{tally[f'{iid}/{pop}']['dropped']}dropped"
                for pop in ("CONTROL", "UPHELD", "REJECTED", "unaudited") if tally[f"{iid}/{pop}"]]
        if bits:
            print(f"  {iid}: " + " · ".join(bits))

    out = a.out or f"logs/replay_{a.variant}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({"variant": a.variant, "model": _graded_by,
                                     "rows": results}, indent=1, ensure_ascii=False),
                         encoding="utf-8")
    print("\nwritten:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
