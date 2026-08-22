"""Freeze a labelled provision set for the engine bake-off.

Why this file exists
--------------------
Two declared engines must be named on the Word submission and cannot be changed afterwards, so
the choice has to rest on a measurement rather than on a reputation. The obvious measurement —
score each candidate against `data/ground_truth/rdtii_reference_p67.csv` — does not work
directly, because the panel's own databases record **no verbatim text**: `Verbatim Snippet` is
empty in all 180 rows. They tell us *which article of which law* answers an indicator, never
what it says.

So the labelled set is assembled by joining two things we do have:

    the panel's answer key       (economy, law, article) -> indicator
    our own extracted provisions (economy, law, article) -> text

Matching is by the numeric article spine from `rdtii/baseline.py`, which already reduces
"Section 199", "s. 26(1)", "第四十条" and "14 дүгээр зүйл" to a comparable form — the same
matcher the Discovery Tag uses, so a bug in it shows up in two places rather than hiding here.

Negatives matter as much as positives. A grader that says yes to everything scores perfectly on
positives alone, and the failure we actually see in production is over-eager mapping, not
under-eager. So the set carries, for every positive, several provisions drawn from the SAME law
that the panel did NOT cite for that indicator. Those are the hard negatives: same statute, same
vocabulary, same drafting style, wrong provision.

The set is written to disk and committed. It is a FROZEN benchmark: if it were rebuilt on each
run, two candidates measured a week apart would not be comparable, which is the one thing a
bake-off must guarantee.

    python tools/build_bakeoff_set.py                 # build, report, write
    python tools/build_bakeoff_set.py --stats         # just describe what is already there
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ROOT                                    # noqa: E402
from backend.rdtii import baseline as B                            # noqa: E402
from backend.schemas import ECONOMY_UN_NAME                        # noqa: E402

OUT = ROOT / "data" / "benchmarks" / "grader_bakeoff.json"
DB = ROOT / "outputs" / "veritrade.db"

#: Hard negatives per positive. Three is enough to punish a yes-to-everything grader without
#: making the set so negative-heavy that accuracy is dominated by saying no.
NEGATIVES_PER_POSITIVE = 3
#: A provision shorter than this is a heading or a cross-reference, not an operative rule.
MIN_CHARS = 120
MAX_CHARS = 2400
SEED = 20260822          # fixed: the set must be identical on every machine


def _provisions_by_economy() -> dict[str, list[dict]]:
    """Every extracted provision we hold, grouped by economy, deduplicated by text."""
    if not DB.exists():
        raise SystemExit(f"no audit database at {DB} — run the pipeline at least once first")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT p.law_name, p.article_section, p.prov_json, d.economy, d.source_url
        FROM provisions p JOIN documents d ON p.doc_id = d.doc_id AND p.run_id = d.run_id
        WHERE d.economy IS NOT NULL
    """).fetchall()
    out: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for r in rows:
        try:
            text = (json.loads(r["prov_json"]) or {}).get("verbatim_snippet") or ""
        except Exception:
            continue
        text = text.strip()
        if not (MIN_CHARS <= len(text) <= MAX_CHARS):
            continue
        key = (r["economy"], text[:200])
        if key in seen:
            continue
        seen.add(key)
        out[r["economy"]].append({
            "economy": r["economy"], "law_name": r["law_name"] or "",
            "article_section": r["article_section"] or "", "text": text,
            "source_url": r["source_url"] or "",
        })
    con.close()
    return out


#: Hand-curated non-English cases. The audit database holds no Chinese corpus, so the joined
#: set above is entirely English (SG/AU/MY) — and a grader chosen on English alone is chosen on
#: the wrong evidence for six of the nine live-test economies. These provisions are quoted from
#: the statutes themselves and their indicator is the panel's own answer, so they are ground
#: truth in the same sense as the joined rows; they are listed separately only because they were
#: assembled by hand rather than by the matcher, and that difference should stay visible.
CURATED_NON_ENGLISH = [
    ("CN", "个人信息保护法", "第四十条", "P6-I2",
     "关键信息基础设施运营者和处理个人信息达到国家网信部门规定数量的个人信息处理者，"
     "应当将在中华人民共和国境内收集和产生的个人信息存储在境内。"
     "确需向境外提供的，应当通过国家网信部门组织的安全评估。"),
    ("CN", "个人信息保护法", "第三十八条", "P6-I4",
     "个人信息处理者因业务等需要，确需向中华人民共和国境外提供个人信息的，"
     "应当具备下列条件之一：（一）依照本法第四十条的规定通过国家网信部门组织的安全评估；"
     "（二）按照国家网信部门的规定经专业机构进行个人信息保护认证。"),
    ("CN", "网络安全法", "第二十一条", "P7-I3",
     "国家实行网络安全等级保护制度。网络运营者应当按照网络安全等级保护制度的要求，"
     "采取监测、记录网络运行状态、网络安全事件的技术措施，"
     "并按照规定留存相关的网络日志不少于六个月。"),
    ("CN", "个人信息保护法", "第五十二条", "P7-I4",
     "处理个人信息达到国家网信部门规定数量的个人信息处理者应当指定个人信息保护负责人，"
     "负责对个人信息处理活动以及采取的保护措施等进行监督。"),
    ("CN", "网络安全法", "第一条", "P7-I2",
     "为了保障网络安全，维护网络空间主权和国家安全、社会公共利益，"
     "保护公民、法人和其他组织的合法权益，促进经济社会信息化健康发展，制定本法。"),
]


def build() -> dict:
    import csv

    ref_path = ROOT / "data" / "ground_truth" / "rdtii_reference_p67.csv"
    with ref_path.open(encoding="utf-8-sig", newline="") as f:
        reference = [r for r in csv.DictReader(f) if (r.get("Article / Section") or "").strip()]

    by_econ = _provisions_by_economy()
    un_to_code = {v: k for k, v in ECONOMY_UN_NAME.items()}
    rng = random.Random(SEED)

    positives: list[dict] = []
    unmatched: list[str] = []
    # (economy, law tokens) -> the indicators the panel cites for that law, so a negative is
    # never a provision the panel happened to cite for a DIFFERENT indicator.
    cited: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in reference:
        code = un_to_code.get(row["Economy"].strip())
        if code:
            cited[(code, row["Law Name"].strip().lower())].add(row["Indicator ID"].strip())

    for row in reference:
        code = un_to_code.get(row["Economy"].strip())
        pool = by_econ.get(code or "", [])
        if not pool:
            unmatched.append(f"{row['Economy']} (no provisions extracted)")
            continue
        want_spine = B.article_spine(row["Article / Section"])
        want_law = B.law_tokens(row["Law Name"])
        if not want_spine:
            continue
        hit = None
        for p in pool:
            if not B._same_law(want_law, B.law_tokens(p["law_name"])):
                continue
            if B.article_spine(p["article_section"]) & want_spine:
                hit = p
                break
        if hit is None:
            unmatched.append(f"{row['Economy']} · {row['Law Name'][:40]} · {row['Article / Section']}")
            continue
        positives.append({
            "id": f"pos:{len(positives)}",
            "economy": code, "law_name": hit["law_name"],
            "article_section": hit["article_section"], "text": hit["text"],
            "source_url": hit["source_url"],
            "indicator_id": row["Indicator ID"].strip(),
            "label": True,
        })

    # ── hard negatives: same law, an indicator the panel did NOT cite it for ──────────
    negatives: list[dict] = []
    all_indicators = sorted({p["indicator_id"] for p in positives})
    for p in positives:
        law_key = None
        for (econ, law), inds in cited.items():
            if econ == p["economy"] and B._same_law(B.law_tokens(law), B.law_tokens(p["law_name"])):
                law_key = inds
                break
        forbidden = law_key or {p["indicator_id"]}
        choices = [i for i in all_indicators if i not in forbidden]
        rng.shuffle(choices)
        for ind in choices[:NEGATIVES_PER_POSITIVE]:
            negatives.append({**p, "id": f"neg:{len(negatives)}", "indicator_id": ind,
                              "label": False})

    # ── hand-curated non-English positives + their negatives ──────────────────────────
    for econ, law, art, ind, text in CURATED_NON_ENGLISH:
        positives.append({"id": f"pos:{len(positives)}", "economy": econ, "law_name": law,
                          "article_section": art, "text": text, "source_url": "",
                          "indicator_id": ind, "label": True, "curated": True})
        for other in [i for i in all_indicators if i != ind][:NEGATIVES_PER_POSITIVE]:
            negatives.append({"id": f"neg:{len(negatives)}", "economy": econ, "law_name": law,
                              "article_section": art, "text": text, "source_url": "",
                              "indicator_id": other, "label": False, "curated": True})

    return {
        "seed": SEED,
        "built_from": {"reference": str(ref_path.relative_to(ROOT)),
                       "audit_db": str(DB.relative_to(ROOT))},
        "note": ("Frozen benchmark. Do not rebuild casually: two candidates measured against "
                 "different sets are not comparable, which is the one guarantee a bake-off "
                 "needs. Positives are the panel's own answer key joined to our extracted text "
                 "by article spine; negatives are provisions of the SAME law paired with an "
                 "indicator the panel did not cite it for."),
        "cases": positives + negatives,
        "unmatched_reference_rows": len(unmatched),
        "unmatched_examples": unmatched[:15],
    }


def describe(data: dict) -> str:
    cases = data["cases"]
    pos = [c for c in cases if c["label"]]
    neg = [c for c in cases if not c["label"]]
    by_econ: dict[str, int] = defaultdict(int)
    by_ind: dict[str, int] = defaultdict(int)
    for c in pos:
        by_econ[c["economy"]] += 1
        by_ind[c["indicator_id"]] += 1
    lines = [f"cases {len(cases)}  ({len(pos)} positive · {len(neg)} negative)",
             f"reference rows with an article that we could NOT match: "
             f"{data['unmatched_reference_rows']}",
             "positives by economy : " + "  ".join(f"{k} {v}" for k, v in sorted(by_econ.items())),
             "positives by indicator: " + "  ".join(f"{k} {v}" for k, v in sorted(by_ind.items()))]
    if data.get("unmatched_examples"):
        lines.append("unmatched examples:")
        lines += [f"   {e}" for e in data["unmatched_examples"][:8]]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stats", action="store_true", help="describe the existing set, build nothing")
    args = ap.parse_args()
    if args.stats:
        if not OUT.exists():
            raise SystemExit(f"{OUT} does not exist yet — run without --stats")
        print(describe(json.loads(OUT.read_text(encoding="utf-8"))))
        return 0
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(describe(data))
    print(f"\nwritten -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
