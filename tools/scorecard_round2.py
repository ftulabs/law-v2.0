"""Per economy x pillar: how many of the panel's Round-2 indicators does an exported CSV reach?

    python tools/scorecard_round2.py outputs/rt_0930/*.csv

For each (economy, indicator) the panel's Round-2 Database cites at least one law for
(data/ground_truth/rdtii_reference_p67.csv), the export "reaches" it when one of its rows for
that indicator cites the same law (same matching as the KNOWN tag: portal id, law number or
name tokens — backend/rdtii/baseline.py), and "reaches the article" when the article matches
too. The panel's rows that only say "no such measure" (score 0 for 6.x, 7.3-7.5) are skipped:
there is nothing to find. The frameworks 7.1 and 7.2 are kept whatever their score, because
there the law itself is the evidence.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rdtii import baseline                                   # noqa: E402
from backend.schemas import ECONOMY_UN_NAME, PLACEHOLDER_LAW_NAMES   # noqa: E402

REF = Path(__file__).resolve().parent.parent / "data/ground_truth/rdtii_reference_p67.csv"
csv.field_size_limit(10**9)


def targets() -> dict[tuple[str, str], list[dict]]:
    out: dict = defaultdict(list)
    for r in csv.DictReader(open(REF, encoding="utf-8-sig")):
        ind = r["Indicator ID"]
        score = (r.get("RDTII_Raw_Score") or "").strip()
        if ind not in ("P7-I1", "P7-I2") and score in ("0", "0.0", ""):
            continue
        out[(r["Economy"], ind)].append(r)
    return out


def _restrict_baseline_to(tg) -> None:
    """Match only against the panel rows that are targets. The full baseline also holds the
    panel's score-0 rows ("Indonesia's PP 71 is NOT an infrastructure requirement"), and a row
    of ours citing that law under 6.3 is a wrong answer the KNOWN tag would count as a hit."""
    full = baseline.load()
    keep = {(e, i): [x for x in full.get((e, i), [])
                     if any(x.law_name == r["Law Name"] for r in rows)]
            for (e, i), rows in tg.items()}
    baseline.load = lambda path=None: keep


def main(paths: list[str]) -> None:
    tg = targets()
    _restrict_baseline_to(tg)
    code_of = {v: k.value if hasattr(k, "value") else k for k, v in ECONOMY_UN_NAME.items()}
    rows_by = defaultdict(list)
    for p in paths:
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r["Law Name"] in PLACEHOLDER_LAW_NAMES or not r.get("Indicator ID"):
                continue
            ind = r["Indicator ID"]
            ind = ind if ind.startswith("P") else f"P{ind.split('.')[0]}-I{ind.split('.')[1]}"
            rows_by[(r["Economy"], ind)].append(r)
    table = defaultdict(lambda: [0, 0, 0, 0])      # (econ, pillar) -> targets, law, article, rows
    missed = defaultdict(list)
    econs = sorted({e for e, _ in rows_by})
    for (econ, ind), refs in tg.items():
        if econ not in econs:
            continue
        pil = ind[1]
        t = table[(econ, pil)]
        t[0] += 1
        law = art = False
        for r in rows_by.get((econ, ind), []):
            tag, note = baseline.classify(econ, ind, r["Law Name"], r["Article / Section"],
                                          r.get("Source URL", ""), r.get("Law Number / Ref", ""))
            if tag == "KNOWN" or (note or "").startswith("Baseline cites this law"):
                law = True
                art = art or (tag == "KNOWN" and not note)
        t[1] += law
        t[2] += art
        if not law:
            missed[(econ, pil)].append(ind)
    for (econ, ind), rs in rows_by.items():
        table[(econ, ind[1])][3] += len(rs)
    print(f"{'economy':32} pil  panel-indicators  law-reached  article-reached  our-rows  missed")
    for (econ, pil), (n, law, art, rows) in sorted(table.items()):
        if n == 0:
            continue
        print(f"{econ[:32]:32} P{pil}   {n:>6}           {law:>3} ({law/n:4.0%})   {art:>3}"
              f"             {rows:>5}   {' '.join(missed[(econ, pil)])}")


if __name__ == "__main__":
    main(sys.argv[1:])
