"""Per-PROVISION scorecard against the panel's database. Four numbers, not one.

    python tools/provision_scorecard.py SG AU MY CN IN MN
    python tools/provision_scorecard.py MN --detail

"Indicators reached" is too coarse to act on: one lucky row anywhere inside an indicator
scores it, and an indicator with five cited provisions counts the same as one with a single
provision. This counts the provisions themselves, and splits our output four ways:

  HIT              the panel cites this provision, and we cite it under the same indicator
  WRONG INDICATOR  we cite the same law and article, but filed under a different indicator —
                   the document was found and read, the classification is what went wrong
  MISSING          the panel cites it and we do not cite it anywhere at all
  NEW              we cite a provision the panel does not — either a genuine find (the brief
                   says finding more than the panel is an explicit goal) or a false positive.
                   It is counted, never scored, because only a lawyer can tell those apart.

The split matters because the three failures need three different fixes. MISSING is discovery
or fetch: the text never arrived. WRONG INDICATOR is the grader or the indicator definition:
the text arrived and was misread. NEW is a question for a human.

A provision is matched on (law, article), where the law matches by name OR by document URL —
see tools/compare_to_key.url_keys for why the URL is needed: the panel names laws in English
and the portals publish them in Mongolian, Chinese and Thai.
"""
from __future__ import annotations

import csv
import glob
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.eval.ground_truth import load_labels          # noqa: E402
from backend.eval.harness import label_section_key, section_key   # noqa: E402
from backend.eval.linkage import _norm                     # noqa: E402
from tools.compare_to_key import IND, url_keys             # noqa: E402


def key_provisions(econ: str) -> list[dict]:
    """One entry per (indicator, law, cited article) the panel accepted."""
    out = []
    for r in load_labels():
        if r.economy != econ or r.kind != "provision" or not r.sections:
            continue
        names = {n for n in (_norm(x) for x in r.laws if len(x) > 4) if n}
        urls = set()
        for u in r.portal_urls + r.other_urls:
            urls |= url_keys(u)
        for sec in r.sections:
            k = label_section_key(sec)
            if k:
                out.append({"indicator": r.indicator_id, "names": names, "urls": urls,
                            "section": k, "label": f"{r.indicator_id} {sorted(names)[:1]} s.{sec}"})
    return out


def our_rows(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            law = (row.get("Law Name") or "").strip()
            if not law or "no evidence" in law.lower():
                continue
            ind = (row.get("Indicator ID") or "").strip()
            out.append({
                "indicator": IND.get(ind, ind),
                "name": _norm(law), "raw_name": law,
                "urls": url_keys(row.get("Source URL") or ""),
                "section": section_key(row.get("Article/Section") or
                                       row.get("Article / Section") or ""),
                "raw_section": (row.get("Article/Section") or
                                row.get("Article / Section") or "").strip(),
            })
    return out


def _same_law(k: dict, r: dict) -> bool:
    if r["name"] and any(n in r["name"] or r["name"] in n for n in k["names"]):
        return True
    return bool(k["urls"] & r["urls"])


def _same_provision(ours: str | None, theirs: str) -> bool:
    """Does our citation cover the article the panel cited?

    Not string equality, and getting that wrong cost Mongolia most of its score. The panel
    cites a CLAUSE — "20.2" is clause 2 of article 20 — while the splitter cuts at article
    level and labels the provision "20". Compared literally, every clause citation in
    Mongolia, and every "s.11(3)" in Singapore, reads as a miss even though the provision
    containing it was found, exported and quoted verbatim.

    A parent covering a cited child is a HIT: the row carries the article's whole text, so
    the clause is in the snippet. A child under a cited parent is also a hit — we cited more
    precisely than the panel did. `harness.section_matches` already encodes this rule for the
    retrieval harness; this is the same rule on the export side.
    """
    if not ours:
        return False
    if ours == theirs:
        return True
    return ours.startswith(theirs + ".") or theirs.startswith(ours + ".")


def score(econ: str, path: str, detail: bool = False) -> dict:
    keys, rows = key_provisions(econ), our_rows(path)
    matched_rows: set[int] = set()
    hit, wrong, missing = [], [], []

    for k in keys:
        same_prov = [i for i, r in enumerate(rows)
                     if _same_law(k, r) and _same_provision(r["section"], k["section"])]
        right = [i for i in same_prov if rows[i]["indicator"] == k["indicator"]]
        if right:
            hit.append(k)
            matched_rows.update(right)
        elif same_prov:
            wrong.append((k, rows[same_prov[0]]["indicator"]))
            matched_rows.update(same_prov)
        else:
            missing.append(k)

    new = [r for i, r in enumerate(rows) if i not in matched_rows]
    res = {"economy": econ, "key_provisions": len(keys), "hit": len(hit),
           "wrong_indicator": len(wrong), "missing": len(missing),
           "our_rows": len(rows), "new": len(new)}
    if detail:
        res["_wrong"] = [(k["label"], got) for k, got in wrong]
        res["_missing"] = [k["label"] for k in missing]
    return res


def newest(econ: str) -> str | None:
    hits = sorted(glob.glob(f"outputs/budget_check/{econ}_P67_*.csv")) or \
        sorted(glob.glob(f"outputs/rt_check/{econ}_P67_*.csv"))
    return hits[-1] if hits else None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    detail = "--detail" in sys.argv
    econs = [e.upper() for e in (args or ["SG", "AU", "MY", "CN", "IN", "MN"])]
    print(f"{'ec':4} {'key prov':>9} {'HIT':>5} {'WRONG IND':>10} {'MISSING':>8} "
          f"{'our rows':>9} {'NEW':>5}   recall")
    for econ in econs:
        path = newest(econ)
        if not path:
            print(f"{econ:4} no run found")
            continue
        r = score(econ, path, detail)
        rec = r["hit"] / r["key_provisions"] if r["key_provisions"] else 0
        print(f"{econ:4} {r['key_provisions']:>9} {r['hit']:>5} {r['wrong_indicator']:>10} "
              f"{r['missing']:>8} {r['our_rows']:>9} {r['new']:>5}   {rec:.0%}")
        if detail:
            for lab, got in r.get("_wrong", []):
                print(f"     WRONG  {lab}  -> filed as {got}")
            for lab in r.get("_missing", []):
                print(f"     MISS   {lab}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
