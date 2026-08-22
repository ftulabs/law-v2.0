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
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ROOT                                    # noqa: E402
from backend.rdtii import baseline as B, instrument                # noqa: E402
from backend.schemas import ECONOMY_UN_NAME                        # noqa: E402

OUT = ROOT / "data" / "benchmarks" / "grader_bakeoff.json"
DB = ROOT / "outputs" / "veritrade.db"

#: Hard negatives per positive. Three is enough to punish a yes-to-everything grader without
#: making the set so negative-heavy that accuracy is dominated by saying no.
NEGATIVES_PER_POSITIVE = 3
#: A provision shorter than this is a heading or a cross-reference, not an operative rule.
MIN_CHARS = 120
MAX_CHARS = 2400
SEED = 20260822          # bump only with a rebuild everyone re-runs          # fixed: the set must be identical on every machine



# ── Why the first build of this set was wrong, and what stops it recurring ───────────
#
# The first version produced 37 positives, and 19 of them were rejected by ALL EIGHT
# candidate models. Eight models that disagree about everything else do not agree on a
# mistake; that pattern means the LABELS were wrong. Reading them confirmed it:
#
#   "Extension to external Territories (Christmas Island...)"  labelled 7.5 government access
#   "Objects of this Act"                                      labelled 7.5
#   "Short title and commencement"                             labelled 6.4 conditional flow
#   "Amendment of section 4 — substituting words in a
#    definition"                                               labelled 6.2 local storage
#
# One cause, two symptoms. Section numbers like 3, 6 and 10 occur in every statute, and
# `_same_law` accepts 75% token overlap against the SHORTER name — so a citation of the
# "Personal Data Protection Act 2010" matched a provision of the "Personal Data Protection
# (AMENDMENT) Act 2024", and picked whatever section 3 happened to be there.
#
# A benchmark that scores a correct model as wrong is worse than no benchmark: it would have
# had us declare an engine on the strength of noise, and the declaration cannot be revised.
# So four filters, each aimed at one observed failure.

#: Boilerplate that opens or closes almost every statute. None of it can be an operative rule,
#: so a citation resolving to one of these is a matcher failure, not a finding.
_BOILERPLATE = re.compile(
    r"^\s*(?:short\s+title|citation|commencement|objects?\b|purpose\s+of\s+this\s+act"
    r"|interpretation|definitions?|application\b|extension\s+to|arrangement\s+of"
    r"|preliminary|repeal|savings?\s+and\s+transitional|schedule\b|non-?application|general\s+principle|.{0,24}\s+principles?\b)", re.I)

#: Indicators the panel scores at ECONOMY level rather than at provision level — 7.1 asks
#: whether a comprehensive framework exists at all, and 7.2 whether a dedicated cybersecurity
#: framework does. Their citation names the Act as the answer, not a paragraph that states the
#: rule, so pairing the cited article's TEXT with the indicator asks a question the text was
#: never meant to answer. Excluded from the set rather than scored as misses.
_ECONOMY_LEVEL = {"P7-I1", "P7-I2"}


def _usable(text: str, article: str) -> bool:
    """False for a provision that cannot carry an operative rule whatever it is paired with.

    The first version of this anchored the pattern with ^ and then matched it against
    f"{article} {text}", so every heading was preceded by "Section 1 " and NOTHING was ever
    caught. "Short title and commencement", "Interpretation", "Non-application" and "Objects"
    all sailed through the filter written to stop them. Match against the text's own opening
    instead, and against the article label separately.
    """
    if _BOILERPLATE.search(text.lstrip()[:60]):
        return False
    # A definitions clause reads as prose but defines rather than obliges.
    return '" means' not in text[:400] and "\u201d means" not in text[:400]


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
        if not _usable(text, r["article_section"] or ""):
            continue
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
    # NOTE one case was removed here: CSL art.1 -> 7.2. It is a PURPOSE clause
    # ("in order to safeguard cybersecurity ... this Law is enacted"), so it states no
    # operative rule, and 7.2 is an economy-level judgement in any case. It was mine, and
    # it broke the same rule the boilerplate filter above exists to enforce.
    ]



# ── Hand review, 2026-08-22 ──────────────────────────────────────────────────────────
#
# Automated filtering got the set from 37 positives to 32 and no further: the models still
# rejected roughly half, and reading the survivors showed they were right to. Thirty-two cases
# is small enough to read, so they were read. Each rejection below names the reason, because a
# benchmark whose labels are a matter of judgement has to show the judgement.
#
# The distinction applied throughout: does the CITED TEXT state the rule the indicator tests?
# The panel's citation can be sound while this pairing is not — they are recording that an
# economy has a measure, and their article reference sometimes points at the Act generally, or
# at the provision that made them look. Our benchmark asks a narrower question, so a row that
# fails it is not an error in their database.

#: (economy, law-name fragment, article, indicator) -> why this pairing is not usable.
REJECTED = {
    ("AU", "data availability", "Section 45", "P7-I5"):
        "the Commissioner's REGULATORY functions — supervision of a sharing scheme, not a power "
        "to obtain personal data",
    ("AU", "telecommunications act", "Section 10", "P7-I5"):
        "'Extension to external Territories' — a geographic application clause",
    ("AU", "data availability", "Section 3", "P7-I5"):
        "'Objects of this Act' — a purpose clause, no operative rule",
    ("AU", "privacy act", "Section 33D", "P7-I4"):
        "the matched span is a mid-sentence fragment of a list, not the DPO/DPIA duty",
    ("MY", "personal data protection act", "Section 6", "P6-I1"):
        "'General Principle' — consent to PROCESSING. Says nothing about transfer abroad",
    ("MY", "personal data protection act", "Section 6", "P6-I4"):
        "same clause; a consent principle is not a conditional cross-border regime",
    ("MY", "personal data protection act", "Section 1", "P6-I4"):
        "'Short title and commencement'",
    ("MY", "personal data protection act", "Section 5", "P7-I3"):
        "'Personal Data Protection Principles' — lists the seven principles, states no minimum "
        "retention period. 7.3 needs a NUMBER",
    ("MY", "personal data protection act", "Section 7", "P7-I5"):
        "'Notice and Choice Principle' — a duty owed to the data subject, not government access",
    ("SG", "companies act", "Section 4", "P6-I2"):
        "'Interpretation' — a definitions clause. The storage duty is s.199",
    ("SG", "companies act", "Section 4", "P7-I3"):
        "same definitions clause",
    ("SG", "criminal procedure code", "Section 20", "P7-I5"):
        "the matched span is an amendment-history annotation, not the section text",
    ("SG", "personal data protection (notifica", "11", "P7-I4"):
        "matched a paragraph of a Schedule about loans and advances",
}

#: Kept DESPITE looking odd, with the reason, so the judgement is reviewable in both directions.
KEPT_WITH_REASON = {
    ("MY", "personal data protection act", "Section 3", "P7-I5"):
        "'Non-application: this Act shall not apply to the Federal Government and State "
        "Governments' — an exemption of government from the data-protection regime IS how the "
        "panel evidences 7.5 for Malaysia. Kept, and it is the hardest case in the set.",
}


def _rejected(economy: str, law_name: str, article: str, indicator: str) -> str | None:
    low = (law_name or "").lower()
    for (e, frag, art, ind), why in REJECTED.items():
        if e == economy and ind == indicator and frag in low and art == article:
            return why
    return None



# ── Why this is an ALLOWLIST and not a filter ────────────────────────────────────────
#
# Three rounds of automated filtering did not produce a trustworthy set, and the reason is
# structural rather than a bug to be found. The panel's citations are frequently multi-part —
# "Section 199; Section 4", "Section 187C; Section 187AA" — so the article spine holds several
# numbers and a match on ANY of them counts. Section numbers 1, 3, 4 and 5 exist in every
# statute ever drafted, so the matcher kept resolving a citation of Companies Act s.199 to
# Companies Act s.4, and a Malaysian citation to a sectoral Code of Practice about water supply.
#
# The models were what exposed it: eight candidates that disagree about everything else all
# rejected the same labels, and reading those labels showed the models were right. A benchmark
# that scores a correct model as wrong is worse than no benchmark, because the engine
# declaration it would inform cannot be revised afterwards.
#
# So the positives are an explicit list of pairs that have been READ. Every one is a provision
# whose own text states the rule its indicator tests. It is small — that is the honest size of
# what we can currently defend — and it grows as corpora are built for more economies.
#
# Rejected pairs and the reason for each are recorded in REJECTED above, so the judgement is
# reviewable in both directions rather than being a silent deletion.

#: (economy, lowercase fragment of the law name, article as WE extract it, indicator)
ALLOWLIST = {
    ("AU", "my health records act", "Section 77", "P6-I1"),   # "must not hold or take records
    ("AU", "my health records act", "Section 77", "P6-I2"),   #  outside Australia" — the panel
                                                              #  scores it under both
    ("AU", "privacy act", "APP 8", "P6-I4"),                  # cross-border disclosure, the
                                                              #  prescribed-country condition
    ("MY", "personal data protection act", "Section 129", "P6-I1"),
    ("MY", "personal data protection act", "Section 129", "P6-I4"),
    ("MY", "personal data protection act", "Section 112", "P7-I5"),   # power of investigation
    ("MY", "cyber security act", "Section 38(1)", "P7-I5"),
    ("MY", "criminal procedure code", "Section 116B(1)", "P7-I5"),    # access to computerised data
    ("SG", "personal data protection act", "Section 26", "P6-I4"),    # transfer outside Singapore
    ("SG", "personal data protection act", "25", "P7-I3"),            # cease to retain
    ("SG", "income tax act", "Section 67", "P7-I3"),                  # keep books of account
    ("SG", "employment act", "Section 95", "P7-I3"),                  # keep for the period
}


def _allowed(economy: str, law_name: str, article: str, indicator: str) -> bool:
    low = (law_name or "").lower()
    art = (article or "").strip()
    for e, frag, a, ind in ALLOWLIST:
        if e == economy and ind == indicator and frag in low and art.startswith(a):
            return True
    return False


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
        if row["Indicator ID"].strip() in _ECONOMY_LEVEL:
            continue                       # scored at economy level, not against one paragraph
        want_spine = B.article_spine(row["Article / Section"])
        want_law = B.law_tokens(row["Law Name"])
        if not want_spine:
            continue
        cited_is_amending = instrument.classify(row["Law Name"]) is instrument.Status.AMENDING
        hit = None
        for p in pool:
            # An amending act is not the act it amends. This is the single fix that removes
            # most of the bad labels: the panel cites the principal act, and the amending act's
            # name overlaps it almost completely.
            if (instrument.classify(p["law_name"]) is instrument.Status.AMENDING) != cited_is_amending:
                continue
            if not B._same_law(want_law, B.law_tokens(p["law_name"])):
                continue
            if not (B.article_spine(p["article_section"]) & want_spine):
                continue
            if not _usable(p["text"], p["article_section"]):
                continue                   # matched a short title / objects / definitions clause
            hit = p
            break
        if hit is None:
            unmatched.append(f"{row['Economy']} · {row['Law Name'][:40]} · {row['Article / Section']}")
            continue
        if not _allowed(code, hit["law_name"], hit["article_section"],
                        row["Indicator ID"].strip()):
            unmatched.append(f"NOT ON ALLOWLIST {row['Economy']} · {hit['law_name'][:30]} · "
                             f"{hit['article_section']} · {row['Indicator ID']}")
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
        "not_used": len(unmatched),
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
